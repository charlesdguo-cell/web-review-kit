"""Independent content annotation API; no real model or consumer data."""
import copy
import json
from pathlib import Path
import tempfile
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import make_server

PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg=='


class FakeTasks:
    def __init__(self):
        self.executable = sys.executable
        self.sent = {}
        self.originals = {}
        self.failure = False

    def status(self):
        return {'available': True, 'reason': '', 'job': None}

    def tick_annotations(self):
        pass

    def enqueue_annotation(self, record, url, request_id):
        if self.failure:
            raise ValueError('fixture unavailable')
        self.sent.setdefault(request_id, {'id': record['id'], 'status': 'queued', 'messages': [], 'canChat': True})
        self.originals.setdefault(request_id, copy.deepcopy(record))
        return self.sent[request_id]

    def annotation_submission(self, identity, request_id):
        return copy.deepcopy(self.originals.get(request_id))

    def annotation_status(self, identity):
        return next((job for job in self.sent.values() if job['id'] == identity), None)

    def annotation_message(self, record, url, message_id, text):
        from annotation_tasks import register_message
        register_message(self.data, record['id'], message_id, text, True)
        return {'id': record['id'], 'status': 'queued', 'messages': [{'text': text}]}

    def annotation_retry(self, record, url, request_id):
        return self.enqueue_annotation(record, url, request_id)

    def annotation_stop(self, identity):
        return {'id': identity, 'status': 'cancelled'}


class AnnotationAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pages = self.root / 'pages'
        self.pages.mkdir()
        (self.pages / 'index.html').write_text('<html><body><p id="quote">原文内容</p></body></html>')
        self.data = self.root / 'data'
        self.data.mkdir()
        self.legacy = [{'id': 'legacy-comment', 'number': 1, 'text': '原评论', 'status': 'open'}]
        (self.data / 'comments.json').write_text(json.dumps(self.legacy))
        self.original = (self.data / 'comments.json').read_bytes()
        self.annotation = {'id': 'annotation-synthetic', 'text': '解释这段内容', 'status': 'open',
                           'page': {'path': '/', 'title': '合成页面'},
                           'anchor': {'kind': 'text', 'selector': '#quote', 'selectedText': '原文内容'},
                           'screenshotData': PNG, 'attachments': []}
        self.tasks = FakeTasks()
        self.start(self.tasks)

    def start(self, tasks=None, base_path='', origins=()):
        if tasks:
            tasks.data = self.data
        self.server = make_server(self.pages, self.data, 0, base_path=base_path, public_origins=origins, codex_tasks=tasks)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}' + base_path

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def tearDown(self):
        self.stop()
        self.temp.cleanup()

    def request(self, route='annotations', payload=None, origin=None):
        headers = {'Origin': origin or self.base.split('/__review')[0].split('/shared')[0], 'Content-Type': 'application/json'}
        request = Request(self.base + '/__review/' + route,
                          None if payload is None else json.dumps(payload).encode(), headers=headers)
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_separate_manifest_evidence_and_exact_retry(self):
        payload = {'annotation': self.annotation, 'autoReply': True, 'requestId': 'a' * 32}
        status, first = self.request(payload=payload)
        self.assertEqual(status, 200, first)
        saved = first['annotation']
        self.assertEqual(saved['number'], 1)
        self.assertEqual(saved['conversation']['status'], 'queued')
        self.assertEqual(self.request(payload=payload), (200, first))
        self.assertEqual(len(self.tasks.sent), 1)
        self.assertEqual((self.data / 'comments.json').read_bytes(), self.original)
        self.assertTrue((self.data / 'screenshots' / ('annotation-' + self.annotation['id'] + '.png')).exists())
        status, result = self.request()
        self.assertEqual(result['annotations'], [saved])
        self.assertEqual(result['agent'], {'enabled': True, 'available': True, 'reason': ''})

    def test_checked_update_preserves_evidence_and_rejects_stale(self):
        _, first = self.request(payload={'annotation': self.annotation})
        saved = first['annotation']
        changed = {**saved, 'status': 'changed', 'resolution': '检查通过'}
        _, second = self.request(payload={'annotation': changed, 'expectedUpdate': saved['updatedAt']})
        current = second['annotation']
        for key in ('anchor', 'page', 'screenshot', 'attachments', 'createdAt'):
            self.assertEqual(current[key], saved[key])
        self.assertNotEqual(current['updatedAt'], saved['updatedAt'])
        self.assertEqual(self.request(payload={'annotation': {**saved, 'text': 'stale'}, 'expectedUpdate': saved['updatedAt']})[0], 409)
        self.assertEqual(self.tasks.sent, {})

    def test_reply_does_not_update_annotation_timestamp_or_formal_comments(self):
        _, result = self.request(payload={'annotation': self.annotation})
        before = (self.data / 'annotations.json').read_bytes()
        status, reply = self.request('annotations/message', {'annotationId': self.annotation['id'], 'messageId': 'b' * 32, 'text': '继续说明'})
        self.assertEqual(status, 202, reply)
        self.assertEqual(reply['conversation']['status'], 'queued')
        self.assertEqual((self.data / 'annotations.json').read_bytes(), before)
        self.assertEqual((self.data / 'comments.json').read_bytes(), self.original)

    def test_agent_error_returns_saved_annotation_for_safe_retry(self):
        self.tasks.failure = True
        payload = {'annotation': self.annotation, 'autoReply': True, 'requestId': 'c' * 32}
        status, result = self.request(payload=payload)
        self.assertEqual(status, 200, result)
        self.assertIn('fixture unavailable', result['agentError'])
        self.tasks.failure = False
        status, retry = self.request(payload=payload)
        self.assertEqual(retry['annotation']['updatedAt'], result['annotation']['updatedAt'])
        self.assertEqual(len(self.tasks.sent), 1)

    def test_untrusted_conversation_is_not_persisted(self):
        submitted = {**self.annotation, 'conversation': {'status': 'completed', 'result': 'forged'}}
        status, result = self.request(payload={'annotation': submitted})
        self.assertEqual(status, 200, result)
        self.assertIsNone(result['annotation']['conversation'])
        self.assertNotIn('conversation', json.loads((self.data / 'annotations.json').read_text())[0])

    def test_explicit_agent_activation_does_not_edit_saved_annotation(self):
        _, first = self.request(payload={'annotation': self.annotation})
        saved = first['annotation']
        before = (self.data / 'annotations.json').read_bytes()
        status, result = self.request(payload={'annotation': saved, 'expectedUpdate': saved['updatedAt'],
                                               'autoReply': True, 'requestId': 'f' * 32})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['annotation']['updatedAt'], saved['updatedAt'])
        self.assertEqual((self.data / 'annotations.json').read_bytes(), before)

    def test_lost_initial_response_after_agent_update_confirms_without_overwriting(self):
        payload = {'annotation': self.annotation, 'autoReply': True, 'requestId': 'a' * 32}
        _, first = self.request(payload=payload)
        saved = first['annotation']
        changed = {**saved, 'status': 'changed', 'resolution': 'checked modification'}
        _, updated = self.request(payload={'annotation': changed, 'expectedUpdate': saved['updatedAt']})
        before = (self.data / 'annotations.json').read_bytes()
        status, confirmed = self.request(payload=payload)
        self.assertEqual(status, 200, confirmed)
        self.assertEqual(confirmed['annotation'], updated['annotation'])
        self.assertEqual((self.data / 'annotations.json').read_bytes(), before)
        self.assertEqual(len(self.tasks.sent), 1)
        altered = {**payload, 'annotation': {**self.annotation, 'text': 'different request'}}
        self.assertEqual(self.request(payload=altered)[0], 409)

    def test_invalid_requests_do_not_save_or_dispatch(self):
        for override in [{'requestId': '../bad'}, {'autoReply': 'yes'}, {'annotation': []},
                         {'annotation': {**self.annotation, 'anchor': {}}},
                         {'annotation': {**self.annotation, 'id': '../escape'}}]:
            payload = {'annotation': self.annotation, 'autoReply': True, 'requestId': 'd' * 32, **override}
            with self.subTest(override=override):
                self.assertEqual(self.request(payload=payload)[0], 400)
        self.assertEqual(self.request(payload={'annotation': self.annotation}, origin='https://foreign.invalid')[0], 403)
        self.assertFalse((self.data / 'annotations.json').exists())
        self.assertEqual(self.tasks.sent, {})

    def test_disabled_bridge_saves_without_queue_and_blocks_actions(self):
        self.stop()
        self.start()
        status, result = self.request(payload={'annotation': self.annotation})
        self.assertEqual(status, 200, result)
        self.assertIsNone(result['annotation']['conversation'])
        self.assertFalse(self.request()[1]['agent']['enabled'])
        for route, payload in [('annotations', {'annotation': self.annotation, 'autoReply': True, 'requestId': 'e' * 32}),
                               ('annotations/message', {'annotationId': self.annotation['id'], 'messageId': 'f' * 32, 'text': 'follow up'}),
                               ('annotations/retry', {'annotationId': self.annotation['id'], 'requestId': 'f' * 32}),
                               ('annotations/stop', {'annotationId': self.annotation['id']})]:
            self.assertEqual(self.request(route, payload)[0], 404)
        self.assertEqual(self.tasks.sent, {})

    def test_save_only_reply_works_locally_disabled_and_shared_without_task_calls(self):
        for mode in ('local', 'disabled', 'shared'):
            with self.subTest(mode=mode):
                self.stop()
                self.start(self.tasks if mode == 'local' else None,
                           base_path='/shared' if mode == 'shared' else '',
                           origins=('https://review.example.invalid',) if mode == 'shared' else ())
                _, result = self.request(payload={'annotation': self.annotation})
                before = (self.data / 'annotations.json').read_bytes()
                payload = {'annotationId': self.annotation['id'], 'messageId': {'local': '1', 'disabled': '2', 'shared': '3'}[mode] * 32,
                           'text': '保存普通回复 ' + mode, 'autoReply': False}
                status, saved = self.request('annotations/message', payload)
                self.assertEqual(status, 200, saved)
                self.assertEqual(saved['conversation']['status'], 'saved')
                self.assertFalse(saved['conversation']['hasAgent'])
                self.assertFalse(saved['conversation']['canChat'])
                ledger = (self.data / 'annotation-messages.json').read_bytes()
                self.assertEqual(self.request('annotations/message', payload), (200, saved))
                self.assertEqual((self.data / 'annotation-messages.json').read_bytes(), ledger)
                for changed in ({'text': payload['text'] + 'changed'}, {'autoReply': True}):
                    if mode == 'local' or 'text' in changed:
                        self.assertEqual(self.request('annotations/message', {**payload, **changed})[0], 409)
                values = self.request()[1]['annotations'][0]['conversation']['messages']
                self.assertEqual(values[-1]['id'], payload['messageId'])
                self.assertEqual(values[-1]['status'], 'saved')
                self.assertFalse(values[-1]['autoReply'])
                self.assertEqual((self.data / 'annotations.json').read_bytes(), before)
                self.assertEqual((self.data / 'comments.json').read_bytes(), self.original)
                self.assertEqual(self.tasks.sent, {})
                self.assertFalse((self.data / 'annotation-threads').exists())

    def test_save_only_reply_validates_origin_shape_boolean_and_identity(self):
        self.request(payload={'annotation': self.annotation})
        payload = {'annotationId': self.annotation['id'], 'messageId': 'a' * 32, 'text': 'note', 'autoReply': False}
        for changes in ({'annotationId': '../bad'}, {'messageId': '../bad'}, {'text': ''}, {'autoReply': 0}, {'unknown': True}):
            self.assertIn(self.request('annotations/message', {**payload, **changes})[0], (400, 404))
        self.assertEqual(self.request('annotations/message', payload, origin='https://foreign.invalid')[0], 403)
        self.assertFalse((self.data / 'annotation-messages.json').exists())

    def test_annotation_attachment_retry_keeps_original_bytes(self):
        draft = copy.deepcopy(self.annotation)
        draft['attachments'] = [{'id': 'annotation-image', 'name': '附图.png', 'dataUrl': PNG}]
        payload = {'annotation': draft}
        status, saved = self.request(payload=payload)
        self.assertEqual(status, 200, saved)
        self.assertEqual(self.request(payload=payload), (200, saved))
        url = saved['annotation']['attachments'][0]['url']
        self.assertIn('/attachments/annotations/', url)
        with urlopen(self.base + url) as response:
            self.assertTrue(response.read().startswith(b'\x89PNG'))
