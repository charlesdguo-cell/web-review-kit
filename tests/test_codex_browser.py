"""Browser integration uses a fake CLI and isolated review data, never the user's Codex account."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from codex_tasks import CodexTasks
from server import make_server
from test_codex_tasks import FAKE_CODEX

ROOT=Path(__file__).resolve().parents[1]
def run_browser_check():
    with tempfile.TemporaryDirectory(prefix='codex-browser-') as directory:
        root=Path(directory)
        (root/'data').mkdir();(root/'pages').mkdir()
        (root/'pages/index.html').write_text('<html><head><title>评论任务测试</title></head><body><h1 id="message">评论联通验证</h1><script>window.activated=0;document.querySelector("h1").onclick=()=>activated++</script></body></html>')
        comments=[{'id':f'fixture-comment-{i:03}','number':i,'status':'open' if i==1 else 'changed','text':'其他页面的旧待处理评论' if i==1 else '已处理的最新评论','createdAt':str(i),'updatedAt':str(i),'page':{'path':'/other.html' if i==1 else '/','title':'评论任务测试'},'anchor':{'selector':'h1','label':'评论联通验证'},'attachments':[]} for i in [1,2]]
        (root/'data/comments.json').write_text(json.dumps(comments))
        executable=root/'fake-codex';executable.write_text(FAKE_CODEX);executable.chmod(0o755)
        tasks=CodexTasks(root,root/'data',root/'jobs',str(executable))
        for number in range(25):
            saved=root/'jobs'/('history%03d'%number);saved.mkdir()
            (saved/'status.json').write_text(json.dumps({'id':saved.name,'status':'completed',
                'startedAt':number+1,'comments':[{'number':91+number,'text':'Saved history comment'}],
                'result':'Legacy batch result <script>window.historyInjected=true</script>' if number==0 else 'Saved batch result'}))
        server=make_server(root/'pages',root/'data',0,codex_tasks=tasks)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            result=subprocess.run(['ruby',str(ROOT/'tests/browser/verify-codex.rb')],cwd=ROOT,env=dict(os.environ,PROTOTYPE_CODEX_TEST_URL=f'http://127.0.0.1:{server.server_port}/',PROTOTYPE_CODEX_FIXTURE=str(root)))
            if result.returncode:raise SystemExit(result.returncode)
        finally:
            job=tasks.current()
            if job and job['status'] in ('starting','running','stopping'):
                tasks.stop(job['id'])
                for _ in range(80):
                    if tasks.current()['status'] not in ('starting','running','stopping'):break
                    time.sleep(.1)
            server.shutdown();server.server_close();worker.join()


if __name__ == "__main__":
    run_browser_check()
else:
    import unittest

    class CodexBrowserTests(unittest.TestCase):
        def test_browser_protocol_fixture(self):
            run_browser_check()
