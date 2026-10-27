import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from codex_tasks import CodexTasks
from server import make_server


FAKE_CODEX = Path(__file__).with_name('codex_app_server_fixture.py').read_text()


class CodexTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='review-codex-test-')
        self.root = Path(self.temp.name)
        self.pages = self.root / 'pages'; self.pages.mkdir()
        (self.pages / 'index.html').write_text('<html><head></head><body>Review</body></html>')
        self.data = self.root / 'data'; self.data.mkdir()
        self.comment = {'id': 'comment-fixture-001', 'number': 1, 'text': '调整标题；$(不要执行) `不是命令`',
                        'status': 'open', 'updatedAt': '100', 'page': {'path': '/index.html'},
                        'anchor': {'selector': 'body'}, 'screenshot': '/__review/screenshots/fixture.png', 'attachments': []}
        (self.data / 'comments.json').write_text(json.dumps([self.comment]))
        self.executable = self.root / 'codex-fixture'; self.executable.write_text(FAKE_CODEX); self.executable.chmod(0o755)
        self.tasks = CodexTasks(self.root, self.data, self.root / 'jobs', str(self.executable))
        self.server = make_server(self.pages, self.data, 0, codex_tasks=self.tasks)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True); self.worker.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        current = self.tasks.current()
        if current and current['status'] in ('starting', 'running', 'stopping'):
            self.tasks.stop(current['id']); self.wait_done()
        for process in self.tasks.workers:
            process.wait(timeout=5)
        self.server.shutdown(); self.server.server_close(); self.worker.join()
        self.temp.cleanup()

    def post(self, payload=None, path='/__review/codex', origin=None):
        request = Request(self.base + path, data=json.dumps(payload if payload is not None else {'scope': 'all-open'}).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': origin or self.base})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def wait_done(self):
        for _ in range(100):
            job = self.tasks.current()
            if job and job['status'] not in ('starting', 'running', 'stopping'):
                return job
            time.sleep(.1)
        self.fail('Worker did not finish')

    def wait_until(self, predicate):
        for _ in range(100):
            job = self.tasks.current()
            if predicate(job):
                return job
            time.sleep(.1)
        self.fail('Conversation did not reach expected state')

    def send_message(self, text='请保持现有配色', message_id=None, job_id=None):
        return self.post({'jobId': job_id or self.tasks.current()['id'],
                          'messageId': message_id or uuid.uuid4().hex, 'text': text}, '/__review/codex/message')

    def rpc(self):
        return [json.loads(line) for line in (self.root / 'rpc.jsonl').read_text().splitlines()]

    def test_live_messages_steer_same_turn_and_are_idempotent(self):
        (self.root / 'behavior').write_text('slow')
        self.post()
        first = self.wait_until(lambda j: j.get('turnId'))
        message_id = uuid.uuid4().hex
        self.assertEqual(self.send_message(message_id=message_id)[0], 202)
        self.assertEqual(self.send_message(message_id=message_id)[0], 202)
        job = self.wait_until(lambda j: any(m.get('status') == 'sent' and m['id'] == message_id for m in j['messages']))
        self.assertEqual(job['id'], first['id']); self.assertEqual(job['turnId'], first['turnId'])
        calls = [c for c in self.rpc() if c.get('method') == 'turn/steer']
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['params']['expectedTurnId'], first['turnId'])
        self.assertEqual(self.send_message('不能复用编号改正文', message_id)[0], 409)
        self.assertEqual([c['number'] for c in job['comments']], [1])

    def test_completed_conversation_resumes_thread_and_keeps_history(self):
        self.post(); first = self.wait_done()
        self.assertEqual(self.send_message('刚才改了哪些内容？')[0], 202)
        job = self.wait_done()
        self.assertEqual(job['status'], 'completed'); self.assertEqual(job['id'], first['id'])
        self.assertEqual(job['threadId'], first['threadId'])
        self.assertTrue(any(c.get('method') == 'thread/resume' and c['params']['threadId'] == first['threadId'] for c in self.rpc()))
        self.assertTrue(any(m['text'] == '刚才改了哪些内容？' and m['status'] == 'sent' for m in job['messages']))
        self.assertGreater(len(job['messages']), len(first['messages']))

    def test_message_at_turn_boundary_starts_next_turn_on_same_thread(self):
        (self.root / 'behavior').write_text('slow'); self.post()
        first = self.wait_until(lambda j: j.get('turnId'))
        (self.root / 'finish-on-steer').touch(); (self.root / 'behavior').write_text('ok')
        self.send_message('补充一条要求')
        job = self.wait_done()
        self.assertEqual(job['id'], first['id']); self.assertEqual(job['status'], 'completed')
        self.assertTrue(any(m['role'] == 'user' and m['status'] == 'sent' for m in job['messages']))
        self.assertEqual(len([c for c in self.rpc() if c.get('method') == 'thread/start']), 1)
        self.assertEqual(len([c for c in self.rpc() if c.get('method') == 'turn/start']), 2)

    def test_messages_during_startup_and_after_stop_are_not_lost(self):
        (self.root / 'behavior').write_text('slow'); self.post()
        self.send_message('启动时立即补充')
        self.wait_until(lambda j: any(m['role'] == 'user' and m['status'] == 'sent' for m in j['messages']))
        self.tasks.stop(self.tasks.current()['id']); self.wait_done()
        (self.root / 'behavior').write_text('ok')
        self.assertEqual(self.send_message('继续讨论已完成的部分')[0], 202)
        job = self.wait_done()
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(len([m for m in job['messages'] if m['role'] == 'user' and m['status'] == 'sent']), 2)

    def test_conversation_rejects_stale_task_invalid_body_and_foreign_origin(self):
        self.post(); job = self.wait_done()
        self.assertEqual(self.send_message(job_id='stale')[0], 409)
        for message in ['', ' ' * 2, '字' * 4001, ['text']]:
            self.assertEqual(self.send_message(message)[0], 400)
        self.assertEqual(self.send_message(message_id='../outside')[0], 400)
        payload = {'jobId': job['id'], 'messageId': uuid.uuid4().hex, 'text': 'hello'}
        self.assertEqual(self.post(payload, '/__review/codex/message', 'https://unrelated.example')[0], 403)
        self.assertEqual(self.post({**payload, 'command': 'shell'}, '/__review/codex/message')[0], 400)

    def test_legacy_completed_task_can_resume_without_reprocessing_batch(self):
        self.post(); job = self.wait_done()
        path = self.root / 'jobs' / job['id'] / 'status.json'
        raw = json.loads(path.read_text()); raw.pop('transport'); raw.pop('messages')
        path.write_text(json.dumps(raw))
        self.send_message('解释刚才的结果')
        resumed = self.wait_done()
        self.assertEqual(resumed['id'], job['id'])
        self.assertTrue(any(m['id'] == 'previous-result' for m in resumed['messages']))
        self.assertEqual(json.loads((self.root / 'invocation.json').read_text())['prompt'], '解释刚才的结果')

    def test_exec_uses_fixed_command_and_comment_snapshot_without_touching_reviews(self):
        before = (self.data / 'comments.json').read_bytes()
        status, response = self.post(); self.assertEqual(status, 202)
        job = self.wait_done(); self.assertEqual(job['status'], 'completed')
        self.assertIn('临时任务完成', job['result'])
        self.assertEqual(job['threadId'], 'fixture-thread')
        invocation = json.loads((self.root / 'invocation.json').read_text())
        self.assertEqual(invocation['cwd'], str(self.root.resolve()))
        self.assertIn(self.comment['text'], invocation['prompt'])
        self.assertNotIn(self.comment['text'], invocation['args'])
        self.assertIn('approval_policy="never"', invocation['args'])
        self.assertIn('expectedUpdate', invocation['prompt'])
        self.assertEqual((self.data / 'comments.json').read_bytes(), before)
        self.assertEqual(self.post()[1]['job']['id'], response['job']['id'])

    def test_duplicate_clicks_share_one_batch_and_new_comments_wait(self):
        (self.root / 'behavior').write_text('slow')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.post(), range(4)))
        self.assertTrue(all(status == 202 for status, _ in results))
        self.assertEqual(len({data['job']['id'] for _, data in results}), 1)
        second = {**self.comment, 'id': 'comment-fixture-002', 'number': 2}
        (self.data / 'comments.json').write_text(json.dumps([self.comment, second]))
        self.assertEqual(self.post()[1]['job']['id'], results[0][1]['job']['id'])
        snapshot = json.loads((self.root / 'jobs' / results[0][1]['job']['id'] / 'request.json').read_text())
        self.assertEqual([c['id'] for c in snapshot['comments']], [self.comment['id']])
        # A fresh server-side manager sees the same running task and shared lock.
        restored = CodexTasks(self.root, self.data, self.root / 'jobs', str(self.executable))
        self.assertIn(restored.current()['status'], ('starting', 'running'))
        self.assertEqual(restored.start([self.comment], self.base)['id'], results[0][1]['job']['id'])
        self.assertEqual(self.post({'jobId': results[0][1]['job']['id']}, '/__review/codex/stop')[0], 200)
        self.assertEqual(self.wait_done()['status'], 'cancelled')

    def test_failure_can_retry_and_cancellation_does_not_report_success(self):
        (self.root / 'behavior').write_text('fail')
        self.post(); failed = self.wait_done(); self.assertEqual(failed['status'], 'failed')
        self.assertTrue(failed['error']); self.assertFalse(failed['result'])
        (self.root / 'behavior').write_text('ok')
        self.post({'retryJobId': failed['id']}); retried = self.wait_done()
        self.assertEqual(retried['status'], 'completed'); self.assertNotEqual(failed['id'], retried['id'])

    def test_captures_all_open_comments_across_pages_in_number_order(self):
        old = {**self.comment, 'id': 'old-comment', 'number': 0, 'page': {'path': '/other.html'}}
        changed = {**self.comment, 'id': 'changed-comment', 'number': 3, 'status': 'changed'}
        resolved = {**self.comment, 'id': 'resolved-comment', 'number': 4, 'status': 'resolved'}
        (self.data / 'comments.json').write_text(json.dumps([changed, self.comment, resolved, old]))
        _, response = self.post(); job = self.wait_done()
        self.assertEqual([c['id'] for c in job['comments']], [old['id'], self.comment['id']])
        snapshot = json.loads((self.root / 'jobs' / job['id'] / 'request.json').read_text())
        self.assertEqual(snapshot['comments'], [old, self.comment])
        invocation = json.loads((self.root / 'invocation.json').read_text())
        self.assertIn('共 2 条', invocation['prompt'])
        self.assertIn('/other.html', invocation['prompt'])
        self.assertNotIn('changed-comment', invocation['prompt'])
        self.assertNotIn('resolved-comment', invocation['prompt'])
        # An ended process is not evidence that any comment was actually completed.
        self.assertEqual(job['completedCount'], 0)
        self.assertEqual(job['pendingCount'], 2)

    def test_retry_only_includes_unfinished_members_and_preserves_new_comments(self):
        second = {**self.comment, 'id': 'second-comment', 'number': 2}
        (self.data / 'comments.json').write_text(json.dumps([self.comment, second]))
        self.post(); first = self.wait_done()
        self.assertEqual(first['pendingCount'], 2)
        new = {**self.comment, 'id': 'later-comment', 'number': 3}
        completed = {**self.comment, 'status': 'changed', 'updatedAt': '101'}
        (self.data / 'comments.json').write_text(json.dumps([completed, second, new]))
        self.assertEqual(self.tasks.current()['completedCount'], 1)
        status, _ = self.post({'retryJobId': first['id']}); self.assertEqual(status, 202)
        retried = self.wait_done()
        self.assertEqual([c['id'] for c in retried['comments']], [second['id']])
        self.assertNotEqual(first['id'], retried['id'])
        self.assertEqual(self.post({'retryJobId': first['id']})[0], 409)
        # A fresh all-open click includes the new comment and any still unfinished work.
        self.post(); next_batch = self.wait_done()
        self.assertEqual([c['id'] for c in next_batch['comments']], [second['id'], new['id']])

    def test_retry_all_unchanged_pending_comments_starts_a_new_attempt(self):
        self.post(); first = self.wait_done()
        self.assertEqual(self.post()[1]['job']['id'], first['id'])
        self.post({'retryJobId': first['id']}); second = self.wait_done()
        self.assertNotEqual(first['id'], second['id'])

    def test_rejects_legacy_or_arbitrary_commands_foreign_origin_and_empty_batch(self):
        for payload in [{}, {'commentId': self.comment['id'], 'expectedUpdate': '100'},
                        {'scope': 'all-open', 'command': 'echo injected'}, {'retryJobId': []}]:
            self.assertEqual(self.post(payload)[0], 400)
        self.assertEqual(self.post(origin='https://unrelated.example')[0], 403)
        (self.data / 'comments.json').write_text(json.dumps([{**self.comment, 'status': 'changed'}]))
        self.assertEqual(self.post()[0], 409)
        self.assertFalse((self.root / 'invocation.json').exists())

    def test_disabled_or_shared_service_does_not_expose_launcher(self):
        with self.assertRaises(ValueError):
            make_server(self.pages, self.data, 0, public_origins=['https://review.example'], codex_tasks=self.tasks)
        disabled = make_server(self.pages, self.root / 'disabled-data', 0)
        worker = threading.Thread(target=disabled.serve_forever, daemon=True); worker.start()
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen(f'http://127.0.0.1:{disabled.server_port}/__review/codex')
            self.assertEqual(error.exception.code, 404)
        finally:
            disabled.shutdown(); disabled.server_close(); worker.join()
        self.assertIn('data-codex="true"', urlopen(self.base + '/').read().decode())

    def test_server_recreation_preserves_task_and_stop_capability(self):
        (self.root / 'behavior').write_text('slow')
        self.post()
        identity = self.tasks.current()['id']
        original_manager = self.tasks
        self.server.shutdown(); self.server.server_close(); self.worker.join()
        self.tasks = CodexTasks(self.root, self.data, self.root / 'jobs', str(self.executable))
        self.server = make_server(self.pages, self.data, 0, codex_tasks=self.tasks)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True); self.worker.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.assertEqual(self.tasks.current()['id'], identity)
        self.assertIn(self.tasks.current()['status'], ('starting', 'running'))
        self.assertEqual(self.send_message('服务重启后补充要求')[0], 202)
        self.wait_until(lambda j: any(m['role'] == 'user' and m['status'] == 'sent' for m in j['messages']))
        self.post({'jobId': identity}, '/__review/codex/stop')
        self.assertEqual(self.wait_done()['status'], 'cancelled')
        for process in original_manager.workers:
            process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
