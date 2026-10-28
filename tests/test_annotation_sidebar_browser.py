"""Aligned annotation sidebar on synthetic documents with a protocol substitute."""
import unittest

from test_annotations_browser import run_browser_check


SIDEBAR_PAGE = '''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sidebar synthetic reading document</title>
<style>html{scroll-behavior:auto}body{margin:0;font:18px/1.7 system-ui;background:#fafaf8;color:#202a35}
main{max-width:780px;padding:64px 56px;margin:0 auto}h1{font-size:30px;margin:0 0 46px}
p{margin:0 0 14px}section{margin:0}#distant{margin-top:760px}#far{margin-top:1100px}
#tail{height:1500px}button{font:inherit}</style></head>
<body style="padding-right: 7px; --fixture-token: retained"><main>
<h1>Reading and annotations</h1>
<p id="first">First original sentence has a stable quotation for sidebar alignment.</p>
<p id="adjacent">Adjacent original sentence demonstrates collision avoidance.</p>
<p id="overlap">Overlapping quotations remain separate conversations in document order.</p>
<p id="resolved">Resolved original sentence remains discoverable through the filter.</p>
<button id="ordinary" onclick="window.pageActions++">Ordinary page button</button>
<section id="distant"><h2>Distant section</h2><p id="middle">Middle original sentence stays attached during native document scrolling.</p></section>
<section id="far"><h2>Far section</h2><p id="last">Last original sentence can be found even outside the current viewport.</p></section>
<div id="tail"></div></main><script>window.pageActions=0</script></body></html>'''


class AnnotationSidebarBrowserTests(unittest.TestCase):
    def test_synthetic_aligned_sidebar(self):
        run_browser_check("verify-annotation-sidebar.rb", SIDEBAR_PAGE, "ok")


if __name__ == '__main__':
    unittest.main()
