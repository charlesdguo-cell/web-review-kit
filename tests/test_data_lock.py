import json
import socket
import threading
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from data_lock import acquire_data_lock, DataLockError
from server import make_server, atomic_json

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'
CHILD = '''import json, sys
from server import make_server
server = make_server(sys.argv[1], sys.argv[2], 0)
print(json.dumps({'port': server.server_port}), flush=True)
server.serve_forever()
'''
PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg=='


class DataLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'index.html').write_text('<html></html>')
        self.children = []

    def tearDown(self):
        for child in self.children:
            child.terminate()
            child.wait(timeout=5)
            child.stdout.close()
            child.stderr.close()
        self.temp.cleanup()

    def start(self, data):
        import os
        child = subprocess.Popen([sys.executable, '-u', '-c', CHILD, str(self.root), str(data)],
                                 env={**os.environ, 'PYTHONPATH': str(RUNTIME)},
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.children.append(child)
        return child

    def save(self, port, identity):
        base = 'http://127.0.0.1:' + str(port)
        comment = {'id': identity, 'text': 'synthetic', 'status': 'open', 'screenshotData': PNG}
        with urlopen(Request(base + '/__review/comments', json.dumps({'comment': comment}).encode(),
                             headers={'Origin': base, 'Content-Type': 'application/json'})) as response:
            self.assertEqual(response.status, 200)

    def test_real_process_same_canonical_directory_rejected_first_still_saves(self):
        data = self.root / 'data'
        first = self.start(data)
        port = json.loads(first.stdout.readline())['port']
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        second = self.start(alias / 'data')
        _, error = second.communicate(timeout=5)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn('Another review writer', error)
        self.save(port, 'first-writer-001')
        self.assertEqual(len(json.loads((data / 'comments.json').read_text())), 1)

    def test_different_directories_can_write_simultaneously(self):
        first, second = self.start(self.root / 'one'), self.start(self.root / 'two')
        self.save(json.loads(first.stdout.readline())['port'], 'first-writer-001')
        self.save(json.loads(second.stdout.readline())['port'], 'second-writer-001')
        self.assertTrue((self.root / 'one/comments.json').exists())
        self.assertTrue((self.root / 'two/comments.json').exists())

    def test_close_and_initialization_failure_release_lock(self):
        data = self.root / 'data'
        first = make_server(self.root, data, 0)
        with self.assertRaises(DataLockError):
            make_server(self.root, data, 0)
        first.server_close()
        first.server_close()
        with patch('server.inspect_data_version', side_effect=ValueError('init failure')):
            with self.assertRaises(ValueError):
                make_server(self.root, data, 0)
        with acquire_data_lock(data):
            pass
        second = make_server(self.root, data, 0)
        try:
            with self.assertRaises(OSError):
                make_server(self.root, self.root / 'other', second.server_port)
            with acquire_data_lock(self.root / 'other'):
                pass
        finally:
            second.server_close()

    def test_legacy_cli_can_reuse_its_exact_running_service(self):
        data = self.root / 'legacy-data'
        child = self.start(data)
        port = json.loads(child.stdout.readline())['port']
        process = subprocess.run([sys.executable, str(RUNTIME / 'server.py'), '--root', str(self.root),
                                  '--data', str(data), '--port', str(port)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('已在运行', process.stdout)
        self.save(port, 'still-writing-001')

    def test_close_drains_inflight_write_before_replacement_can_save(self):
        data = self.root / 'drain-data'
        entered, resume, close_started, closed = (threading.Event() for _ in range(4))
        failures = []
        def paused_write(path, value):
            entered.set()
            if not resume.wait(5):
                raise RuntimeError('test did not release pending write')
            atomic_json(path, value)
        server = make_server(self.root, data, 0)
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        def first_save():
            try:
                self.save(server.server_port, 'first-review')
            except BaseException as error:
                failures.append(error)
        def close():
            close_started.set()
            server.server_close()
            closed.set()
        writing = threading.Thread(target=first_save, daemon=True)
        closing = threading.Thread(target=close, daemon=True)
        replacement = None
        replacement_worker = None
        try:
            with patch('server.atomic_json', side_effect=paused_write):
                writing.start()
                self.assertTrue(entered.wait(3))
                server.shutdown()
                serving.join(timeout=3)
                closing.start()
                self.assertTrue(close_started.wait(1))
                self.assertFalse(closed.wait(0.1), 'closed before pending writer drained')
                with self.assertRaises(DataLockError):
                    make_server(self.root, data, 0)
                resume.set()
                writing.join(timeout=3)
                closing.join(timeout=3)
                self.assertTrue(closed.is_set())
                self.assertFalse(writing.is_alive())
            self.assertEqual(failures, [])
            replacement = make_server(self.root, data, 0)
            replacement_worker = threading.Thread(target=replacement.serve_forever, daemon=True)
            replacement_worker.start()
            self.save(replacement.server_port, 'second-review')
            self.assertEqual([item['id'] for item in json.loads((data / 'comments.json').read_text())],
                             ['first-review', 'second-review'])
        finally:
            resume.set()
            writing.join(timeout=3)
            if closing.ident is not None:
                closing.join(timeout=3)
            server.shutdown()
            server.server_close()
            serving.join(timeout=3)
            if replacement is not None:
                replacement.shutdown()
                replacement.server_close()
                replacement_worker.join(timeout=3)

    def test_idle_partial_post_cannot_hold_close_or_write_after_release(self):
        data = self.root / 'idle-data'
        server = make_server(self.root, data, 0)
        begun = threading.Event()
        original_post = server.RequestHandlerClass.do_POST
        def signal_post(handler):
            begun.set()
            return original_post(handler)
        server.RequestHandlerClass.do_POST = signal_post
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        connection = socket.create_connection(('127.0.0.1', server.server_port), timeout=3)
        comment = {'id': 'late-review', 'text': 'late', 'status': 'open', 'screenshotData': PNG}
        payload = json.dumps({'comment': comment}).encode()
        headers = ('POST /__review/comments HTTP/1.0\r\nHost: 127.0.0.1:{0}\r\n'
                   'Origin: http://127.0.0.1:{0}\r\nContent-Length: {1}\r\n\r\n').format(
                       server.server_port, len(payload)).encode()
        closed = threading.Event()
        closing = threading.Thread(target=lambda: (server.server_close(), closed.set()), daemon=True)
        replacement = None
        try:
            connection.sendall(headers + payload[:1])
            self.assertTrue(begun.wait(3))
            server.shutdown()
            serving.join(timeout=3)
            closing.start()
            self.assertTrue(closed.wait(1), 'idle body reader blocked close')
            replacement = make_server(self.root, data, 0)
            connection.sendall(payload[1:])
            response = connection.recv(4096)
            self.assertIn(b'409', response.split(b'\r\n', 1)[0])
            self.assertFalse((data / 'comments.json').exists())
        finally:
            connection.close()
            if closing.ident is not None:
                closing.join(timeout=3)
            server.shutdown()
            server.server_close()
            serving.join(timeout=3)
            if replacement is not None:
                replacement.server_close()
