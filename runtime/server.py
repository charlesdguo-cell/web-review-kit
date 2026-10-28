#!/usr/bin/env python3
"""Serve any static prototype with persistent reviews, locally or behind HTTPS Nginx."""
import argparse
import base64
from contextlib import contextmanager
from dataclasses import asdict
import errno
import hashlib
from html import escape
import json
import mimetypes
import os
from pathlib import Path
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen
from typing import TYPE_CHECKING
import webbrowser

from data_lock import acquire_data_lock, DataLockError
from data_version import inspect_data_version, require_writable_data, DataVersionError

if TYPE_CHECKING:
    from project_config import ProjectConfig

TOOLS = Path(__file__).resolve().parent
PROJECT = TOOLS.parent.parent
MAX_ATTACHMENTS = 6
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENTS_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'image/gif': 'gif'}


class ReviewHTTPServer(ThreadingHTTPServer):
    # HTTP/2 proxies open many upstream connections together for page assets.
    # The default backlog of five can drop that burst before handlers start.
    request_queue_size = 128

    def __init__(self, address, handler, data_dir):
        self.annotation_tick = None
        self.annotation_error = ''
        self._writers = threading.Condition()
        self._active_writers = 0
        self._closing = False
        self._data_lock = acquire_data_lock(data_dir)
        self._data_lock.__enter__()
        try:
            inspect_data_version(data_dir)
            super().__init__(address, handler)
        except BaseException:
            self._release_data_lock()
            raise

    def _release_data_lock(self):
        owner, self._data_lock = self._data_lock, None
        if owner is not None:
            owner.__exit__(None, None, None)

    @contextmanager
    def data_writer(self):
        # Admit only complete, validated requests. Idle sockets must not hold close
        # open, and a previously accepted socket must never write after ownership ends.
        with self._writers:
            if self._closing:
                raise DataLockError('Review service is closing; reload before saving')
            self._active_writers += 1
        try:
            yield
        finally:
            with self._writers:
                self._active_writers -= 1
                self._writers.notify_all()

    def server_close(self):
        with self._writers:
            self._closing = True
        try:
            super().server_close()
        finally:
            with self._writers:
                while self._active_writers:
                    self._writers.wait()
                self._release_data_lock()

    def service_actions(self):
        # The HTTP lifecycle owns queue dispatch; it never creates a second launcher.
        if self.annotation_tick is not None and not self._closing:
            try:
                with self.data_writer():
                    self.annotation_tick()
                self.annotation_error = ''
            except (OSError, ValueError, KeyError, TypeError, DataLockError):
                # Malformed/unavailable private queue state must not take down the
                # page server or the existing review APIs, nor be silently replayed.
                self.annotation_error = '批注任务队列暂不可用，请检查本机任务记录'


def attachment_image(data_url):
    if not isinstance(data_url, str):
        raise ValueError('附图数据无效')
    header, separator, encoded = data_url.partition(',')
    mime = header.removeprefix('data:').removesuffix(';base64')
    if not separator or header != f'data:{mime};base64' or mime not in IMAGE_EXTENSIONS:
        raise ValueError('附图支持 PNG、JPEG、WebP 和 GIF')
    if len(encoded) > (MAX_ATTACHMENT_BYTES + 2) // 3 * 4:
        raise ValueError('每张附图不能超过 5 MB')
    image = base64.b64decode(encoded, validate=True)
    signatures = {
        'image/png': image.startswith(b'\x89PNG\r\n\x1a\n'),
        'image/jpeg': image.startswith(b'\xff\xd8\xff'),
        'image/gif': image[:6] in (b'GIF87a', b'GIF89a'),
        'image/webp': image.startswith(b'RIFF') and image[8:12] == b'WEBP',
    }
    if not signatures[mime] or len(image) > MAX_ATTACHMENT_BYTES:
        raise ValueError('附图格式无效或超过 5 MB')
    return mime, image


def same_submission(previous, submitted):
    # Server timestamps and the original page snapshot do not change on a retry.
    managed = {'number', 'createdAt', 'updatedAt', 'screenshot', 'screenshotData'}
    def content(record):
        return {**{k: v for k, v in record.items() if k not in managed}, 'attachments': record.get('attachments', [])}
    return content(previous) == content(submitted)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, path)


def make_server(root, data, port, base_path='', public_origins=(), bind_host='127.0.0.1', codex_tasks=None, project_config=None):
    root, data = Path(root).resolve(), Path(data).resolve()
    base_path = '/' + base_path.strip('/') if base_path.strip('/') else ''
    if base_path and not re.fullmatch(r'(?:/[a-zA-Z0-9_-]+)+', base_path):
        raise ValueError('base-path 必须是由字母、数字、下划线或短横线组成的路径')
    origins = set(public_origins)
    if codex_tasks and (bind_host != '127.0.0.1' or origins or base_path):
        raise ValueError('Codex 任务入口只允许在本机独立评审服务启用')
    if bind_host != '127.0.0.1' and not origins:
        raise ValueError('非本机监听必须显式配置 public-origin')
    for origin in origins:
        parts = urlsplit(origin)
        if parts.scheme != 'https' or not parts.netloc or parts.path or parts.query or parts.fragment or parts.username:
            raise ValueError('public-origin 必须是 HTTPS 域名，不包含路径')
    if project_config is not None:
        requested = project_config.server
        if (root != project_config.web_root or data != project_config.data_dir or
                port != requested['port'] or bind_host != requested['host'] or
                base_path != requested['basePath'] or origins != set(requested['publicOrigins']) or
                bool(codex_tasks) != project_config.codex['enabled']):
            raise ValueError('Server arguments do not match project configuration')
    project_id = project_config.project_id if project_config is not None else ''
    page_identity = {'strategy': 'pathname', 'queryKeys': [], 'includeHash': False}
    browser_storage = {'namespace': project_id, 'legacyKeys': []}
    if project_config is not None:
        page_identity.update(project_config.page_identity)
        browser_storage.update(project_config.browser_storage)
    identity_attributes = (f' data-project-id="{escape(project_id, quote=True)}"'
                           f' data-page-identity="{escape(json.dumps(page_identity, ensure_ascii=False), quote=True)}"'
                           f' data-browser-storage="{escape(json.dumps(browser_storage, ensure_ascii=False), quote=True)}"')
    api = base_path + '/__review/'
    lock = threading.Lock()
    manifest = data / 'comments.json'
    annotation_manifest = data / 'annotations.json'

    def records():
        inspect_data_version(data)
        return json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else []

    def annotation_records():
        inspect_data_version(data)
        try:
            items = json.loads(annotation_manifest.read_text(encoding='utf-8')) if annotation_manifest.exists() else []
        except (ValueError, OSError) as error:
            raise DataVersionError('Cannot read content annotations') from error
        if not isinstance(items, list) or any(not isinstance(item, dict) or not isinstance(item.get('id'), str) for item in items):
            raise DataVersionError('Invalid content annotation manifest')
        return items

    def annotation_agent():
        available = bool(codex_tasks and codex_tasks.executable and os.access(codex_tasks.executable, os.X_OK))
        if server.annotation_error:
            return {'enabled': bool(codex_tasks), 'available': False, 'reason': server.annotation_error}
        return {'enabled': bool(codex_tasks), 'available': available,
                'reason': '' if available else '未检测到可执行的本机 Codex' if codex_tasks else '当前入口仅保存批注，自动回复需在本机启用 Agent'}

    def build_id():
        digest = hashlib.sha256()
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.suffix in ('.html', '.js', '.css') and 'vendor' not in p.parts and '.review' not in p.parts:
                digest.update(str(p.relative_to(root)).encode())
                digest.update(p.read_bytes())
        return digest.hexdigest()[:12]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if args and str(args[0]).startswith('POST'):
                # A launcher can exit while this server keeps running. Logging to
                # its closed stderr must not abort a response after a saved write.
                try:
                    super().log_message(fmt, *args)
                except (OSError, ValueError):
                    pass

        def send(self, status, value, content_type='application/json; charset=utf-8', headers=None):
            body = json.dumps(value, ensure_ascii=False).encode() if isinstance(value, (dict, list)) else value
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def do_HEAD(self):
            self.do_GET()

        def send_file(self, target):
            size = target.stat().st_size
            content_type = mimetypes.guess_type(target)[0] or 'application/octet-stream'
            headers = {'Accept-Ranges': 'bytes'}
            status, start, end = 200, 0, size - 1
            # Parse ranges without loading the whole asset into memory.
            requested = self.headers.get('Range', '') if self.command == 'GET' and not self.headers.get('If-Range') else ''
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested.strip(), re.I)
            if match and any(match.groups()):
                first, last = match.groups()
                try:
                    start = int(first) if first else max(0, size - int(last))
                    end = min(int(last), size - 1) if first and last else size - 1
                except ValueError:
                    start, end = 0, size - 1
                else:
                    if start >= size or end < start:
                        headers['Content-Range'] = f'bytes */{size}'
                        return self.send(416, b'', content_type, headers)
                    headers['Content-Range'] = f'bytes {start}-{end}/{size}'
                    status = 206
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(max(0, end - start + 1)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            if self.command == 'HEAD':
                return
            # A media request may be cancelled as soon as its metadata arrives.
            # Keep per-request memory bounded, including large suffix ranges.
            try:
                with target.open('rb') as stream:
                    stream.seek(start)
                    remaining = max(0, end - start + 1)
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def allowed(self, write=False):
            expected = f'127.0.0.1:{self.server.server_port}'
            host = self.headers.get('Host')
            local = host in (expected, f'localhost:{self.server.server_port}')
            origin = 'https://' + (host or '')
            if not local and origin not in origins:
                return False
            if write:
                return self.headers.get('Origin') == ('http://' + host if local else origin)
            return self.headers.get('Sec-Fetch-Site') != 'cross-site'

        def public_record(self, comment):
            # Stored paths remain portable between localhost and any deployment prefix.
            result = dict(comment)
            if result.get('screenshot', '').startswith('/__review/screenshots/'):
                result['screenshot'] = base_path + result['screenshot']
            if 'attachments' in result:
                result['attachments'] = [{**image, 'url': base_path + image['url']} for image in result['attachments']]
            return result

        def public_annotation(self, annotation):
            from annotation_tasks import merge_saved_messages, read_conversation
            result = self.public_record(annotation)
            result['conversation'] = (codex_tasks.annotation_status(annotation['id']) if codex_tasks else
                                      read_conversation(data, annotation['id']))
            result['conversation'] = merge_saved_messages(data, annotation['id'], result['conversation'])
            return result

        def prepare_attachments(self, comment, previous, annotation=False):
            existing = {image['id']: image for image in (previous or {}).get('attachments', [])}
            images = comment.get('attachments', list(existing.values()))
            if not isinstance(images, list) or len(images) > MAX_ATTACHMENTS:
                raise ValueError('每条评论最多添加 6 张附图')
            prepared, pending, identities = [], [], set()
            for index, image in enumerate(images):
                identity = image.get('id') if isinstance(image, dict) else None
                if not isinstance(identity, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', identity) or identity in identities:
                    raise ValueError('附图编号无效或重复')
                identities.add(identity)
                old = existing.get(identity)
                if image.get('dataUrl'):
                    mime, content = attachment_image(image['dataUrl'])
                    filename = hashlib.sha256(content).hexdigest() + '.' + IMAGE_EXTENSIONS[mime]
                    relative = ('annotations/' if annotation else '') + comment['id'] + '/' + filename
                    image_path = data / 'attachments' / relative
                    url = '/__review/attachments/' + relative
                    name = image.get('name') or f'附图 {index + 1}'
                    if not isinstance(name, str) or len(name) > 120:
                        raise ValueError('附图名称过长')
                    stored = {'id': identity, 'name': name, 'mimeType': mime, 'size': len(content), 'url': url}
                    if old and stored != old:
                        raise ValueError('已保存的附图不能替换，请移除后重新添加')
                    pending.append((image_path, content))
                elif old and image.get('url') in (old['url'], base_path + old['url']):
                    stored = dict(old)
                else:
                    raise ValueError('附图不存在，请重新添加')
                prepared.append(stored)
            if sum(image['size'] for image in prepared) > MAX_ATTACHMENTS_BYTES:
                raise ValueError('每条评论的附图合计不能超过 10 MB')
            if 'attachments' in comment or existing:
                comment['attachments'] = prepared
            return prepared, pending

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {'error': '请从已配置的评审入口访问'})
            path = unquote(urlsplit(self.path).path)
            if base_path:
                if not path.startswith(base_path + '/'):
                    return self.send(404, {'error': '不存在'})
                path = path[len(base_path):]
            if path == '/__review/comments':
                with lock:
                    try:
                        items = records()
                    except DataVersionError as error:
                        return self.send(409, {'error': str(error), 'code': error.code})
                    return self.send(200, {'comments': [self.public_record(c) for c in items], 'storage': '服务器共享评审' if origins else str(manifest), 'build': build_id()})
            if path == '/__review/annotations':
                with lock:
                    try:
                        items = annotation_records()
                        return self.send(200, {'annotations': [self.public_annotation(item) for item in items],
                                               'build': build_id(), 'agent': annotation_agent()})
                    except DataVersionError as error:
                        return self.send(409, {'error': str(error), 'code': error.code})
            if path == '/__review/health':
                if project_config is not None:
                    health = configured_health(project_config)
                    if origins:
                        health['build'] = build_id()
                    return self.send(200, health)
                if origins:
                    return self.send(200, {'service': 'prototype-review', 'build': build_id()})
                return self.send(200, {'service': 'prototype-review', 'root': str(root), 'data': str(data)})
            if path == '/__review/codex':
                if not codex_tasks:
                    return self.send(404, {'error': '此评审入口未启用本机 Codex'})
                return self.send(200, codex_tasks.status())
            if path.startswith('/__review/screenshots/'):
                target_root, relative = data / 'screenshots', path.removeprefix('/__review/screenshots/')
            elif path.startswith('/__review/attachments/'):
                target_root, relative = data / 'attachments', path.removeprefix('/__review/attachments/')
            elif path.startswith('/__review/'):
                target_root, relative = TOOLS, path.removeprefix('/__review/')
                if relative not in ('review.js', 'review.css', 'html2canvas.min.js'):
                    return self.send(404, {'error': '不存在'})
            else:
                target_root, relative = root, path.lstrip('/') or 'index.html'
                if any(part.startswith('.') for part in Path(relative).parts):
                    return self.send(404, {'error': '不存在'})
            target = (target_root / relative).resolve()
            if target_root not in target.parents or not target.is_file():
                return self.send(404, {'error': '页面或文件不存在'})
            if target.suffix == '.html':
                html = target.read_text()
                # Every HTML route receives the same module; no page registry or adapters.
                html = re.sub(r'<script\b[^>]*data-prototype-review[^>]*>\s*</script\s*>', '', html, flags=re.I)
                script = f'<script src="{api}review.js" data-prototype-review{identity_attributes} data-build="{build_id()}" data-endpoint="{api}" data-base-path="{base_path}/" data-shared="{str(bool(origins)).lower()}" data-codex="{str(bool(codex_tasks)).lower()}"></script>'
                html = re.sub(r'(<head\b[^>]*>)', lambda m: m[0] + script, html, count=1, flags=re.I) if re.search(r'<head\b', html, re.I) else script + html
                return self.send(200, html.encode(), 'text/html; charset=utf-8')
            return self.send_file(target)

        def do_POST(self):
            if not self.allowed(write=True):
                return self.send(403, {'error': '请从已配置的评审页面保存'})
            if urlsplit(self.path).path in (api + 'codex', api + 'codex/stop', api + 'codex/message'):
                return self.codex_request()
            if urlsplit(self.path).path in (api + 'annotations', api + 'annotations/message', api + 'annotations/retry', api + 'annotations/stop'):
                return self.annotation_request()
            if urlsplit(self.path).path != api + 'comments':
                return self.send(404, {'error': '不存在'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 32 * 1024 * 1024:
                    raise ValueError('评论和图片过大，请减少附图后重试')
                payload = json.loads(self.rfile.read(length))
                comment = payload['comment']
                if not isinstance(comment, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', comment.get('id', '')):
                    raise ValueError('评论编号无效')
                if not isinstance(comment.get('text'), str) or len(comment['text']) > 10000:
                    raise ValueError('评论文字不能超过 10000 字')
                if comment.get('status') not in ('open', 'changed', 'resolved'):
                    raise ValueError('评论状态无效')
                status, value = self.save_comment(payload, comment)
                return self.send(status, value)
            except (DataVersionError, DataLockError) as error:
                return self.send(409, {'error': str(error), 'code': error.code})
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self.send(400, {'error': str(error)})
            except OSError:
                return self.send(500, {'error': '评论文件保存失败，内容仍保留在输入框中'})

        def save_comment(self, payload, comment, annotation=False):
            with lock, self.server.data_writer():
                require_writable_data(data, project_config.project_id if project_config is not None else None)
                if project_config is not None and payload.get('projectId', project_config.project_id) != project_config.project_id:
                    raise DataVersionError('Review submission belongs to a different project')
                items = annotation_records() if annotation else records()
                response_key = 'annotation' if annotation else 'comment'
                previous = next((c for c in items if c['id'] == comment['id']), None)
                try:
                    attachments, pending = self.prepare_attachments(comment, previous, annotation)
                except ValueError:
                    if previous and payload.get('expectedUpdate') != previous.get('updatedAt'):
                        return 409, {'error': '这条评论已更新，请重新打开后再保存'}
                    raise
                if not comment['text'].strip() and not attachments:
                    raise ValueError('请填写评论或添加图片')
                if annotation and previous and same_submission(previous, comment):
                    # Requesting an Agent for a saved annotation is not a content
                    # edit; preserve its evidence version even with a fresh token.
                    return 200, {response_key: self.public_record(previous)}
                if previous and payload.get('expectedUpdate') != previous.get('updatedAt'):
                    # A committed edit may lose its response. A retry of that
                    # exact record is already satisfied; do not rewrite it or
                    # accept any stale changes to content, status or anchors.
                    if same_submission(previous, comment):
                        return 200, {response_key: self.public_record(previous)}
                    return 409, {'error': '这条评论已更新，请重新打开后再保存'}
                screenshot = comment.pop('screenshotData', None)
                if previous:
                    comment['screenshot'] = previous.get('screenshot')
                elif screenshot:
                    if not screenshot.startswith('data:image/png;base64,'):
                        raise ValueError('截图格式无效')
                    image = base64.b64decode(screenshot.split(',', 1)[1], validate=True)
                    if not image.startswith(b'\x89PNG\r\n\x1a\n'):
                        raise ValueError('截图格式无效')
                    image_path = data / 'screenshots' / (('annotation-' if annotation else '') + comment['id'] + '.png')
                    pending.append((image_path, image))
                    comment['screenshot'] = '/__review/screenshots/' + image_path.name
                else:
                    raise ValueError('截图未就绪，请重试保存')
                now = str(time.time_ns())
                comment['number'] = previous['number'] if previous else max((c['number'] for c in items), default=0) + 1
                comment['createdAt'] = previous['createdAt'] if previous else now
                comment['updatedAt'] = now
                if previous:
                    items[items.index(previous)] = comment
                else:
                    items.append(comment)
                for image_path, image in pending:
                    image_path.parent.mkdir(parents=True, exist_ok=True)
                    if not image_path.exists():
                        temporary = image_path.with_name(image_path.name + '.tmp')
                        temporary.write_bytes(image)
                        os.replace(temporary, image_path)
                atomic_json(annotation_manifest if annotation else manifest, items)
                return 200, {response_key: self.public_record(comment)}

        def annotation_request(self):
            from codex_tasks import TaskConflict
            route = urlsplit(self.path).path
            try:
                length = int(self.headers.get('Content-Length', '0'))
                maximum = 32 * 1024 * 1024 if route == api + 'annotations' else 32768
                if not 0 < length <= maximum or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('批注请求格式无效')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError('批注请求格式无效')
                if route == api + 'annotations':
                    if set(payload) - {'annotation', 'expectedUpdate', 'autoReply', 'requestId', 'projectId'}:
                        raise ValueError('批注请求包含未知字段')
                    auto = payload.get('autoReply', False)
                    if type(auto) is not bool:
                        raise ValueError('自动回复参数无效')
                    if auto and not codex_tasks:
                        return self.send(404, {'error': '当前入口未启用自动回复'})
                    if auto and not re.fullmatch(r'[a-f0-9]{32}', str(payload.get('requestId', ''))):
                        raise ValueError('请求编号无效')
                    annotation = payload.get('annotation')
                    if not isinstance(annotation, dict):
                        raise ValueError('批注内容无效')
                    annotation = dict(annotation)
                    annotation.pop('conversation', None)
                    if not isinstance(annotation.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', annotation['id']):
                        raise ValueError('批注编号无效')
                    if not isinstance(annotation.get('text'), str) or len(annotation['text']) > 10000:
                        raise ValueError('批注文字不能超过 10000 字')
                    if annotation.get('status') not in ('open', 'changed', 'resolved'):
                        raise ValueError('批注状态无效')
                    anchor = annotation.get('anchor')
                    if (not isinstance(annotation.get('page'), dict) or not isinstance(annotation['page'].get('path'), str) or
                            not isinstance(anchor, dict) or anchor.get('kind') != 'text' or
                            not isinstance(anchor.get('selector'), str) or not isinstance(anchor.get('selectedText'), str) or
                            not anchor['selectedText'].strip()):
                        raise ValueError('批注需要原文选区和页面位置')
                    if auto:
                        # A lost first response may be retried after the Agent has
                        # already changed the record. Confirm the immutable accepted
                        # request before optimistic save validation; never replay its
                        # old status or overwrite the current annotation.
                        frozen = codex_tasks.annotation_submission(annotation['id'], payload['requestId'])
                        if frozen is not None:
                            self.prepare_attachments(annotation, frozen, annotation=True)
                            if not same_submission(frozen, annotation):
                                raise TaskConflict('已发送请求的内容不能更改，请在批注中继续讨论。')
                            with lock:
                                current = next((item for item in annotation_records() if item['id'] == annotation['id']), None)
                                if current is None:
                                    raise TaskConflict('已发送的批注记录已变化，请刷新核对。')
                                return self.send(200, {'annotation': self.public_annotation(current)})
                    status, result = self.save_comment(payload, annotation, annotation=True)
                    if status != 200:
                        return self.send(status, result)
                    saved = result['annotation']
                    if auto:
                        try:
                            with self.server.data_writer():
                                result['annotation']['conversation'] = codex_tasks.enqueue_annotation(
                                    saved, f'http://127.0.0.1:{self.server.server_port}', payload['requestId'])
                        except (TaskConflict, ValueError, OSError) as error:
                            # Saving evidence succeeded. Keep its identity/version so the UI
                            # retries dispatch instead of creating a duplicate annotation.
                            result['agentError'] = str(error)
                    if 'conversation' not in saved:
                        saved.update(conversation=self.public_annotation(saved)['conversation'])
                    return self.send(200, result)
                action = route.rsplit('/', 1)[1]
                required = {'message': {'annotationId', 'messageId', 'text'},
                            'retry': {'annotationId', 'requestId'}, 'stop': {'annotationId'}}[action]
                allowed = required | ({'autoReply'} if action == 'message' else set())
                if not required <= set(payload) or set(payload) - allowed or not isinstance(payload.get('annotationId'), str):
                    raise ValueError('批注对话请求格式无效')
                auto = payload.get('autoReply', True)
                if type(auto) is not bool:
                    raise ValueError('自动回复参数无效')
                if not codex_tasks and (action != 'message' or auto):
                    return self.send(404, {'error': '当前入口未启用自动回复'})
                if action in ('message', 'retry'):
                    token = payload['messageId' if action == 'message' else 'requestId']
                    if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{32}', token):
                        raise ValueError('请求编号无效')
                if action == 'message' and (not isinstance(payload['text'], str) or not payload['text'].strip() or len(payload['text']) > 4000):
                    raise ValueError('请输入 1–4000 字的消息')
                with lock, self.server.data_writer():
                    require_writable_data(data, project_config.project_id if project_config is not None else None)
                    record = next((item for item in annotation_records() if item['id'] == payload['annotationId']), None)
                    if record is None:
                        return self.send(404, {'error': '批注不存在'})
                    url = f'http://127.0.0.1:{self.server.server_port}'
                    if action == 'message':
                        if auto:
                            conversation = codex_tasks.annotation_message(record, url, payload['messageId'], payload['text'])
                        else:
                            from annotation_tasks import save_annotation_message
                            conversation = save_annotation_message(data, record['id'], payload['messageId'], payload['text'])
                    elif action == 'retry':
                        conversation = codex_tasks.annotation_retry(record, url, payload['requestId'])
                    else:
                        conversation = codex_tasks.annotation_stop(record['id'])
                return self.send(200 if action == 'stop' or not auto else 202, {'conversation': conversation})
            except (DataVersionError, DataLockError) as error:
                return self.send(409, {'error': str(error), 'code': error.code})
            except TaskConflict as error:
                return self.send(409, {'error': str(error)})
            except (ValueError, KeyError, TypeError) as error:
                return self.send(400, {'error': str(error)})
            except OSError:
                return self.send(500, {'error': '批注服务暂不可用，内容已保留，可稍后重试'})

        def codex_request(self):
            if not codex_tasks:
                return self.send(404, {'error': '此评审入口未启用本机 Codex'})
            from codex_tasks import ACTIVE, TaskConflict, job_comments
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 32768 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('任务请求格式无效')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError('任务请求格式无效')
                if urlsplit(self.path).path.endswith('/message'):
                    if set(payload) != {'jobId', 'messageId', 'text'}:
                        raise ValueError('对话只接受任务编号、消息编号和正文')
                    return self.send(202, {'job': codex_tasks.message(payload['jobId'], payload['messageId'], payload['text'])})
                if urlsplit(self.path).path.endswith('/stop'):
                    if set(payload) != {'jobId'}:
                        raise ValueError('停止任务只接受 jobId')
                    return self.send(200, {'job': codex_tasks.stop(payload['jobId'])})
                retry = payload.get('retryJobId')
                if payload != {'scope': 'all-open'} and not (set(payload) == {'retryJobId'} and isinstance(retry, str) and retry):
                    raise ValueError('请刷新页面；启动任务只接受全部待处理评论或重试批次')
                with lock:
                    previous = codex_tasks.current()
                    if previous and previous['status'] in ACTIVE:
                        return self.send(202, {'job': previous})
                    pending = [c for c in records() if c['status'] == 'open']
                    if retry:
                        if not previous or previous['id'] != retry:
                            raise TaskConflict('任务已变化，请刷新后再重试。')
                        ids = {c['id'] for c in job_comments(previous)}
                        pending = [c for c in pending if c['id'] in ids]
                    job = codex_tasks.start(pending, f'http://127.0.0.1:{self.server.server_port}', retry_job_id=retry)
                return self.send(202, {'job': job})
            except TaskConflict as error:
                return self.send(409, {'error': str(error)})
            except (ValueError, TypeError, KeyError) as error:
                return self.send(400, {'error': str(error)})
            except OSError:
                return self.send(500, {'error': '本机任务暂时无法启动，请查看服务日志。'})

    server = ReviewHTTPServer((bind_host, port), Handler, data)
    if codex_tasks:
        server.annotation_tick = codex_tasks.tick_annotations
    return server


def configured_health(config):
    """Local identity includes resolved directories; shared identity exposes no paths."""
    from project_config import TOOL_VERSION
    fingerprint = hashlib.sha256(json.dumps(asdict(config), default=str, sort_keys=True,
                                          separators=(',', ':')).encode()).hexdigest()
    health = {'service': 'prototype-review', 'projectId': config.project_id,
              'toolVersion': TOOL_VERSION, 'requiredToolVersion': config.tool_version,
              'toolVersionPolicy': config.version_policy,
              'versionMatches': TOOL_VERSION == config.tool_version, 'schemaVersion': 1,
              'configurationHash': fingerprint,
              'server': {name: config.server[name] for name in ('host', 'port', 'basePath', 'publicOrigins')},
              'codexEnabled': config.codex['enabled']}
    if not config.server['publicOrigins']:
        health.update(root=str(config.web_root), data=str(config.data_dir))
    return health


def serve_project(config: 'ProjectConfig') -> None:
    """Start the configured project or reuse only its exact existing service."""
    from project_config import ConfigError, TOOL_VERSION
    if config.tool_version != TOOL_VERSION:
        raise ConfigError('Actual runtime VERSION differs from project requirement', 3, 'version_conflict')
    from release_manager import validate_runtime
    validate_runtime(config, release=TOOLS.parent)
    options = config.server
    tasks = None
    if config.codex['enabled']:
        from codex_tasks import CodexTasks, execution_config_for
        tasks = CodexTasks(config.project_root, config.data_dir, config.jobs_dir,
                           config.codex['executable'], execution_config=execution_config_for(config))
    url = f"http://127.0.0.1:{options['port']}{options['basePath']}/"
    result = {'ok': True, 'projectId': config.project_id, 'toolVersion': TOOL_VERSION,
              'requiredToolVersion': config.tool_version, 'versionMatches': True,
              'command': 'serve', 'url': url}
    try:
        server = make_server(config.web_root, config.data_dir, options['port'],
                             options['basePath'], options['publicOrigins'], options['host'],
                             tasks, project_config=config)
    except (OSError, DataLockError) as error:
        if isinstance(error, OSError) and error.errno != errno.EADDRINUSE:
            raise
        try:
            with urlopen(url + '__review/health', timeout=2) as response:
                health = json.load(response)
        except (OSError, ValueError):
            health = {}
        # Shared health also has a content build hash. It is not a service identity.
        expected = configured_health(config)
        if health and {k: v for k, v in health.items() if k != 'build'} == expected:
            validate_runtime(config, release=TOOLS.parent)
            print(json.dumps({**result, 'reused': True}, ensure_ascii=False), flush=True)
            return
        raise ConfigError('Data directory or port is owned by another service, project or configuration',
                          3, 'service_conflict')
    # Lock is held: reject a pin changed between resolution and service startup.
    from project_config import load_project_config
    try:
        current = load_project_config(config.project_root)
        if (current.project_id != config.project_id or current.tool_version != config.tool_version or
                current.version_policy != config.version_policy):
            raise ConfigError('Project pin/identity changed during service startup', 3, 'version_conflict')
        validate_runtime(config, release=TOOLS.parent)
    except BaseException:
        server.server_close()
        raise
    print(json.dumps({**result, 'reused': False}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=PROJECT / 'dist')
    parser.add_argument('--data', type=Path, default=PROJECT / 'review-data')
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--base-path', default='', help='反向代理下的原型路径前缀')
    parser.add_argument('--public-origin', action='append', default=[], help='允许访问的 HTTPS 来源，可重复指定；仍仅监听本机')
    parser.add_argument('--bind-host', default='127.0.0.1', help='默认仅监听本机；容器内可显式使用 0.0.0.0')
    parser.add_argument('--codex', action='store_true', help='在本机项目评审工具栏启用 Codex 任务按钮')
    parser.add_argument('--codex-bin', type=Path, help='指定本机 Codex 可执行文件；默认自动查找')
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error('页面目录不存在；请先在项目根目录运行 ruby tools/build/build-prototype.rb，或用 --root 指定页面目录')
    tasks = None
    if args.codex:
        if args.bind_host != '127.0.0.1' or args.public_origin or args.base_path or args.root.resolve() not in (PROJECT / 'dist', PROJECT / 'prototype'):
            parser.error('Codex 任务按钮仅适用于本机项目目录，不能用于共享或远程评审入口')
        from codex_tasks import CodexTasks
        tasks = CodexTasks(PROJECT, args.data, PROJECT / 'artifacts/review-codex', str(args.codex_bin.resolve()) if args.codex_bin else None)
    try:
        server = make_server(args.root, args.data, args.port, args.base_path, args.public_origin, args.bind_host, tasks)
    except (OSError, DataLockError) as error:
        if isinstance(error, OSError) and error.errno != errno.EADDRINUSE:
            raise
        url = f'http://127.0.0.1:{args.port}/'
        try:
            with urlopen(url + '__review/health', timeout=2) as response:
                health = json.load(response)
        except (OSError, ValueError):
            health = {}
        if health == {'service': 'prototype-review', 'root': str(args.root.resolve()), 'data': str(args.data.resolve())}:
            print(f'评审服务已在运行：{url}', flush=True)
            if args.open:
                webbrowser.open(url)
            return
        parser.error(f'端口 {args.port} 已被其他服务使用，请用 --port 指定另一端口')
    url = f'http://127.0.0.1:{server.server_port}/' + (args.base_path.strip('/') + '/' if args.base_path.strip('/') else '')
    print(f'评审入口：{url}\n评论记录：{args.data.resolve() / "comments.json"}', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
