"""Persistent annotation conversations using the existing project worker lock.

Private queue/transport state stays with jobs. Only the deliberately small public
projection lives in review data, where backups and shared reads can preserve it.
"""
import copy
import fcntl
import json
from pathlib import Path
import re
import time
import uuid
from contextlib import contextmanager

ACTIVE = {'starting', 'running', 'stopping'}
STATES = ACTIVE | {'queued', 'completed', 'failed', 'cancelled', 'saved'}
IDENTITY = re.compile(r'^[A-Za-z0-9_-]{8,80}$')
TOKEN = re.compile(r'^[0-9a-f]{32}$')


def validate_identity(identity):
    if not isinstance(identity, str) or not IDENTITY.fullmatch(identity):
        raise ValueError('批注编号无效')
    return identity


def validate_token(token):
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError('请求编号无效')


def validate_message(annotation_id, message_id, text, auto_reply):
    validate_identity(annotation_id); validate_token(message_id)
    if type(auto_reply) is not bool:
        raise ValueError('自动回复参数无效')
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError('请输入 1–4000 字的消息')


def message_operations(data_dir):
    try:
        value = json.loads((Path(data_dir) / 'annotation-messages.json').read_text())
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError('批注消息记录无效')
    return value


def register_message(data_dir, annotation_id, message_id, text, auto_reply):
    """Persist immutable send intent outside worker snapshots, without any launcher.

    The data lock is shared by independent HTTP managers. Atomic replacement lets
    worker/public readers merge notes without acquiring private queue locks.
    """
    from codex_tasks import TaskConflict, write_json
    validate_message(annotation_id, message_id, text, auto_reply)
    directory = Path(data_dir)
    with (directory / 'annotation-messages.lock').open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        operations = message_operations(directory)
        operation = {'annotationId': annotation_id, 'text': text, 'autoReply': auto_reply}
        previous = operations.get(message_id)
        if previous is not None:
            if any(previous.get(key) != value for key, value in operation.items()):
                raise TaskConflict('同一消息编号不能更改批注、正文或 Agent 响应选择。')
            return previous
        # Older jobs predate the intent ledger. Respect their public identities.
        snapshot = read_conversation(directory, annotation_id)
        existing = next((m for m in (snapshot or {}).get('messages', []) if m['id'] == message_id), None)
        # Public bodies are redacted, so they cannot establish canonical send
        # intent. The manager validates Agent retries against its private index.
        if existing and not auto_reply:
            raise TaskConflict('请求编号已用于其他消息。')
        operation['createdAt'] = time.time()
        operations[message_id] = operation
        write_json(directory / 'annotation-messages.json', operations)
        return operation


def merge_saved_messages(data_dir, annotation_id, snapshot):
    saved = [{'id': identity, 'role': 'user', 'text': operation['text'], 'status': 'saved',
              'autoReply': False, 'createdAt': operation['createdAt']}
             for identity, operation in message_operations(data_dir).items()
             if operation.get('annotationId') == annotation_id and operation.get('autoReply') is False]
    if not saved:
        return snapshot
    result = copy.deepcopy(snapshot) if snapshot else public_conversation({'id': annotation_id, 'status': 'saved'})
    known = {m['id'] for m in result['messages']}
    result['messages'].extend(m for m in saved if m['id'] not in known)
    result['messages'].sort(key=lambda m: (m['createdAt'], m['id']))
    # Apply the same public sanitation to notes as to worker output.
    return public_conversation(result)


def save_annotation_message(data_dir, annotation_id, message_id, text):
    register_message(data_dir, annotation_id, message_id, text, False)
    return read_conversation(data_dir, annotation_id)


def _text(value, roots=()):
    if not isinstance(value, str):
        return ''
    for root in sorted((str(p) for p in roots if p), key=len, reverse=True):
        value = value.replace(root, '[本机路径]')
    # Public replies must not leak conventional machine-local paths either.
    return re.sub(r'/(?:Users|private|tmp|var|home)/[^\s<>\[\]"\'，。；]+', '[本机路径]', value)


def public_conversation(job, messages=None, roots=()):
    result = {key: _text(job.get(key, ''), roots) for key in ('progress', 'result', 'error')}
    result.update(id=job.get('annotationId', job.get('id', '')),
                  status=job.get('status') if job.get('status') in STATES else 'failed',
                  messages=[], canChat=bool(job.get('threadId') or job.get('status') in ACTIVE | {'queued'}))
    result['canChat'] = bool(job.get('canChat', result['canChat']))
    result['hasAgent'] = bool(job.get('hasAgent', job.get('status') != 'saved'))
    if job.get('initialMessageId'):
        result['initialMessageId'] = str(job['initialMessageId'])
    elif result['hasAgent']:
        initial = next((m for m in job.get('messages', []) if m.get('role') == 'user'), None)
        if initial:
            result['initialMessageId'] = str(initial.get('id', ''))
    for message in messages if messages is not None else job.get('messages', []):
        if message.get('role') not in ('user', 'assistant'):
            continue
        result['messages'].append({'id': str(message.get('id', '')),
                                   'role': message['role'], 'text': _text(message.get('text', ''), roots),
                                   'status': message.get('status', 'sent') if message.get('status', 'sent') in
                                   ('queued', 'streaming', 'sent', 'failed', 'cancelled', 'saved') else 'failed',
                                   'createdAt': message.get('createdAt') if isinstance(message.get('createdAt'), (int, float)) else 0})
        if type(message.get('autoReply')) is bool:
            result['messages'][-1]['autoReply'] = message['autoReply']
        turn_id = message.get('turnId')
        if message['role'] == 'assistant' and isinstance(turn_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', turn_id):
            result['messages'][-1]['turnId'] = turn_id
    return result


def read_conversation(data_dir, annotation_id):
    """Read public data only; this path never discovers or activates a launcher."""
    validate_identity(annotation_id)
    path = Path(data_dir) / 'annotation-threads' / (annotation_id + '.json')
    try:
        snapshot = json.loads(path.read_text())
        # Whitelist again so a manually edited snapshot cannot expose task internals.
        result = public_conversation(snapshot)
        result['id'] = annotation_id
        result['canChat'] = bool(snapshot.get('canChat'))
        return merge_saved_messages(data_dir, annotation_id, result)
    except (OSError, ValueError, TypeError, AttributeError):
        return merge_saved_messages(data_dir, annotation_id, None)


def publish_conversation(data, directory, job, request=None, persist=True):
    from codex_tasks import inbox_messages, write_json
    request = request or json.loads((directory / 'request.json').read_text())
    messages = sorted(job.get('messages', []) + inbox_messages(directory), key=lambda m: (m['createdAt'], m['id']))
    snapshot = public_conversation(job, messages, (request.get('project'), request.get('data'), str(directory.parent)))
    if persist:
        target = Path(data) / 'annotation-threads'
        target.mkdir(parents=True, exist_ok=True)
        write_json(target / (validate_identity(job['annotationId']) + '.json'), snapshot)
    return merge_saved_messages(data, job['annotationId'], snapshot)


class AnnotationTasksMixin:
    @contextmanager
    def _annotation_guard(self):
        # A second HTTP service/manager must see exactly the same idempotency boundary.
        with self.mutex, (self.output / 'annotation-queue.lock').open('a+') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def _annotation_index(self):
        path = self.output / 'annotation-index.json'
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return {'annotations': {}, 'requests': {}}

    def _annotation_save_index(self, index):
        from codex_tasks import write_json
        write_json(self.output / 'annotation-index.json', index)

    def _annotation_job(self, index, annotation_id):
        from codex_tasks import TaskConflict
        identity = index['annotations'].get(annotation_id)
        if not identity:
            raise TaskConflict('批注尚未建立 Agent 对话。')
        if not TOKEN.fullmatch(identity):
            raise ValueError('批注任务关联无效')
        directory = self.output / identity
        return directory, json.loads((directory / 'status.json').read_text())

    def _annotation_available(self):
        import os
        if not self.executable or not os.access(self.executable, os.X_OK):
            raise ValueError('未检测到可执行的本机 Codex；批注已保存。')

    def _annotation_publish(self, directory, job):
        return publish_conversation(self.data, directory, job)

    def _annotation_view(self, directory, job):
        return publish_conversation(self.data, directory, job, persist=False)

    def _tick_annotations_locked(self, index):
        from codex_tasks import write_json
        handle = self._lock()
        try:
            queued = []
            for annotation_id in index['annotations']:
                directory, job = self._annotation_job(index, annotation_id)
                if handle and job['status'] in ACTIVE:
                    # No inherited worker owns the execution lock. Never replay an
                    # uncertain turn, including one interrupted just before spawn.
                    job.update(status='failed', progress='任务已中断',
                               error='任务意外中断，可重试；已经完成的修改仍保留。', finishedAt=time.time())
                    write_json(directory / 'status.json', job)
                    from codex_tasks import inbox_messages
                    for message in inbox_messages(directory):
                        if message['status'] == 'queued':
                            message.update(status='failed')
                            write_json(directory / 'inbox' / (message['id'] + '.json'), message)
                # A live worker publishes its own streaming/final snapshots. A
                # manager must not overwrite them with a stale status read.
                if handle or job['status'] == 'queued':
                    self._annotation_publish(directory, job)
                if job['status'] == 'queued':
                    queued.append((job.get('queuedAt', job['startedAt']), directory, job))
            if handle and queued:
                _, directory, job = min(queued, key=lambda item: (item[0], item[2]['id']))
                try:
                    self._annotation_available()
                    job.update(status='starting', progress='正在启动 Agent', finishedAt=None)
                    write_json(directory / 'status.json', job)
                    self._annotation_publish(directory, job)
                    self._spawn(directory, handle)
                except (OSError, ValueError):
                    job.update(status='failed', error='无法启动本机 Codex，请检查安装与目录权限；已保存的批注和修改仍保留。', finishedAt=time.time())
                    write_json(directory / 'status.json', job)
                    self._annotation_publish(directory, job)
        finally:
            if handle:
                handle.close()
        self.workers = [p for p in self.workers if p.poll() is None]

    def tick_annotations(self):
        with self._annotation_guard():
            self._tick_annotations_locked(self._annotation_index())

    def enqueue_annotation(self, record, review_url, request_id, user_message=None):
        from codex_tasks import TaskConflict, write_json
        identity = validate_identity(record['id']); validate_token(request_id)
        with self._annotation_guard():
            index = self._annotation_index()
            previous = index['requests'].get(request_id)
            operation = ({'annotationId': identity, 'kind': 'initial'} if user_message is None else
                         {'annotationId': identity, 'kind': 'message', 'text': user_message})
            if previous:
                if previous != operation:
                    raise TaskConflict('请求编号已用于其他操作。')
                self._tick_annotations_locked(index)
                return self._annotation_view(*self._annotation_job(index, identity))
            if identity in index['annotations']:
                raise TaskConflict('该批注已有对话，请继续追问或重试。')
            self._annotation_available()
            job = {'id': uuid.uuid4().hex, 'kind': 'annotation', 'annotationId': identity, 'status': 'queued',
                   'startedAt': time.time(), 'queuedAt': time.time(), 'finishedAt': None,
                   'progress': '等待 Agent 处理', 'result': '', 'error': '', 'threadId': None, 'transport': 'app-server',
                   'messages': [{'id': request_id, 'role': 'user', 'text': record['text'], 'status': 'sent', 'createdAt': time.time()}]}
            job['initialMessageId'] = request_id if user_message is None else 'root-' + identity
            job['messages'][0]['id'] = job['initialMessageId']
            if user_message is not None:
                job['messages'][0]['createdAt'] = 0
                job['messages'].append({'id': request_id, 'role': 'user', 'text': user_message,
                                        'status': 'sent', 'autoReply': True, 'createdAt': time.time()})
            directory = self.output / job['id']; directory.mkdir()
            request = {'kind': 'annotation', 'annotation': copy.deepcopy(record),
                       'initialAnnotation': copy.deepcopy(record), 'project': str(self.project),
                       'data': str(self.data), 'reviewUrl': review_url, 'executable': self.executable,
                       'requestPath': str(directory / 'request.json'),
                       'savedContext': (read_conversation(self.data, identity) or {}).get('messages', [])}
            if user_message is not None:
                request['userMessage'] = user_message
            if self.execution_config is not None:
                request['executionConfig'] = copy.deepcopy(self.execution_config)
            write_json(directory / 'request.json', request); write_json(directory / 'status.json', job)
            index['annotations'][identity] = job['id']
            index['requests'][request_id] = operation
            self._annotation_save_index(index)
            self._tick_annotations_locked(index)
            return self._annotation_view(*self._annotation_job(index, identity))

    def annotation_submission(self, annotation_id, request_id):
        """Confirm an accepted initial submit without writing or advancing jobs.

        A worker may already have changed the annotation after a lost response.
        The original frozen envelope lets the server validate that exact retry
        before applying normal optimistic-update checks to ordinary edits.
        """
        from codex_tasks import TaskConflict
        validate_identity(annotation_id); validate_token(request_id)
        with self._annotation_guard():
            index = self._annotation_index()
            previous = index['requests'].get(request_id)
            if previous is None:
                return None
            if previous != {'annotationId': annotation_id, 'kind': 'initial'}:
                raise TaskConflict('请求编号已用于其他操作。')
            directory, _ = self._annotation_job(index, annotation_id)
            request = json.loads((directory / 'request.json').read_text())
            return copy.deepcopy(request.get('initialAnnotation', request['annotation']))

    def _annotation_queue_message(self, index, directory, job, record, review_url, message_id, text, retry=False):
        from codex_tasks import TaskConflict, mailbox, write_json, annotation_prompt_for
        with mailbox(directory):
            # The worker may have published a newer state while we waited.
            job = json.loads((directory / 'status.json').read_text())
            folder = directory / 'inbox'; folder.mkdir(exist_ok=True)
            path = folder / (message_id + '.json')
            if path.exists():
                existing = json.loads(path.read_text())
                if existing['text'] != text:
                    raise TaskConflict('同一消息编号不能更改正文。')
                # Recover an uncommitted enqueue (inbox persisted before the
                # queue marker/index). Sent or failed messages are never replayed.
                if existing['status'] == 'queued' and job['status'] not in ACTIVE | {'queued'}:
                    job.update(status='queued', queuedAt=time.time(), progress='等待 Agent 处理', error='', finishedAt=None)
                    (directory / 'cancel').unlink(missing_ok=True)
                    write_json(directory / 'status.json', job)
                return
            if job['status'] == 'stopping':
                raise TaskConflict('任务正在停止，请停止后再继续对话。')
            if retry and job['status'] in ACTIVE | {'queued'}:
                raise TaskConflict('任务仍在处理，请等待完成。')
            self._annotation_available()
            request = json.loads((directory / 'request.json').read_text())
            context = {**request, 'annotation': copy.deepcopy(record), 'reviewUrl': review_url,
                       'userMessage': text, 'retry': retry,
                       'savedContext': [m for m in (read_conversation(self.data, record['id']) or {}).get('messages', [])
                                        if m.get('autoReply') is False]}
            message = {'id': message_id, 'role': 'user', 'text': text, 'inputText': annotation_prompt_for(context),
                       'annotation': copy.deepcopy(record), 'createdAt': time.time(), 'status': 'queued'}
            if not job.get('threadId') and job['status'] not in ACTIVE | {'queued'}:
                # No thread was established. A user retry is explicit permission to
                # start this freshly frozen request; a plain follow-up is not.
                if not retry:
                    raise TaskConflict('任务尚未建立会话，请重试。')
                request.update(annotation=copy.deepcopy(record), reviewUrl=review_url,
                               savedContext=context['savedContext'])
                write_json(directory / 'request.json', request)
                # First prompt now includes current annotation. Avoid delivering it twice.
                message['status'] = 'sent'
            write_json(path, message)
            if job['status'] not in ACTIVE | {'queued'}:
                job.update(status='queued', queuedAt=time.time(), progress='等待 Agent 处理', error='', finishedAt=None)
                (directory / 'cancel').unlink(missing_ok=True)
                write_json(directory / 'status.json', job)

    def annotation_message(self, record, review_url, message_id, text, auto_reply=True):
        from codex_tasks import TaskConflict
        identity = record['id']
        validate_message(identity, message_id, text, auto_reply)
        if not auto_reply:
            return save_annotation_message(self.data, identity, message_id, text)
        # This explicit current message is the only new executable intent. Earlier
        # saved root/notes are context, never queued or replayed as separate turns.
        with self._annotation_guard():
            index = self._annotation_index()
            previous = index['requests'].get(message_id)
            ledger_entry = message_operations(self.data).get(message_id)
            if previous:
                # Before the intent ledger existed, accepted Agent messages were
                # stripped. Confirm that private canonical value before looking
                # at a sanitized public projection or introducing a new ledger.
                canonical = text if ledger_entry is not None else text.strip()
                if previous != {'annotationId': identity, 'kind': 'message', 'text': canonical}:
                    raise TaskConflict('请求编号已用于其他消息。')
                if ledger_entry is not None:
                    register_message(self.data, identity, message_id, text, True)
                self._tick_annotations_locked(index)
                return self._annotation_view(*self._annotation_job(index, identity))
            first = identity not in index['annotations']
            legacy_inbox = False
            if not first:
                directory, job = self._annotation_job(index, identity)
                inbox = directory / 'inbox' / (message_id + '.json')
                if ledger_entry is None and inbox.exists():
                    canonical = json.loads(inbox.read_text()).get('text')
                    if canonical != text.strip():
                        raise TaskConflict('同一消息编号不能更改正文。')
                    text = canonical
                    legacy_inbox = True
            if not legacy_inbox:
                register_message(self.data, identity, message_id, text, True)
            if not first:
                operation = {'annotationId': identity, 'kind': 'message', 'text': text}
                self._annotation_queue_message(index, directory, job, record, review_url, message_id, text)
                index['requests'][message_id] = operation; self._annotation_save_index(index)
                self._tick_annotations_locked(index)
                return self._annotation_view(*self._annotation_job(index, identity))
        # enqueue_annotation takes the same guard; dispatch after leaving.
        return self.enqueue_annotation(record, review_url, message_id, user_message=text)

    def annotation_retry(self, record, review_url, request_id):
        from codex_tasks import TaskConflict
        identity = validate_identity(record['id']); validate_token(request_id)
        with self._annotation_guard():
            index = self._annotation_index(); directory, job = self._annotation_job(index, identity)
            operation = {'annotationId': identity, 'kind': 'retry'}
            previous = index['requests'].get(request_id)
            if previous and previous != operation:
                raise TaskConflict('请求编号已用于其他操作。')
            if not previous:
                self._annotation_queue_message(index, directory, job, record, review_url, request_id,
                                               '请根据最新批注重试上一次未完成的请求，保留已有修改并先核对实际状态。', retry=True)
                index['requests'][request_id] = operation; self._annotation_save_index(index)
            self._tick_annotations_locked(index)
            return self._annotation_view(*self._annotation_job(index, identity))

    def annotation_stop(self, annotation_id):
        from codex_tasks import inbox_messages, mailbox, write_json
        validate_identity(annotation_id)
        with self._annotation_guard():
            index = self._annotation_index(); directory, job = self._annotation_job(index, annotation_id)
            with mailbox(directory):
                job = json.loads((directory / 'status.json').read_text())
                if job['status'] == 'queued':
                    job.update(status='cancelled', progress='任务已停止', finishedAt=time.time())
                    for message in inbox_messages(directory):
                        if message['status'] == 'queued':
                            message.update(status='failed'); write_json(directory / 'inbox' / (message['id'] + '.json'), message)
                    write_json(directory / 'status.json', job)
                elif job['status'] in ACTIVE:
                    (directory / 'cancel').touch()
                    # Worker owns status.json while running; only its cancel marker
                    # is changed here, avoiding lost streaming messages.
                    job.update(status='stopping', progress='正在停止任务')
                if job['status'] == 'cancelled':
                    self._annotation_publish(directory, job)
                return self._annotation_view(directory, job)

    def annotation_status(self, annotation_id):
        # Polling is read-only. Server service_actions drives queue advancement
        # under its data-writer lease; worker saves publish live snapshots.
        return read_conversation(self.data, annotation_id)
