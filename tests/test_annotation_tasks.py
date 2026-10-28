"""Synthetic annotation queue tests; only the app-server protocol substitute runs."""
import copy
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
import uuid

from annotation_tasks import public_conversation, publish_conversation, read_conversation, save_annotation_message
from codex_tasks import CodexTasks, TaskConflict, annotation_prompt_for, prompt_for, write_json

FIXTURE = Path(__file__).with_name('codex_app_server_fixture.py').read_text()


class AnnotationTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='annotation-task-')
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'; self.data.mkdir()
        self.output = self.root / 'jobs'
        self.exe = self.root / 'protocol-fixture'; self.exe.write_text(FIXTURE); self.exe.chmod(0o755)
        self.execution = {'projectId': 'synthetic', 'toolVersion': 'test', 'skillPath': '/deliberately/no/batch/skill',
                          'guidance': {'requiredFiles': ['README.synthetic'], 'sourceRoots': ['src/'],
                                       'buildCommands': [['python3', 'build.py']], 'checkCommands': [['python3', 'check.py']]}}
        self.tasks = self.manager()
        (self.root / 'distinct-threads').touch()
        self.a = self.record('annotation-a', '解释这句话是什么意思？')
        self.b = self.record('annotation-b', '请将这句文字改短。')
        (self.data / 'annotations.json').write_text(json.dumps([self.a, self.b]))
        (self.data / 'comments.json').write_text('[]')
        self.base = 'http://127.0.0.1:12345'
        self.managers = [self.tasks]

    def record(self, identity, text):
        return {'id': identity, 'number': 1, 'text': text, 'status': 'open', 'updatedAt': '100',
                'createdAt': '90', 'page': {'path': '/synthetic.html'},
                'anchor': {'type': 'text', 'selector': 'p', 'textRange': {'start': 0, 'end': 2, 'exact': '原文'}},
                'screenshot': '/__review/screenshots/annotation.png', 'attachments': []}

    def manager(self):
        return CodexTasks(self.root, self.data, self.output, str(self.exe), self.execution)

    def tearDown(self):
        try:
            for identity in ('annotation-a', 'annotation-b'):
                try:
                    self.tasks.annotation_stop(identity)
                except (TaskConflict, FileNotFoundError):
                    pass
            for manager in self.managers:
                for process in manager.workers:
                    try:
                        process.wait(timeout=8)
                    except Exception:
                        os.killpg(process.pid, signal.SIGTERM); process.wait(timeout=5)
        finally:
            self.temp.cleanup()

    def wait(self, identity, predicate=lambda status: status['status'] in ('completed', 'failed', 'cancelled')):
        for _ in range(150):
            self.tasks.tick_annotations()
            result = self.tasks.annotation_status(identity)
            if predicate(result):
                return result
            time.sleep(.05)
        self.fail('Annotation did not reach expected state: ' + str(result))

    def calls(self, method):
        try:
            return [c for line in (self.root / 'rpc.jsonl').read_text().splitlines()
                    for c in [json.loads(line)] if c.get('method') == method]
        except FileNotFoundError:
            return []

    def job(self, identity):
        index = json.loads((self.output / 'annotation-index.json').read_text())
        directory = self.output / index['annotations'][identity]
        return directory, json.loads((directory / 'status.json').read_text())

    def enqueue(self, record=None, token=None):
        return self.tasks.enqueue_annotation(record or self.a, self.base, token or uuid.uuid4().hex)

    def test_serial_queue_distinct_snapshots_and_no_legacy_pointer(self):
        (self.root / 'behavior').write_text('slow')
        self.enqueue(); self.wait(self.a['id'], lambda c: c['status'] == 'running' and any(m['role'] == 'assistant' for m in c['messages']))
        second = self.enqueue(self.b)
        self.assertEqual(second['status'], 'queued')
        self.assertEqual(len(self.calls('thread/start')), 1)
        self.assertFalse((self.output / 'current.json').exists())
        self.tasks.execution_config = None
        with self.assertRaises(TaskConflict):
            self.tasks.start([{**self.a, 'id': 'legacy-comment'}], self.base)
        self.tasks.annotation_stop(self.a['id']); self.wait(self.a['id'])
        (self.root / 'behavior').write_text('ok')
        self.assertEqual(self.wait(self.b['id'])['status'], 'completed')
        self.assertEqual(len(self.calls('thread/start')), 2)
        ad, aj = self.job(self.a['id']); bd, bj = self.job(self.b['id'])
        self.assertNotEqual(aj['threadId'], bj['threadId'])
        self.assertNotEqual(ad, bd)
        self.assertEqual(json.loads((ad / 'request.json').read_text())['annotation'], self.a)
        self.assertEqual(json.loads((bd / 'request.json').read_text())['annotation'], self.b)
        self.assertEqual(json.loads((self.data / 'comments.json').read_text()), [])

    def test_external_lock_and_restart_resume_waiting_queue(self):
        lock = self.tasks._lock()
        try:
            self.assertEqual(self.enqueue()['status'], 'queued')
            self.assertEqual(self.enqueue(self.b)['status'], 'queued')
            self.assertEqual(self.calls('initialize'), [])
            restored = self.manager(); self.managers.append(restored); self.tasks = restored
            self.assertEqual(self.tasks.annotation_status(self.a['id'])['status'], 'queued')
        finally:
            lock.close()
        self.assertEqual(self.wait(self.a['id'])['status'], 'completed')
        self.assertEqual(self.wait(self.b['id'])['status'], 'completed')
        self.assertEqual(len(self.calls('turn/start')), 2)

    def test_legacy_batch_and_annotation_use_same_lock_and_pointer_unchanged(self):
        (self.root / 'behavior').write_text('slow')
        self.tasks.execution_config = None
        comment = {**self.a, 'id': 'legacy-comment'}
        legacy = self.tasks.start([comment], self.base)
        self.assertEqual(self.enqueue()['status'], 'queued')
        self.tasks.stop(legacy['id'])
        for _ in range(120):
            current = self.tasks.current()
            if current['status'] not in ('starting', 'running', 'stopping'):
                break
            time.sleep(.05)
        (self.root / 'behavior').write_text('ok')
        self.assertEqual(self.wait(self.a['id'])['status'], 'completed')
        self.assertEqual(self.tasks.current()['id'], legacy['id'])
        self.assertEqual(self.tasks.current()['status'], 'cancelled')

    def test_completed_legacy_followup_rejects_busy_annotation_before_inbox_write(self):
        self.tasks.execution_config = None
        legacy = self.tasks.start([{**self.a, 'id': 'legacy-comment'}], self.base)
        for _ in range(150):
            if self.tasks.current()['status'] == 'completed':
                break
            time.sleep(.05)
        self.assertEqual(self.tasks.current()['status'], 'completed')
        original_thread = self.tasks.current()['threadId']
        (self.root / 'behavior').write_text('slow')
        self.enqueue()
        self.wait(self.a['id'], lambda c: c['status'] == 'running')
        identity = uuid.uuid4().hex
        path = self.output / legacy['id'] / 'inbox' / (identity + '.json')
        with self.assertRaisesRegex(TaskConflict, '尚未发送'):
            self.tasks.message(legacy['id'], identity, '请继续解释旧批次')
        self.assertFalse(path.exists())
        self.tasks.annotation_stop(self.a['id']); self.wait(self.a['id'])
        (self.root / 'behavior').write_text('ok')
        self.tasks.message(legacy['id'], identity, '请继续解释旧批次')
        for _ in range(150):
            resumed = self.tasks.current()
            if resumed['status'] == 'completed':
                break
            time.sleep(.05)
        self.assertEqual(resumed['status'], 'completed')
        self.assertEqual(resumed['threadId'], original_thread)
        self.assertEqual(len([m for m in resumed['messages'] if m['id'] == identity]), 1)
        self.assertEqual(json.loads(path.read_text())['status'], 'sent')

    def test_initial_submission_confirmation_is_original_read_only_and_scoped(self):
        (self.root / 'doctor-behavior').write_text('handshake-fail')
        token = uuid.uuid4().hex
        self.enqueue(token=token); self.assertEqual(self.wait(self.a['id'])['status'], 'failed')
        (self.root / 'doctor-behavior').unlink()
        self.tasks.annotation_retry({**self.a, 'updatedAt': 'new-version', 'status': 'changed'}, self.base, uuid.uuid4().hex)
        self.assertEqual(self.wait(self.a['id'])['status'], 'completed')
        directory, _ = self.job(self.a['id'])
        before = {p: p.read_bytes() for p in (directory / 'request.json', directory / 'status.json',
                                             self.output / 'annotation-index.json')}
        starts = len(self.calls('turn/start'))
        original = self.tasks.annotation_submission(self.a['id'], token)
        self.assertEqual(original, self.a)
        original['text'] = 'must not mutate original'
        self.assertEqual(self.tasks.annotation_submission(self.a['id'], token), self.a)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertEqual(len(self.calls('turn/start')), starts)
        self.assertIsNone(self.tasks.annotation_submission(self.a['id'], uuid.uuid4().hex))
        with self.assertRaises(TaskConflict):
            self.tasks.annotation_submission(self.b['id'], token)
        message = uuid.uuid4().hex
        self.tasks.annotation_message(self.a, self.base, message, 'another message')
        self.wait(self.a['id'])
        with self.assertRaises(TaskConflict):
            self.tasks.annotation_submission(self.a['id'], message)
        # Compatibility with an already persisted pre-field initial request.
        request = json.loads((directory / 'request.json').read_text()); request.pop('initialAnnotation')
        write_json(directory / 'request.json', request)
        self.assertEqual(self.tasks.annotation_submission(self.a['id'], token), request['annotation'])

    def test_initial_message_and_retry_tokens_are_persistent_and_idempotent(self):
        token = uuid.uuid4().hex
        self.enqueue(token=token); self.wait(self.a['id'])
        self.enqueue({**self.a, 'updatedAt': 'new'}, token)
        self.assertEqual(len(self.calls('turn/start')), 1)
        message = uuid.uuid4().hex
        self.tasks.annotation_message(self.a, self.base, message, '再解释一句')
        self.wait(self.a['id'])
        self.tasks.annotation_message(self.a, self.base, message, '再解释一句')
        self.assertEqual(len(self.calls('turn/start')), 2)
        with self.assertRaises(TaskConflict):
            self.tasks.annotation_message(self.a, self.base, message, '不能换正文')
        with self.assertRaises(TaskConflict):
            self.enqueue(self.b, token)
        retry = uuid.uuid4().hex
        self.tasks.annotation_retry({**self.a, 'updatedAt': 'new'}, self.base, retry)
        self.wait(self.a['id']); self.tasks.annotation_retry(self.a, self.base, retry)
        self.assertEqual(len(self.calls('turn/start')), 3)
        self.assertEqual(len(self.calls('thread/resume')), 2)
        directory, _ = self.job(self.a['id'])
        frozen = json.loads((directory / 'inbox' / (retry + '.json')).read_text())
        self.assertEqual(frozen['annotation']['updatedAt'], 'new')

    def test_live_followup_steers_only_its_thread_and_freezes_context(self):
        (self.root / 'behavior').write_text('slow')
        self.enqueue(); self.wait(self.a['id'], lambda c: c['status'] == 'running' and any(m['role'] == 'assistant' for m in c['messages']))
        message = uuid.uuid4().hex
        self.tasks.annotation_message({**self.a, 'updatedAt': 'latest'}, self.base, message, '继续回答这个问题')
        self.wait(self.a['id'], lambda c: any(m['id'] == message and m['status'] == 'sent' for m in c['messages']))
        self.assertEqual(len(self.calls('turn/steer')), 1)
        self.assertIn('latest', self.calls('turn/steer')[0]['params']['input'][0]['text'])
        self.assertEqual(len(self.calls('thread/start')), 1)
        self.enqueue(self.b)
        self.assertEqual(len(self.calls('turn/steer')), 1)

    def test_worker_survives_manager_restart_historical_thread_and_no_skill_injection(self):
        self.enqueue(); first = self.wait(self.a['id'])
        old_dir, first_job = self.job(self.a['id'])
        before = (old_dir / 'request.json').read_bytes()
        restored = self.manager(); self.managers.append(restored); self.tasks = restored
        self.tasks.execution_config['guidance']['requiredFiles'] = ['NEW-UNRELATED']
        self.tasks.annotation_message(self.a, self.base, uuid.uuid4().hex, '继续追问')
        done = self.wait(self.a['id'])
        _, last_job = self.job(self.a['id'])
        self.assertEqual(first_job['threadId'], last_job['threadId'])
        self.assertGreater(len(done['messages']), len(first['messages']))
        self.assertEqual((old_dir / 'request.json').read_bytes(), before)
        self.assertEqual(len(self.calls('thread/resume')), 1)
        for call in self.calls('turn/start'):
            self.assertEqual([item['type'] for item in call['params']['input']], ['text'])
        prompt = self.calls('turn/start')[-1]['params']['input'][0]['text']
        self.assertIn('README.synthetic', prompt); self.assertNotIn('NEW-UNRELATED', prompt)

    def test_crashed_started_worker_fails_without_automatic_replay(self):
        lock = self.tasks._lock()
        self.enqueue()
        lock.close()
        directory, job = self.job(self.a['id'])
        job.update(status='running', threadId='unknown-thread')
        write_json(directory / 'status.json', job)
        restored = self.manager(); self.managers.append(restored); self.tasks = restored
        self.tasks.tick_annotations()
        failed = self.tasks.annotation_status(self.a['id'])
        self.assertEqual(failed['status'], 'failed'); self.assertIn('中断', failed['error'])
        self.tasks.tick_annotations(); self.assertEqual(self.calls('thread/resume'), [])
        self.tasks.annotation_retry(self.a, self.base, uuid.uuid4().hex)
        self.assertEqual(self.wait(self.a['id'])['status'], 'completed')
        self.assertEqual(self.calls('thread/resume')[0]['params']['threadId'], 'unknown-thread')

    def test_stop_queued_then_explicit_retry_and_failed_initial_start(self):
        lock = self.tasks._lock()
        self.enqueue()
        self.assertEqual(self.tasks.annotation_stop(self.a['id'])['status'], 'cancelled')
        lock.close()
        self.tasks.tick_annotations(); self.assertEqual(self.calls('initialize'), [])
        self.tasks.annotation_retry(self.a, self.base, uuid.uuid4().hex)
        self.assertEqual(self.wait(self.a['id'])['status'], 'completed')
        # A failed initializer leaves no thread: retries start once with fresh record.
        (self.root / 'doctor-behavior').write_text('handshake-fail')
        self.enqueue(self.b); self.assertEqual(self.wait(self.b['id'])['status'], 'failed')
        (self.root / 'doctor-behavior').unlink()
        self.tasks.annotation_retry({**self.b, 'updatedAt': 'fresh'}, self.base, uuid.uuid4().hex)
        self.assertEqual(self.wait(self.b['id'])['status'], 'completed')
        self.assertIn('fresh', self.calls('turn/start')[-1]['params']['input'][0]['text'])

    def test_sanitized_snapshot_uses_data_only_and_keeps_manifest_timestamps(self):
        before = (self.data / 'annotations.json').read_bytes()
        self.enqueue(); self.wait(self.a['id'])
        snapshot = read_conversation(self.data, self.a['id'])
        self.assertEqual(snapshot['status'], 'completed')
        self.assertEqual(set(snapshot), {'id', 'status', 'progress', 'result', 'error', 'messages', 'canChat',
                                         'hasAgent', 'initialMessageId'})
        self.assertEqual((self.data / 'annotations.json').read_bytes(), before)
        raw = json.dumps(snapshot)
        for private in ('threadId', 'inputText', 'requestPath', 'executionConfig', str(self.root)):
            self.assertNotIn(private, raw)
        directory, job = self.job(self.a['id'])
        job['result'] = '请看 ' + str(self.root / 'private-file') + ' /Users/another/private/log.txt'
        write_json(directory / 'status.json', job)
        self.tasks.tick_annotations()
        public = read_conversation(self.data, self.a['id'])
        self.assertNotIn(str(self.root), public['result']); self.assertNotIn('/Users/another', public['result'])
        # Shared reads are useful after private job state is absent, and do not launch.
        import shutil
        shutil.rmtree(self.output)
        self.assertEqual(read_conversation(self.data, self.a['id'])['result'], public['result'])
        with self.assertRaises(ValueError):
            read_conversation(self.data, '../escape')

    def test_status_read_is_non_mutating_and_missing_executable_fails_queue_explicitly(self):
        lock = self.tasks._lock()
        self.enqueue()
        directory, _ = self.job(self.a['id'])
        before = (directory / 'status.json').read_bytes()
        snapshot = self.data / 'annotation-threads' / (self.a['id'] + '.json')
        modified = snapshot.stat().st_mtime_ns
        lock.close()
        self.assertEqual(self.tasks.annotation_status(self.a['id'])['status'], 'queued')
        self.assertEqual(self.calls('initialize'), [])
        self.assertEqual((directory / 'status.json').read_bytes(), before)
        self.assertEqual(snapshot.stat().st_mtime_ns, modified)
        self.exe.unlink()
        self.tasks.tick_annotations()
        self.assertEqual(self.tasks.annotation_status(self.a['id'])['status'], 'failed')
        self.assertIn('无法启动', self.tasks.annotation_status(self.a['id'])['error'])
        self.assertEqual(self.calls('initialize'), [])

    def test_lost_enqueue_commit_recovers_inbox_once_without_replaying_sent_message(self):
        self.enqueue(); self.wait(self.a['id'])
        directory, job = self.job(self.a['id'])
        identity = uuid.uuid4().hex
        inbox = directory / 'inbox'; inbox.mkdir(exist_ok=True)
        # Simulate HTTP process death after inbox persistence but before queue/index.
        write_json(inbox / (identity + '.json'), {'id': identity, 'role': 'user', 'text': '边界消息',
                                                 'createdAt': time.time(), 'status': 'queued'})
        self.tasks.annotation_message(self.a, self.base, identity, '边界消息')
        self.assertEqual(self.wait(self.a['id'])['status'], 'completed')
        self.tasks.annotation_message(self.a, self.base, identity, '边界消息')
        self.assertEqual(len(self.calls('turn/start')), 2)
        self.assertEqual(len(self.calls('thread/resume')), 1)

    def test_annotation_prompt_separates_questions_and_scoped_changes(self):
        request = {'kind': 'annotation', 'annotation': self.a, 'project': str(self.root),
                   'data': str(self.data), 'reviewUrl': self.base, 'executionConfig': self.execution}
        prompt = prompt_for(request)
        self.assertEqual(prompt, annotation_prompt_for(request))
        for term in ('问题直接回答', 'open 状态不代表', '__review/annotations', 'expectedUpdate', '不能标记 resolved',
                     '原记录', 'README.synthetic', 'src/', 'build.py', 'check.py', '不写 conversation'):
            self.assertIn(term, prompt)
        self.assertNotIn('Morsea', prompt)

    def test_save_only_without_executable_is_durable_idempotent_and_immutable(self):
        self.exe.unlink()
        before = (self.data / 'annotations.json').read_bytes()
        token = uuid.uuid4().hex
        saved = self.tasks.annotation_message(self.a, self.base, token, '  保存原样的消息  ', False)
        self.assertEqual(saved['status'], 'saved')
        self.assertFalse(saved['hasAgent']); self.assertFalse(saved['canChat'])
        self.assertEqual(saved['messages'][0]['text'], '  保存原样的消息  ')
        ledger = self.data / 'annotation-messages.json'
        frozen = ledger.read_bytes(); modified = ledger.stat().st_mtime_ns
        restored = self.manager(); self.managers.append(restored)
        self.assertEqual(restored.annotation_message(self.a, self.base, token, '  保存原样的消息  ', False), saved)
        self.assertEqual(ledger.read_bytes(), frozen); self.assertEqual(ledger.stat().st_mtime_ns, modified)
        for record, text, auto in [(self.b, '  保存原样的消息  ', False), (self.a, '保存原样的消息', False),
                                   (self.a, '  保存原样的消息  ', True)]:
            with self.assertRaises(TaskConflict):
                self.tasks.annotation_message(record, self.base, token, text, auto)
        self.assertFalse((self.output / 'annotation-index.json').exists())
        self.assertEqual(list(self.output.glob('*/status.json')), [])
        self.assertEqual(self.calls('initialize'), [])
        self.assertEqual((self.data / 'annotations.json').read_bytes(), before)

    def test_save_only_during_worker_and_later_snapshot_publish_cannot_erase_note(self):
        (self.root / 'behavior').write_text('slow')
        self.enqueue()
        self.wait(self.a['id'], lambda c: c['status'] == 'running' and any(m['role'] == 'assistant' for m in c['messages']))
        directory, stale_job = self.job(self.a['id'])
        token = uuid.uuid4().hex
        self.tasks.annotation_message(self.a, self.base, token, '仅保存，不干预正在运行的回复', False)
        self.assertEqual(len(self.calls('turn/steer')), 0)
        self.assertFalse((directory / 'inbox' / (token + '.json')).exists())
        public = publish_conversation(self.data, directory, stale_job)
        self.assertEqual(len([m for m in public['messages'] if m['id'] == token]), 1)
        self.tasks.annotation_stop(self.a['id'])
        done = self.wait(self.a['id'])
        self.assertEqual(len([m for m in done['messages'] if m['id'] == token]), 1)
        self.assertEqual(len(self.calls('turn/start')), 1)
        self.assertEqual(len(self.calls('turn/steer')), 0)
        self.assertFalse(any(m['id'] == token for m in json.loads((directory / 'status.json').read_text())['messages']))

    def test_first_explicit_followup_starts_one_current_intent_with_saved_context(self):
        self.a['text'] = '旧修改要求只能作为上下文'
        note = uuid.uuid4().hex
        self.tasks.annotation_message(self.a, self.base, note, '旧的保存消息，不应补发', False)
        current = uuid.uuid4().hex
        self.tasks.annotation_message(self.a, self.base, current, '只回答现在的问题')
        done = self.wait(self.a['id'])
        self.assertEqual(done['status'], 'completed')
        self.assertEqual(len(self.calls('thread/start')), 1)
        self.assertEqual(len(self.calls('turn/start')), 1)
        self.assertEqual(len(self.calls('turn/steer')), 0)
        prompt = self.calls('turn/start')[0]['params']['input'][0]['text']
        for text in ('本轮补充消息：只回答现在的问题', '旧修改要求只能作为上下文', '旧的保存消息，不应补发', '不追溯执行'):
            self.assertIn(text, prompt)
        self.assertEqual(done['initialMessageId'], 'root-' + self.a['id'])
        self.assertEqual([m['id'] for m in done['messages'] if m['role'] == 'user'],
                         [done['initialMessageId'], note, current])
        self.tasks.annotation_message(self.a, self.base, current, '只回答现在的问题')
        self.assertEqual(len(self.calls('turn/start')), 1)
        with self.assertRaises(TaskConflict):
            self.tasks.annotation_message(self.a, self.base, current, '只回答现在的问题', False)
        self.tasks.annotation_message(self.a, self.base, uuid.uuid4().hex, '下一轮明确发送')
        self.wait(self.a['id'])
        self.assertEqual(len(self.calls('thread/start')), 1)
        self.assertEqual(len(self.calls('thread/resume')), 1)
        self.assertIn('旧的保存消息，不应补发', self.calls('turn/start')[-1]['params']['input'][0]['text'])

    def test_save_only_message_validation_and_public_path_sanitation(self):
        for token, text, auto in [('../bad', 'text', False), (uuid.uuid4().hex, '', False),
                                  (uuid.uuid4().hex, 'x' * 4001, False), (uuid.uuid4().hex, 'text', 'false')]:
            with self.assertRaises(ValueError):
                self.tasks.annotation_message(self.a, self.base, token, text, auto)
        token = uuid.uuid4().hex
        saved = save_annotation_message(self.data, self.a['id'], token, '查看 /Users/test/private/file.txt')
        self.assertNotIn('/Users/test', json.dumps(saved))
        self.assertIn('[本机路径]', saved['messages'][0]['text'])
        self.assertEqual(self.calls('initialize'), [])

    def test_independent_writers_keep_all_saved_messages_without_jobs(self):
        identities = [uuid.uuid4().hex for _ in range(12)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(save_annotation_message, self.data, self.a['id'], token, 'note ' + str(index))
                       for index, token in enumerate(identities)]
            for future in futures:
                future.result()
        saved = read_conversation(self.data, self.a['id'])
        self.assertEqual({m['id'] for m in saved['messages']}, set(identities))
        self.assertEqual(len(saved['messages']), len(identities))
        self.assertEqual(self.calls('initialize'), [])
        self.assertFalse((self.output / 'annotation-index.json').exists())

    def test_preledger_confirmation_uses_private_body_and_legacy_whitespace_contract(self):
        self.enqueue(); self.wait(self.a['id'])
        token = uuid.uuid4().hex
        canonical = '请检查 /Users/synthetic/project/file.txt'
        self.tasks.annotation_message(self.a, self.base, token, canonical)
        self.wait(self.a['id'])
        # This is the baseline persisted shape: canonical index + inbox, no ledger.
        (self.data / 'annotation-messages.json').unlink()
        turns = len(self.calls('turn/start')); steers = len(self.calls('turn/steer'))
        for body in (canonical, '  ' + canonical + '  '):
            self.tasks.annotation_message(self.a, self.base, token, body)
        self.assertEqual(len(self.calls('turn/start')), turns)
        self.assertEqual(len(self.calls('turn/steer')), steers)
        self.assertFalse((self.data / 'annotation-messages.json').exists())
        with self.assertRaises(TaskConflict):
            self.tasks.annotation_message(self.a, self.base, token, canonical + ' changed')
        with self.assertRaises(TaskConflict):
            self.tasks.annotation_message(self.a, self.base, token, canonical, False)

    def test_retry_before_first_thread_refreshes_notes_and_keeps_current_intent(self):
        (self.root / 'doctor-behavior').write_text('handshake-fail')
        current = '本轮只解释'
        self.tasks.annotation_message(self.a, self.base, uuid.uuid4().hex, current)
        self.assertEqual(self.wait(self.a['id'])['status'], 'failed')
        self.assertEqual(len(self.calls('turn/start')), 0)
        note = '后来仅保存但重试时需要看到的上下文'
        self.tasks.annotation_message(self.a, self.base, uuid.uuid4().hex, note, False)
        (self.root / 'doctor-behavior').unlink()
        self.tasks.annotation_retry(self.a, self.base, uuid.uuid4().hex)
        done = self.wait(self.a['id'])
        self.assertEqual(done['status'], 'completed')
        self.assertEqual(len(self.calls('turn/start')), 1)
        prompt = self.calls('turn/start')[0]['params']['input'][0]['text']
        self.assertIn('本轮补充消息：' + current, prompt)
        self.assertIn(note, prompt)
        self.assertNotIn('本轮补充消息：请根据最新批注重试', prompt)
        self.assertEqual(len(self.calls('turn/steer')), 0)

    def test_public_assistant_turn_identity_is_opaque_and_retained_on_read(self):
        self.enqueue()
        done = self.wait(self.a['id'])
        assistants = [m for m in done['messages'] if m['role'] == 'assistant']
        self.assertGreater(len(assistants), 1)
        self.assertEqual(len({m['turnId'] for m in assistants}), 1)
        raw = {'id': self.a['id'], 'status': 'completed', 'messages': [
            {'id': 'safe', 'role': 'assistant', 'text': 'text', 'turnId': 'opaque-turn_1'},
            {'id': 'path', 'role': 'assistant', 'text': 'text', 'turnId': '/Users/private/turn'},
            {'id': 'user', 'role': 'user', 'text': 'text', 'turnId': 'opaque-user'}]}
        public = public_conversation(raw)
        self.assertEqual(public['messages'][0]['turnId'], 'opaque-turn_1')
        self.assertNotIn('turnId', public['messages'][1]); self.assertNotIn('turnId', public['messages'][2])


if __name__ == '__main__':
    unittest.main()
