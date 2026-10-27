import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import threading

from data_version import inspect_data_version, activate_data_version, require_writable_data, DataVersionError
from server import make_server


class DataVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        self.data = self.project / 'reviews'
        self.data.mkdir(parents=True)
        self.manifest = self.data / 'comments.json'
        self.raw = '[{"id":"legacy-record", "updatedAt":"unaltered", "unknown":{"keep":true}}]\n'
        self.manifest.write_text(self.raw)
        (self.data / 'screenshots').mkdir()
        (self.data / 'screenshots/evidence.png').write_bytes(b'synthetic evidence')

    def tearDown(self):
        self.temp.cleanup()

    def test_legacy_inspection_is_read_only_and_activation_backs_up_everything(self):
        before = {str(p.relative_to(self.data)): p.read_bytes() for p in self.data.rglob('*') if p.is_file()}
        self.assertTrue(inspect_data_version(self.data)['legacy'])
        self.assertFalse((self.data / 'meta.json').exists())
        result = activate_data_version(self.data, 'project-one', self.root / 'backup', self.project)
        self.assertEqual(result['schemaVersion'], 1)
        self.assertEqual(result['projectId'], 'project-one')
        for path, content in before.items():
            self.assertEqual((self.root / 'backup' / path).read_bytes(), content)
            self.assertEqual((self.data / path).read_bytes(), content)
        self.assertEqual((self.data / 'comments.json').read_text(), self.raw)
        self.assertEqual(self.manifest.stat().st_mtime_ns, (self.root / 'backup/comments.json').stat().st_mtime_ns)

    def test_backup_failure_and_inside_workspace_never_activate(self):
        with self.assertRaises(DataVersionError):
            activate_data_version(self.data, 'project-one', self.project / 'backup', self.project)
        with patch('data_version.shutil.copytree', side_effect=OSError('backup failed')):
            with self.assertRaises(OSError):
                activate_data_version(self.data, 'project-one', self.root / 'backup', self.project)
        self.assertFalse((self.data / 'meta.json').exists())
        self.assertEqual(self.manifest.read_text(), self.raw)

    def test_unknown_version_and_wrong_project_refuse_writes(self):
        meta = self.data / 'meta.json'
        meta.write_text(json.dumps({'schemaVersion': 99, 'projectId': 'one'}))
        self.assertFalse(inspect_data_version(self.data)['supported'])
        with self.assertRaises(DataVersionError):
            require_writable_data(self.data, 'one')
        meta.write_text(json.dumps({'schemaVersion': 1, 'projectId': 'one'}))
        with self.assertRaises(DataVersionError):
            require_writable_data(self.data, 'two')

    def test_corrupt_comments_and_metadata_raise_never_replace(self):
        for target in (self.manifest, self.data / 'meta.json'):
            with self.subTest(target=target.name):
                target.write_text('{broken')
                with self.assertRaisesRegex(DataVersionError, 'Invalid review data JSON'):
                    inspect_data_version(self.data)
                self.assertEqual(target.read_text(), '{broken')
                target.unlink()
        missing = self.root / 'missing'
        self.assertTrue(inspect_data_version(missing)['legacy'])
        self.assertFalse(missing.exists())

    def test_service_reads_legacy_without_activation_and_rejects_unknown_write(self):
        (self.project / 'index.html').write_text('<html></html>')
        server = make_server(self.project, self.data, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            with urlopen(base + '/__review/comments') as response:
                self.assertEqual(json.load(response)['comments'][0]['updatedAt'], 'unaltered')
            self.assertFalse((self.data / 'meta.json').exists())
            (self.data / 'meta.json').write_text(json.dumps({'schemaVersion': 2, 'projectId': 'unknown'}))
            comment = {'id': 'new-review-001', 'text': 'test', 'status': 'open'}
            with self.assertRaises(HTTPError) as raised:
                urlopen(Request(base + '/__review/comments', json.dumps({'comment': comment}).encode(),
                                headers={'Origin': base}))
            self.assertEqual(raised.exception.code, 409)
            self.assertEqual(self.manifest.read_text(), self.raw)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
