#!/usr/bin/env python3
"""Isolated app-server protocol fixture. Never calls a model or user account."""
import json
import pathlib
import queue
import sys
import threading
import time
import uuid

if '--version' in sys.argv:
    print('codex-cli 0.162.1-fixture')
    raise SystemExit(0)

root = pathlib.Path.cwd()
incoming = queue.Queue()
active = None
deadline = None
mode = 'ok'
thread_id = 'fixture-thread'


def read():
    for line in sys.stdin:
        incoming.put(json.loads(line))
    incoming.put(None)


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def event(method, **params):
    emit({'method': method, 'params': {'threadId': thread_id, **params}})


def reply(text):
    identity = uuid.uuid4().hex
    event('item/agentMessage/delta', turnId=active, itemId=identity, delta=text[:4])
    event('item/completed', turnId=active, item={'id': identity, 'type': 'agentMessage', 'text': text})


def finish(status='completed'):
    global active, deadline
    if not active:
        return
    if status == 'completed':
        if mode == 'complete':
            current = json.loads((root / 'jobs/current.json').read_text())
            request = json.loads((root / 'jobs' / current['id'] / 'request.json').read_text())
            file = pathlib.Path(request['data']) / 'comments.json'
            reviews = json.loads(file.read_text()); versions = {c['id']: c['updatedAt'] for c in request['comments']}
            for comment in reviews:
                if comment['status'] == 'open' and versions.get(comment['id']) == comment['updatedAt']:
                    comment.update(status='changed', updatedAt=str(time.time_ns()))
            temporary = file.with_suffix('.fixture'); temporary.write_text(json.dumps(reviews)); temporary.replace(file)
        reply('临时任务完成，正式评论未修改。')
    event('turn/completed', turn={'id': active, 'status': status, 'error': {'message': 'Codex 执行未完成（测试）'} if status == 'failed' else None})
    active = None; deadline = None


threading.Thread(target=read, daemon=True).start()
while True:
    try:
        request = incoming.get(timeout=.05)
    except queue.Empty:
        if deadline and time.monotonic() >= deadline:
            finish('failed' if mode == 'fail' else 'completed')
        continue
    if request is None:
        break
    with (root / 'rpc.jsonl').open('a') as file:
        file.write(json.dumps(request, ensure_ascii=False) + '\n')
    method = request.get('method'); params = request.get('params', {})
    if 'id' not in request:
        continue
    result = {}
    if method == 'initialize':
        if (root / 'doctor-behavior').exists() and (root / 'doctor-behavior').read_text() == 'handshake-fail':
            emit({'id': request['id'], 'error': {'code': -32600, 'message': 'SENSITIVE handshake failure'}})
            continue
        result = {'userAgent': 'fixture'}
    elif method == 'account/read':
        behavior = (root / 'doctor-behavior').read_text() if (root / 'doctor-behavior').exists() else ''
        result = {'account': None if behavior in ('unauthenticated', 'api-provider') else {'type': 'chatgpt', 'email': 'SENSITIVE@example.test'},
                  'requiresOpenaiAuth': behavior != 'api-provider'}
    elif method in ('thread/start', 'thread/resume'):
        if method == 'thread/resume':
            thread_id = params['threadId']
        elif (root / 'distinct-threads').exists():
            thread_id = 'fixture-' + uuid.uuid4().hex
        result = {'thread': {'id': thread_id}}
    elif method == 'turn/start':
        mode = (root / 'behavior').read_text() if (root / 'behavior').exists() else 'ok'
        prompt = params['input'][0]['text']
        (root / 'invocation.json').write_text(json.dumps({'args': sys.argv[1:], 'prompt': prompt, 'cwd': str(root)}))
        active = uuid.uuid4().hex
        result = {'turn': {'id': active, 'status': 'inProgress'}}
    elif method == 'turn/steer':
        if params['expectedTurnId'] != active:
            emit({'id': request['id'], 'error': {'code': -32600, 'message': 'No active turn'}})
            continue
        if (root / 'finish-on-steer').exists():
            finish()
            emit({'id': request['id'], 'error': {'code': -32600, 'message': 'No active turn'}})
            continue
        result = {'turnId': active}
    emit({'id': request['id'], 'result': result})
    if method == 'turn/start':
        if mode == 'unsupported':
            emit({'id': 'fixture-client-request', 'method': 'item/tool/call', 'params': {'tool': 'unavailable'}})
        event('turn/started', turn={'id': active, 'status': 'inProgress'})
        reply('正在检查指定评论' if '本次评论快照' in prompt else '同一会话继续：' + prompt)
        deadline = None if mode == 'slow' else time.monotonic() + .25
    elif method == 'turn/steer':
        reply('已收到补充要求：' + params['input'][0]['text'])
    elif method == 'turn/interrupt':
        finish('interrupted')
