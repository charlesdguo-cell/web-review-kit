"""Refresh preservation on synthetic pages; no real Codex executable or jobs."""
import unittest

from test_annotations_browser import run_browser_check


REFRESH_PAGE = '''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Refresh synthetic document</title>
<style>html{scroll-behavior:auto}body{margin:0;font:18px/1.7 system-ui;background:#fafaf8;color:#202a35}
main{max-width:720px;padding:70px 50px;margin:auto}h1{font-size:30px}#spacer{height:650px}
p{margin:20px 0}#tail{height:1700px}input{font:inherit}</style></head><body><main>
<h1>Persistent annotation reading</h1><input id="ordinary-input" value="Original field value">
<p id="top">A separate original sentence provides a resolved conversation.</p><div id="spacer"></div>
<p id="target">The selected original sentence retains its paragraph identity.</p>
<p id="other-target">A second nearby sentence stays unchanged during the build.</p>
<div id="tail"></div></main><script>
window.refreshFixtureLoad=Number(sessionStorage.getItem('refresh-fixture-loads')||0)+1;
sessionStorage.setItem('refresh-fixture-loads',String(window.refreshFixtureLoad));
</script></body></html>'''


class AnnotationRefreshBrowserTests(unittest.TestCase):
    def test_synthetic_refresh_preservation(self):
        run_browser_check("verify-annotation-refresh.rb", REFRESH_PAGE, "ok")

    def test_synthetic_same_document_identity(self):
        run_browser_check("verify-annotation-refresh-identity.rb", REFRESH_PAGE, "ok",
                          page_identity={'queryKeys': ['section'], 'includeHash': True})


if __name__ == '__main__':
    unittest.main()
