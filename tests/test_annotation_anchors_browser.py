"""Conservative annotation anchors on synthetic pages, with no real Agent tasks."""
import unittest

from test_annotations_browser import run_browser_check


ANCHOR_PAGE = '''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Annotation anchor fixture</title>
<style>html{scroll-behavior:auto}body{margin:0;font:18px/1.7 system-ui;background:#fafaf8;color:#202a35}
main{max-width:780px;padding:64px 56px;margin:0 auto}h1{font-size:30px;margin:0 0 38px}
p,section{margin:0 0 18px}#tail{height:2200px}</style></head><body><main>
<h1>Retained annotation discussions</h1>
<p id="stable">Stable original quotation for an explicit identity.</p>
<section class="reading"><p>Stable surrounding introduction remains in this section.</p><p>Original section sentence.</p><p>Stable surrounding conclusion remains in this section.</p></section>
<section class="leading-context">
      <h2>Original leading quote.</h2>
      <p>A sufficiently distinctive following paragraph preserves this section identity.</p>
      </section>
<p id="deleted">Deleted original paragraph has a preserved discussion.</p>
<section class="replacement">Original replacement container has distinctive surrounding context.</section>
<div class="positioned"><p>Original positional quotation.</p><p>Unrelated next paragraph stays in place.</p></div>
<p id="exact">Exact quotation remains linked to its original text.</p>
<div id="tail"></div></main></body></html>'''


class AnnotationAnchorBrowserTests(unittest.TestCase):
    def test_synthetic_retained_annotation_anchors(self):
        run_browser_check("verify-annotation-anchors.rb", ANCHOR_PAGE, "ok")


if __name__ == '__main__':
    unittest.main()
