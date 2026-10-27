"""Local TLS proxy smoke. Self-signed test certificate; no system trust changes."""
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.request

W = Path(__file__).resolve().parents[2]
RELEASE = Path('/Users/charles/.local/share/web-review-kit/releases/0.1.0-rc.3')
V = Path(os.environ['VALIDATION_PROJECT']).resolve()
assert V == Path('/Users/charles/.local/share/web-review-kit-validation')
OUT = V / 'artifacts/acceptance'
checks = []
def check(name, result):
    assert result, name
    checks.append(name)
    print('PASS ' + name, flush=True)
def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

with tempfile.TemporaryDirectory(prefix='web-review-https-') as scratch:
    root = Path(scratch)
    shutil.copytree(V / 'public', root / 'public')
    backend_port = free_port()
    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def forward(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            conn = http.client.HTTPConnection('127.0.0.1', backend_port, timeout=30)
            conn.request(self.command, self.path, body=body, headers=dict(self.headers))
            response = conn.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in ('connection', 'transfer-encoding'):
                    self.send_header(key, value)
            self.end_headers()
            data = response.read()
            if self.command != 'HEAD':
                self.wfile.write(data)
            conn.close()
        do_GET = do_HEAD = do_POST = forward
    proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
    port = proxy.server_port
    origin = 'https://127.0.0.1:' + str(port)
    base = origin + '/team/review/'
    config = json.loads((V / 'review.config.json').read_text())
    config.update(projectId='field-notes-shared-isolated', webRoot='public', dataDir='data', jobsDir='jobs')
    config['server'] = dict(host='127.0.0.1', port=backend_port, basePath='/team/review', publicOrigins=[origin])
    config['codex']['enabled'] = False
    (root / 'review.config.json').write_text(json.dumps(config))
    cert, key = root / 'cert.pem', root / 'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-keyout',str(key),'-out',str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(str(cert), str(key))
    proxy.socket = tls.wrap_socket(proxy.socket, server_side=True)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    log = (OUT / 'shared-backend.log').open('w')
    process = subprocess.Popen(['python3',str(RELEASE/'web-review.py'),'--project',str(root),'serve'],stdout=log,stderr=subprocess.STDOUT)
    context = ssl._create_unverified_context()
    def request(path, method='GET', headers=None):
        req = urllib.request.Request(base+path,method=method,headers=headers or {})
        return urllib.request.urlopen(req,context=context,timeout=20)
    try:
        # Wait on the backend before sending through the TLS proxy.
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', backend_port), timeout=.2):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise AssertionError('Shared backend failed to start')
        health = json.load(request('__review/health'))
        check('HTTPS prefix reports separate shared identity and disabled Codex',health['projectId']=='field-notes-shared-isolated' and not health['codexEnabled'])
        check('shared health hides project filesystem paths',all(key not in health for key in ('projectRoot','webRoot','dataDir','jobsDir')))
        html = request('index.html').read().decode()
        check('HTTPS HTML injects exactly one prefixed toolbar',html.count('data-prototype-review')==1 and '/team/review/__review/review.js' in html)
        assets = [('__review/review.js', RELEASE/'runtime/review.js'),('__review/review.css', RELEASE/'runtime/review.css'),('__review/html2canvas.min.js', RELEASE/'runtime/html2canvas.min.js'),('assets/tidal.svg',root/'public/assets/tidal.svg'),('assets/tone.wav',root/'public/assets/tone.wav')]
        for path, local in assets:
            check('HTTPS asset bytes '+path,request(path).read()==local.read_bytes())
        expected = (root/'public/assets/tone.wav').read_bytes()
        with request('assets/tone.wav','HEAD') as response:
            check('HTTPS HEAD returns length and empty body',response.status==200 and int(response.headers['Content-Length'])==len(expected) and response.read()==b'')
        with request('assets/tone.wav',headers={'Range':'bytes=12-35'}) as response:
            check('HTTPS media Range returns exact partial bytes',response.status==206 and response.headers['Content-Range']=='bytes 12-35/'+str(len(expected)) and response.read()==expected[12:36])
        subprocess.run(['ruby',str(W/'tests/acceptance/shared_browser.rb')],env=dict(os.environ,SHARED_ACCEPTANCE_URL=base,SHARED_ACCEPTANCE_OUT=str(OUT)),check=True,cwd=W)
        stored = json.loads((root/'data/comments.json').read_text())
        check('shared temporary record keeps original evidence and changed status',len(stored)==1 and stored[0]['status']=='changed' and len(stored[0]['attachments'])==1 and bool(stored[0]['screenshot']))
        (OUT/'shared-https-results.json').write_text(json.dumps(dict(checks=checks,url=base,temporaryOnly=True,systemTrustChanged=False,toolVersion='0.1.0-rc.3'),indent=2))
        print(str(len(checks))+' HTTPS contract checks passed',flush=True)
    finally:
        process.terminate()
        process.wait(timeout=10)
        proxy.shutdown()
        proxy.server_close()
        thread.join()
        log.close()
