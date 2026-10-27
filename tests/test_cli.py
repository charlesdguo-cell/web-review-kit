import json
from pathlib import Path
import socket
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from project_config import load_project_config
from server import make_server

CLI = Path(__file__).resolve().parents[1] / 'web-review.py'


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / '独立 project'
        (self.project / 'site').mkdir(parents=True)
        (self.project / 'site/index.html').write_text('<html><head></head><body>Synthetic</body></html>')
        (self.project / 'business.txt').write_bytes(b'preserve business')
        self.servers = []

    def tearDown(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join()
        self.temp.cleanup()

    def cli(self, *args, project=None):
        result = subprocess.run([sys.executable, str(CLI), '--project', str(project or self.project), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8)
        return result.returncode, json.loads(result.stdout)

    def setup(self, *extra, project=None, port=8799):
        return self.cli('setup', '--web-root', 'site', '--data-dir', 'reviews', '--jobs-dir', '.review/jobs',
                        '--port', str(port), *extra, project=project)

    def start(self, config, tasks=None):
        server = make_server(config.web_root, config.data_dir, config.server['port'],
                             config.server['basePath'], config.server['publicOrigins'],
                             config.server['host'], tasks, project_config=config)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        return server

    def free_port(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            return sock.getsockname()[1]

    def test_setup_repeated_preserves_pin_identity_and_business(self):
        before = (self.project / 'business.txt').read_bytes()
        code, first = self.setup()
        self.assertEqual(code, 0, first)
        path = self.project / 'review.config.json'
        original = path.read_bytes()
        code, second = self.setup()
        self.assertEqual(code, 0, second)
        self.assertEqual(first['projectId'], second['projectId'])
        self.assertEqual(path.read_bytes(), original)
        raw = json.loads(original)
        self.assertEqual(raw['webRoot'], 'site')
        self.assertEqual(raw['server']['port'], 8799)
        self.assertNotIn('model', raw['codex'])
        self.assertEqual((self.project / 'business.txt').read_bytes(), before)
        self.assertFalse((self.project / 'reviews').exists())
        self.assertFalse((self.project / '.review').exists())
        raw['toolVersion'] = 'older-pinned-version'
        path.write_text(json.dumps(raw))
        pinned = path.read_bytes()
        self.assertEqual(self.setup()[0], 0)
        self.assertEqual(path.read_bytes(), pinned)

    def test_setup_conflict_returns_diff_without_overwrite(self):
        self.assertEqual(self.setup()[0], 0)
        path = self.project / 'review.config.json'
        before = path.read_bytes()
        code, result = self.setup(port=8800)
        self.assertEqual(code, 3)
        self.assertFalse(result['ok'])
        self.assertIn('server.port', result['diff'])
        self.assertEqual(path.read_bytes(), before)

    def test_setup_distinguishes_path_lookup_and_explicit_executable(self):
        path = self.project / 'review.config.json'
        for existing, requested in [('codex', './codex'), ('./codex', 'codex')]:
            with self.subTest(existing=existing, requested=requested):
                if path.exists():
                    path.unlink()
                self.assertEqual(self.setup('--codex-bin', existing)[0], 0)
                before = path.read_bytes()
                code, result = self.setup('--codex-bin', requested)
                self.assertEqual(code, 3)
                self.assertEqual(result['error'], 'configuration_conflict')
                self.assertEqual(result['diff']['codex.executable'],
                                 {'existing': existing, 'requested': requested})
                self.assertEqual(path.read_bytes(), before)

    def test_setup_reuses_equivalent_explicit_executable_paths(self):
        self.assertEqual(self.setup('--codex-bin', './bin/../codex')[0], 0)
        path = self.project / 'review.config.json'
        before = path.read_bytes()
        self.assertEqual(self.setup('--codex-bin', str(self.project / 'codex'))[0], 0)
        self.assertEqual(path.read_bytes(), before)

    def test_unknown_version_and_invalid_cli_return_json_2(self):
        self.setup()
        path = self.project / 'review.config.json'
        raw = json.loads(path.read_text())
        raw['configVersion'] = 55
        path.write_text(json.dumps(raw))
        self.assertEqual(self.cli('serve')[0], 2)
        self.assertEqual(self.cli('setup', '--unknown-option')[0], 2)

    def test_version_without_config(self):
        code, result = self.cli('version')
        self.assertEqual(code, 0)
        self.assertTrue(result['toolVersion'])
        self.assertIn('projectId', result)

    def test_explicit_review_url_keeps_frozen_endpoint_and_checks_identity(self):
        port = self.free_port()
        self.setup(port=port)
        config = load_project_config(self.project)
        self.start(config)
        path = self.project / 'review.config.json'
        raw = json.loads(path.read_text())
        raw['server']['port'] = self.free_port()
        path.write_text(json.dumps(raw))
        url = 'http://127.0.0.1:' + str(port)
        code, result = self.cli('--review-url', url, 'list')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['comments'], [])
        raw['projectId'] = 'wrong-project'
        path.write_text(json.dumps(raw))
        code, result = self.cli('--review-url', url, 'list')
        self.assertEqual((code, result['error']), (3, 'project_conflict'))

    def test_explicit_review_url_is_not_a_service_or_setup_override(self):
        self.setup()
        for command in ('serve', 'setup', 'doctor', 'version'):
            with self.subTest(command=command):
                code, result = self.cli('--review-url', 'http://127.0.0.1:1', command)
                self.assertEqual((code, result['error']), (2, 'invalid_arguments'))

    def test_setup_shared_and_codex_permissions(self):
        code, _ = self.setup('--host', '0.0.0.0', '--base-path', '/team/review',
                             '--public-origin', 'https://reviews.example.test')
        self.assertEqual(code, 0)
        config = load_project_config(self.project)
        self.assertFalse(config.codex['enabled'])
        self.assertEqual(config.codex['approvalPolicy'], 'never')
        self.assertEqual(config.codex['sandbox'], 'danger-full-access')

    def test_reuse_requires_identity_directories_port_and_executor(self):
        port = self.free_port()
        self.setup(port=port)
        config = load_project_config(self.project)
        self.start(config)
        self.assertEqual(self.cli('serve')[0], 0)
        path = self.project / 'review.config.json'
        original = json.loads(path.read_text())
        for key, value in [('projectId', 'different-project'), ('dataDir', 'different-reviews'),
                           ('jobsDir', 'different-jobs')]:
            raw = {**original, key: value}
            path.write_text(json.dumps(raw))
            self.assertEqual(self.cli('serve')[0], 3)
        raw = json.loads(json.dumps(original))
        raw['codex']['enabled'] = True
        path.write_text(json.dumps(raw))
        self.assertEqual(self.cli('serve')[0], 3)
        # A second independent project on the occupied port cannot reuse it.
        second = Path(self.temp.name) / 'other'
        (second / 'site').mkdir(parents=True)
        self.setup(project=second, port=port)
        self.assertEqual(self.cli('serve', project=second)[0], 3)
        with urlopen(f'http://127.0.0.1:{port}/__review/health') as response:
            self.assertEqual(json.load(response)['projectId'], config.project_id)

    def test_health_legacy_local_shared(self):
        port = self.free_port()
        self.setup(port=port)
        config = load_project_config(self.project)
        self.start(config)
        with urlopen(f'http://127.0.0.1:{port}/__review/health') as response:
            health = json.load(response)
        self.assertEqual(health['projectId'], config.project_id)
        self.assertEqual(health['toolVersion'], config.tool_version)
        self.assertEqual(health['schemaVersion'], 1)
        self.assertEqual(health['root'], str(config.web_root))
        self.assertEqual(health['data'], str(config.data_dir))
        # Existing standalone make_server has its original exact health shape.
        legacy_data = (self.project / 'legacy-reviews').resolve()
        legacy = make_server(config.web_root, legacy_data, 0)
        worker = threading.Thread(target=legacy.serve_forever, daemon=True)
        worker.start()
        self.servers.append((legacy, worker))
        with urlopen(f'http://127.0.0.1:{legacy.server_port}/__review/health') as response:
            self.assertEqual(json.load(response), {'service': 'prototype-review', 'root': str(config.web_root),
                                                  'data': str(legacy_data)})
        path = self.project / 'review.config.json'
        raw = json.loads(path.read_text())
        raw['server'].update(port=self.free_port(), basePath='/team', publicOrigins=['https://reviews.example.test'])
        raw['dataDir'] = 'shared-reviews'
        path.write_text(json.dumps(raw))
        shared = load_project_config(self.project)
        self.start(shared)
        request = Request(f'http://127.0.0.1:{shared.server["port"]}/team/__review/health',
                          headers={'Host': 'reviews.example.test'})
        with urlopen(request) as response:
            result = json.load(response)
        self.assertEqual(result['projectId'], config.project_id)
        self.assertNotIn(str(self.project), json.dumps(result))
        for key in ('root', 'data', 'projectRoot', 'jobsDir'):
            self.assertNotIn(key, result)

    def test_serve_launches_configured_external_project(self):
        port = self.free_port()
        self.assertEqual(self.setup(port=port)[0], 0)
        process = subprocess.Popen([sys.executable, str(CLI), '--project', str(self.project), 'serve'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output = queue.Queue()
        reader = threading.Thread(target=lambda: output.put(process.stdout.readline()), daemon=True)
        reader.start()
        try:
            ready = json.loads(output.get(timeout=5))
            self.assertTrue(ready['ok'])
            self.assertFalse(ready['reused'])
            with urlopen(f'http://127.0.0.1:{port}/index.html') as response:
                self.assertIn('Synthetic', response.read().decode())
            self.assertFalse((self.project / '.review/jobs').exists())
        finally:
            process.terminate()
            process.wait(timeout=5)
            reader.join(timeout=2)
            process.stdout.close()
            process.stderr.close()

    def test_wrong_runtime_port_or_executor_cannot_claim_configuration(self):
        port = self.free_port()
        self.setup(port=port)
        config = load_project_config(self.project)
        with self.assertRaises(ValueError):
            make_server(config.web_root, config.data_dir, 0, project_config=config)
        with self.assertRaises(ValueError):
            make_server(config.web_root, config.data_dir, port, codex_tasks=object(), project_config=config)

    def test_occupied_unrelated_port_is_conflict_without_termination(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.setup(port=port)
            self.assertEqual(self.cli('serve')[0], 3)
            self.assertEqual(listener.getsockname()[1], port)


if __name__ == '__main__':
    unittest.main()
