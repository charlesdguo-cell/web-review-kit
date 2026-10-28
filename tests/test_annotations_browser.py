"""Annotation UI integration: temporary pages, fake protocol executable, isolated Chrome."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from codex_tasks import CodexTasks
from project_config import TOOL_VERSION, load_project_config
from server import make_server


ROOT = Path(__file__).resolve().parents[1]
PAGE = '''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Annotation protocol fixture</title>
<style>body{margin:64px;font:22px/1.7 sans-serif;background:#f8f8fb;color:#192237}
main{max-width:700px}p{margin:22px 0}#multiline{width:280px}input{font:inherit}</style>
</head><body><main><h1>合成批注演示 · 协议替身回复</h1>
<p id="cross">Normal <strong>reading across</strong> inline text preserves the quote.</p>
<p id="multiline">Multiple lines provide a durable selection after resize and refresh.</p>
<p id="reverse">Reverse selection keeps its original text and context.</p>
<p id="stale">A unique original quote will later change.</p>
<p id="duplicate">Repeated quote. Repeated quote.</p>
<input id="ordinary-input" value="Editable fields stay ordinary">
<p id="editable" contenteditable="true">Editable text stays ordinary</p>
<button id="page-action" onclick="window.pageActions++">Ordinary page action</button>
</main><script>window.pageActions=0;</script></body></html>'''


def run_browser_check(runner="verify-annotations.rb", page=PAGE, behavior="slow", page_identity=None):
    """Run an isolated synthetic browser script; never use retained consumer data."""
    with tempfile.TemporaryDirectory(prefix='annotation-browser-') as directory:
        fixture = Path(directory)
        pages, data = fixture / 'pages', fixture / 'data'
        pages.mkdir()
        data.mkdir()
        (pages / 'index.html').write_text(page)
        (pages / 'other.html').write_text(page)
        legacy = {'id': 'fixture-legacy', 'number': 1, 'text': 'Legacy review remains independent',
                  'status': 'open', 'createdAt': '1', 'updatedAt': '1',
                  'page': {'path': '/', 'title': 'Synthetic'},
                  'anchor': {'selector': 'h1', 'label': 'Synthetic'}, 'attachments': []}
        (data / 'comments.json').write_text(json.dumps([legacy]))
        executable = fixture / 'fake-codex'
        executable.write_text((ROOT / 'tests/codex_app_server_fixture.py').read_text())
        executable.chmod(0o755)
        tasks = CodexTasks(fixture, data, fixture / 'jobs', str(executable))
        (fixture / 'behavior').write_text(behavior)
        offline = fixture / 'offline'
        offline.mkdir()
        assets = offline / 'review-assets'
        assets.mkdir()
        for name in ('review.js', 'review.css', 'html2canvas.min.js'):
            shutil.copyfile(ROOT / 'runtime' / name, assets / name)
        (offline / 'index.html').write_text(page.replace('</head>',
            '<script src="review-assets/review.js" data-prototype-review></script></head>'))
        shared_data = fixture / 'shared-data'
        shared_data.mkdir()
        config, local_port = None, 0
        if page_identity is not None:
            # The optional identity test uses the real validated configuration
            # path. All existing callers retain their standalone fixture server.
            with socket.socket() as available:
                available.bind(('127.0.0.1', 0))
                local_port = available.getsockname()[1]
            raw = {'configVersion': 1, 'projectId': 'annotation-identity-fixture',
                   'toolVersion': TOOL_VERSION, 'webRoot': 'pages', 'dataDir': 'data', 'jobsDir': 'jobs',
                   'server': {'host': '127.0.0.1', 'port': local_port, 'basePath': '', 'publicOrigins': []},
                   'pageIdentity': page_identity, 'browserStorage': {},
                   'guidance': {'requiredFiles': [], 'sourceRoots': [], 'buildCommands': [], 'checkCommands': []},
                   'codex': {'enabled': True, 'executable': str(executable),
                             'approvalPolicy': 'never', 'sandbox': 'danger-full-access'}}
            (fixture / 'review.config.json').write_text(json.dumps(raw))
            config = load_project_config(fixture)
        servers = [make_server(pages, data, local_port, codex_tasks=tasks, project_config=config),
                   make_server(pages, shared_data, 0, base_path='/team/review',
                               public_origins=['https://annotations.example.test']),
                   make_server(pages, fixture / 'disabled-data', 0)]
        workers = []
        for server in servers:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            workers.append(worker)
        try:
            result = subprocess.run(['ruby', str(ROOT / 'tests/browser' / runner)],
                cwd=ROOT, env=dict(os.environ,
                    ANNOTATIONS_TEST_URL='http://127.0.0.1:{}/'.format(servers[0].server_port),
                    ANNOTATIONS_SHARED_URL='http://127.0.0.1:{}/team/review/'.format(servers[1].server_port),
                    ANNOTATIONS_DISABLED_URL='http://127.0.0.1:{}/'.format(servers[2].server_port),
                    ANNOTATIONS_OFFLINE_URL=(offline / 'index.html').as_uri(),
                    ANNOTATIONS_FIXTURE=str(fixture)))
            if result.returncode:
                raise AssertionError('Annotation browser check exited {}'.format(result.returncode))
        finally:
            # Only stop fixture-owned conversations; never inspect or touch real jobs.
            annotations = data / 'annotations.json'
            if annotations.exists():
                for annotation in json.loads(annotations.read_text()):
                    conversation = tasks.annotation_status(annotation['id'])
                    if conversation and conversation.get('status') in ('starting', 'running', 'stopping'):
                        tasks.annotation_stop(annotation['id'])
                deadline = time.monotonic() + 5
                while any(process.poll() is None for process in tasks.workers) and time.monotonic() < deadline:
                    time.sleep(.05)
            for server in servers:
                server.shutdown()
                server.server_close()
            for worker in workers:
                worker.join()


class AnnotationBrowserTests(unittest.TestCase):
    def test_synthetic_annotation_protocol_browser(self):
        run_browser_check()


if __name__ == '__main__':
    unittest.main()
