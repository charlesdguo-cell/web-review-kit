import copy
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from project_config import setup_project
from server import make_server
from review_data import ReviewClient, ReviewDataError

PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg=='


class ReviewDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'index.html').write_text('<html><head></head></html>')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.config, _ = setup_project(self.root, {'port': port})
        self.server = make_server(self.root, self.config.data_dir, port, project_config=self.config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(port)
        self.client = ReviewClient(self.base, self.config.project_id)
        comment = {'id': 'synthetic-review-001', 'text': 'original', 'status': 'open',
                   'page': {'path': '/index.html', 'extension': [1, 2]}, 'anchor': {'selector': '#a'},
                   'screenshotData': PNG, 'extension': {'nested': ['preserve']},
                   'attachments': [{'id': 'synthetic-attachment', 'name': 'sample.png', 'dataUrl': PNG}]}
        request = Request(self.base + '/__review/comments', json.dumps({'comment': comment}).encode(),
                          headers={'Origin': self.base, 'Content-Type': 'application/json'})
        with urlopen(request) as response:
            self.saved = json.load(response)['comment']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_mark_changed_preserves_evidence_and_extensions(self):
        frozen = copy.deepcopy(self.saved)
        changed = self.client.mark_changed(frozen, 'verified implementation')
        self.assertEqual(changed['status'], 'changed')
        self.assertEqual(changed['resolution'], 'verified implementation')
        self.assertNotEqual(changed['updatedAt'], frozen['updatedAt'])
        for field, value in frozen.items():
            if field not in ('status', 'resolution', 'updatedAt'):
                self.assertEqual(changed[field], value, field)
        self.assertEqual(frozen, self.saved)
        self.assertEqual(self.client.show(frozen['id']), changed)

    def test_stale_snapshot_never_refreshes_timestamp(self):
        frozen = copy.deepcopy(self.saved)
        self.client.mark_changed(frozen, 'first')
        before = (self.config.data_dir / 'comments.json').read_bytes()
        with self.assertRaises(ReviewDataError) as raised:
            self.client.mark_changed(frozen, 'other')
        self.assertEqual(raised.exception.exit_code, 3)
        self.assertEqual((self.config.data_dir / 'comments.json').read_bytes(), before)

    def test_lost_post_response_retry_is_already_satisfied(self):
        real = self.client._request
        def lose_response(method, path, payload=None):
            result = real(method, path, payload)
            if method == 'POST':
                raise OSError('response lost after commit')
            return result
        with patch.object(self.client, '_request', side_effect=lose_response):
            with self.assertRaises(ReviewDataError):
                self.client.mark_changed(self.saved, 'done')
        before = (self.config.data_dir / 'comments.json').read_bytes()
        changed = self.client.mark_changed(self.saved, 'done')
        self.assertEqual(changed, self.client.show(self.saved['id']))
        self.assertEqual((self.config.data_dir / 'comments.json').read_bytes(), before)

    def test_wrong_project_identity_refuses_write(self):
        before = (self.config.data_dir / 'comments.json').read_bytes()
        with self.assertRaises(ReviewDataError) as raised:
            ReviewClient(self.base, 'wrong-project').mark_changed(self.saved, 'done')
        self.assertEqual(raised.exception.exit_code, 3)
        self.assertEqual((self.config.data_dir / 'comments.json').read_bytes(), before)

    def test_export_preserves_raw_metadata_and_only_downloads_own_evidence(self):
        foreign = copy.deepcopy(self.saved)
        foreign['screenshot'] = 'https://external.invalid/__review/screenshots/secret.png'
        foreign['attachments'].append({'url': self.base + '/index.html', 'custom': True})
        with patch.object(self.client, 'list', return_value=[foreign]):
            exported = self.client.export(self.root / 'export')
        self.assertEqual(json.loads((self.root / 'export/comments.json').read_text()), [foreign])
        files = exported['evidence']
        self.assertEqual(len(files), 1)
        self.assertTrue((self.root / 'export' / files[0]['path']).is_file())

    def test_cli_list_show_export_and_guarded_mark_changed(self):
        cli = Path(__file__).resolve().parents[1] / 'web-review.py'
        def run(*argv):
            process = subprocess.run([sys.executable, str(cli), '--project', str(self.root), *argv],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8)
            return process.returncode, json.loads(process.stdout)
        code, result = run('list')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['comments'], [self.saved])
        code, shown = run('show', '--id', self.saved['id'])
        self.assertEqual(code, 0, shown)
        snapshot = self.root / 'snapshot.json'
        snapshot.write_text(json.dumps(shown), encoding='utf-8')
        resolution = self.root / 'resolution.txt'
        resolution.write_text('已验证', encoding='utf-8')
        command = ('mark-changed', '--snapshot', str(snapshot), '--id', self.saved['id'],
                   '--resolution-file', str(resolution))
        code, changed = run(*command)
        self.assertEqual(code, 0, changed)
        self.assertEqual(changed['comment']['status'], 'changed')
        self.assertEqual(changed['comment']['resolution'], '已验证')
        self.assertEqual(run(*command)[1]['comment'], changed['comment'])
        self.assertEqual(run(*command, '--status', 'resolved')[0], 2)
        self.assertEqual(run(*command, '--force')[0], 2)
        code, exported = run('export', '--output', str(self.root / 'cli-export'))
        self.assertEqual(code, 0, exported)
        self.assertEqual(len(exported['export']['evidence']), 2)

    def test_retry_refuses_unrelated_extension_change_after_lost_response(self):
        changed = self.client.mark_changed(self.saved, 'done')
        altered = {**changed, 'extension': {'unrelated': 'human edit'}}
        request = Request(self.base + '/__review/comments',
                          json.dumps({'comment': altered, 'expectedUpdate': changed['updatedAt']}).encode(),
                          headers={'Origin': self.base, 'Content-Type': 'application/json'})
        with urlopen(request):
            pass
        before = (self.config.data_dir / 'comments.json').read_bytes()
        with self.assertRaises(ReviewDataError) as raised:
            self.client.mark_changed(self.saved, 'done')
        self.assertEqual(raised.exception.exit_code, 3)
        self.assertEqual((self.config.data_dir / 'comments.json').read_bytes(), before)

    def test_server_rejects_explicit_wrong_project_submission(self):
        from urllib.error import HTTPError
        request = Request(self.base + '/__review/comments',
                          json.dumps({'comment': self.saved, 'expectedUpdate': self.saved['updatedAt'],
                                      'projectId': 'foreign-project'}).encode(),
                          headers={'Origin': self.base, 'Content-Type': 'application/json'})
        before = (self.config.data_dir / 'comments.json').read_bytes()
        with self.assertRaises(HTTPError) as raised:
            urlopen(request)
        self.assertEqual(raised.exception.code, 409)
        self.assertEqual((self.config.data_dir / 'comments.json').read_bytes(), before)
