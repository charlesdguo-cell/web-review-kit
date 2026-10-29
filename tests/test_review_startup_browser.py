"""Review startup uses only synthetic pages and an isolated headless browser."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
PAGE = '''<!doctype html><html><head><meta charset="utf-8">
<script src="review.js" data-prototype-review></script>
<style>body{margin:60px;background:#f8f8fb;color:#192237;font:20px sans-serif}
button{padding:12px}p{max-width:600px}</style></head><body>
<h1>Synthetic review startup</h1><p id="quote">A synthetic quotation remains available for annotations.</p>
<button id="ordinary">Ordinary action</button><input id="page-input" value="Page input"><script>
window.pageActions=0;window.capturedClicks=0;
document.querySelector('#ordinary').onclick=()=>window.pageActions++;
window.addEventListener('click',()=>window.capturedClicks++,true);
</script></body></html>'''


class ReviewStartupBrowserTests(unittest.TestCase):
    def test_stylesheet_loading_visibility_and_existing_interactions(self):
        with tempfile.TemporaryDirectory(prefix='review-startup-') as directory:
            fixture = Path(directory)
            requests = {}

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    path = urlsplit(self.path).path
                    requests[path] = requests.get(path, 0) + 1
                    if path == '/requests':
                        body, content_type = json.dumps(requests).encode(), 'application/json'
                    elif path.endswith('.html'):
                        body, content_type = PAGE.encode(), 'text/html; charset=utf-8'
                    elif path.endswith('/review.js'):
                        body, content_type = (ROOT / 'runtime/review.js').read_bytes(), 'text/javascript'
                    elif path.endswith('/review.css'):
                        if path.startswith('/missing/') or (fixture / 'fail-style').exists():
                            self.send_error(503, 'Synthetic stylesheet failure')
                            return
                        if path.startswith('/delayed/'):
                            deadline = time.monotonic() + 15
                            while not (fixture / 'release-style').exists() and time.monotonic() < deadline:
                                time.sleep(.02)
                        body, content_type = (ROOT / 'runtime/review.css').read_bytes(), 'text/css'
                    else:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'public, max-age=3600' if path.startswith('/cached/') else 'no-store')
                    self.end_headers()
                    self.wfile.write(body)

            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                result = subprocess.run(['ruby', str(ROOT / 'tests/browser/verify-review-startup.rb')],
                    cwd=ROOT, env=dict(os.environ,
                        REVIEW_STARTUP_URL='http://127.0.0.1:{}/'.format(server.server_port),
                        REVIEW_STARTUP_FIXTURE=str(fixture)))
                self.assertEqual(result.returncode, 0, 'Review startup browser check failed')
            finally:
                (fixture / 'release-style').touch()
                server.shutdown()
                server.server_close()
                worker.join()


if __name__ == '__main__':
    unittest.main()
