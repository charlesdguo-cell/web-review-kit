"""One persisted Codex conversation, with live steering through the stdio app server."""
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time

from codex_tasks import inbox_messages, mailbox, write_json


class RpcError(Exception):
    pass


class AppServer:
    def __init__(self, request, directory, notify):
        self.notify = notify
        self.serial = 0
        self.incoming = queue.Queue()
        self.responses = {}
        self.errors = (directory / 'stderr.log').open('a')
        self.events = (directory / 'events.jsonl').open('a')
        environment = dict(os.environ)
        environment.pop('CODEX_THREAD_ID', None)
        self.process = subprocess.Popen(
            [request['executable'], 'app-server', '--listen', 'stdio://',
             '-c', 'approval_policy="never"', '-c', 'sandbox_mode="danger-full-access"'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
            cwd=request['project'], env=environment, text=True, start_new_session=True)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        try:
            for line in self.process.stdout:
                self.events.write(line); self.events.flush()
                try:
                    self.incoming.put(json.loads(line))
                except ValueError:
                    continue
        finally:
            self.incoming.put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def poll(self, timeout=.1):
        try:
            message = self.incoming.get(timeout=timeout)
        except queue.Empty:
            return
        if message is None:
            raise RpcError('Codex app server disconnected')
        if 'method' in message:
            if 'id' in message:
                # This client does not grant new permissions or execute arbitrary client tools.
                self.send({'id': message['id'], 'error': {'code': -32601, 'message': 'Unsupported client request'}})
            else:
                self.notify(message['method'], message.get('params', {}))
        elif 'id' in message:
            self.responses[message['id']] = message

    def call(self, method, params, timeout=30):
        self.serial += 1
        identity = self.serial
        self.send({'id': identity, 'method': method, 'params': params})
        deadline = time.monotonic() + timeout
        while identity not in self.responses:
            if time.monotonic() >= deadline:
                raise RpcError(method + ' timed out')
            self.poll()
        response = self.responses.pop(identity)
        if 'error' in response:
            raise RpcError(response['error'].get('message', 'Codex request failed'))
        return response.get('result', {})

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=3)
        self.reader.join(timeout=2)
        self.process.stdin.close(); self.process.stdout.close()
        self.errors.close(); self.events.close()


def run_session(directory, lock_fd, prompt_for):
    os.fstat(lock_fd)  # Inherited project lock survives a review HTTP server restart.
    request = json.loads((directory / 'request.json').read_text())
    job = json.loads((directory / 'status.json').read_text())
    job.setdefault('messages', [])
    client = None
    active = None
    finished = set()
    stopping = False
    stop_at = None
    released = False
    last_save = 0

    def save():
        nonlocal last_save
        write_json(directory / 'status.json', job)
        last_save = time.monotonic()

    def notify(method, params):
        nonlocal active
        if params.get('threadId') and params['threadId'] != job.get('threadId'):
            return
        if method == 'turn/started':
            active = params['turn']['id']
            job.update(status='running', turnId=active)
        elif method == 'turn/completed':
            turn = params['turn']; finished.add(turn['id'])
            if active == turn['id']:
                active = None
            status = turn['status']
            job.update(status={'completed': 'completed', 'interrupted': 'cancelled'}.get(status, 'failed'), turnId=None)
            if status == 'failed':
                job['error'] = (turn.get('error') or {}).get('message') or 'Codex 执行未完成，请检查登录、网络或任务日志。'
            elif status == 'completed':
                replies = [m for m in job['messages'] if m.get('turnId') == turn['id'] and m['text']]
                job['result'] = replies[-1]['text'] if replies else '本轮处理结束。'
                job['progress'] = '本轮已完成，可继续对话'
                (directory / 'result.txt').write_text(job['result'])
        elif method in ('item/started', 'item/completed', 'item/agentMessage/delta'):
            item = params.get('item') or {}
            identity = item.get('id') or params.get('itemId')
            if method == 'item/agentMessage/delta' or item.get('type') == 'agentMessage':
                message = next((m for m in job['messages'] if m['id'] == identity), None)
                if message is None:
                    message = {'id': identity, 'role': 'assistant', 'text': '', 'createdAt': time.time(),
                               'turnId': params.get('turnId'), 'status': 'streaming'}
                    job['messages'].append(message)
                if method == 'item/agentMessage/delta':
                    message['text'] += params.get('delta', '')
                else:
                    message['text'] = item.get('text', message['text'])
                if method == 'item/completed':
                    message['status'] = 'sent'
                if message['text']:
                    job['progress'] = message['text'][-1200:]
            elif method == 'item/started' and not stopping:
                if item.get('type') == 'commandExecution':
                    job['progress'] = '正在执行本地检查与操作'
                elif item.get('type') == 'fileChange':
                    job['progress'] = '正在修改项目文件'

    def begin(text):
        nonlocal active
        job.update(status='running', error='', progress='正在处理你的消息')
        result = client.call('turn/start', {'threadId': job['threadId'], 'input': [{'type': 'text', 'text': text}]})
        turn = result['turn']
        active = None if turn['id'] in finished else turn['id']
        job['turnId'] = active
        save()

    def deliver(message):
        try:
            if active:
                try:
                    client.call('turn/steer', {'threadId': job['threadId'], 'expectedTurnId': active,
                                              'input': [{'type': 'text', 'text': message['text']}]})
                except RpcError:
                    # A turn can finish while the message is in flight. Continue on the same thread.
                    if active is not None:
                        raise
                    begin(message['text'])
            else:
                begin(message['text'])
            message.update(status='sent', deliveredAt=time.time())
        except RpcError as error:
            message.update(status='failed', error='消息未确认送达，请查看任务状态后重新发送。')
            print('message: ' + str(error), file=sys.stderr)
        write_json(directory / 'inbox' / (message['id'] + '.json'), message)

    try:
        client = AppServer(request, directory, notify)
        client.call('initialize', {'clientInfo': {'name': 'morsea_review', 'title': 'Morsea Review', 'version': '1.0'}})
        client.send({'method': 'initialized'})
        options = {'cwd': request['project'], 'approvalPolicy': 'never', 'sandbox': 'danger-full-access'}
        resuming = bool(job.get('threadId'))
        if resuming:
            options['threadId'] = job['threadId']
        result = client.call('thread/resume' if resuming else 'thread/start', options)
        job.update(threadId=result['thread']['id'], status='running', transport='app-server')
        save()
        if not resuming and not (directory / 'cancel').exists():
            begin(prompt_for(request))
        while True:
            if (directory / 'cancel').exists() and not stopping:
                stopping = True; stop_at = time.monotonic()
                job.update(status='stopping', progress='正在停止任务')
                save()
                if active:
                    try:
                        client.call('turn/interrupt', {'threadId': job['threadId'], 'turnId': active}, timeout=5)
                    except RpcError:
                        pass
            if not stopping:
                for message in inbox_messages(directory):
                    if message['status'] == 'queued':
                        deliver(message)
            if active is None or stopping and time.monotonic() - stop_at > 6:
                with mailbox(directory):
                    pending = [m for m in inbox_messages(directory) if m['status'] == 'queued']
                    if pending and not stopping:
                        continue
                    if stopping:
                        job.update(status='cancelled', progress='任务已停止', result='已停止，已经完成的文件修改仍保留。')
                        for message in pending:
                            message.update(status='failed', error='任务已停止，消息未发送。')
                            write_json(directory / 'inbox' / (message['id'] + '.json'), message)
                    job['finishedAt'] = time.time()
                    save()
                    # Delivery cannot race the last queue check and strand a new message.
                    if active is not None:
                        client.close(); client = None
                    os.close(lock_fd); released = True
                    break
            client.poll()
            if time.monotonic() - last_save > .25:
                save()
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        job.update(status='failed', error='Codex 执行未完成，请检查本机登录、网络或任务日志后重试。')
    finally:
        if client:
            client.close()
        if not released:
            with mailbox(directory):
                job['finishedAt'] = time.time()
                for message in inbox_messages(directory):
                    if message['status'] == 'queued':
                        message.update(status='failed', error='任务中断，消息未确认送达。')
                        write_json(directory / 'inbox' / (message['id'] + '.json'), message)
                save()
                os.close(lock_fd)
