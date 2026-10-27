import copy
import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import make_server


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'pages'
        self.root.mkdir()
        (self.root / 'brand-new.html').write_text('<html><head></head><body>New page</body></html>')
        self.data = Path(self.temp.name) / 'reviews'
        self.server = make_server(self.root, self.data, 0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.comment = {'id': 'sample-review-001', 'text': '调整按钮文案', 'status': 'open', 'page': {'path': '/brand-new.html'},
                        'anchor': {'selector': '#button'}, 'screenshotData': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg=='}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.temp.cleanup()

    def post(self, comment, expected=None, origin=None):
        request = Request(self.base + '/__review/comments', data=json.dumps({'comment': comment, 'expectedUpdate': expected}).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': origin or self.base})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_new_page_inherits_overlay(self):
        html = urlopen(self.base + '/brand-new.html').read().decode()
        self.assertEqual(html.count('data-prototype-review'), 1)
        self.assertLess(html.index('review.js'), html.index('<body>'))

    def test_page_asset_connection_burst(self):
        payload = b'// Page asset\n' * 4096
        (self.root / 'asset.js').write_bytes(payload)
        barrier = threading.Barrier(64)

        def fetch(_):
            barrier.wait(timeout=10)
            with urlopen(self.base + '/asset.js', timeout=8) as response:
                return response.status, response.read()

        with ThreadPoolExecutor(max_workers=64) as pool:
            responses = list(pool.map(fetch, range(64)))
        for index, (status, body) in enumerate(responses):
            with self.subTest(request=index):
                self.assertEqual(status, 200)
                self.assertEqual(body, payload)

    def test_media_byte_ranges_allow_seeking(self):
        media = bytes(range(256)) * 4
        (self.root / 'sample.wav').write_bytes(media)
        for requested, start, end in [('bytes=0-', 0, 1023), ('bytes=100-199', 100, 199),
                                       ('bytes=1000-9999', 1000, 1023), ('bytes=-20', 1004, 1023),
                                       ('bytes=-9999', 0, 1023)]:
            with self.subTest(requested=requested):
                with urlopen(Request(self.base + '/sample.wav', headers={'Range': requested})) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.headers['Accept-Ranges'], 'bytes')
                    self.assertEqual(response.headers['Content-Range'], f'bytes {start}-{end}/1024')
                    self.assertEqual(int(response.headers['Content-Length']), end - start + 1)
                    self.assertEqual(response.read(), media[start:end + 1])

    def test_unsatisfiable_media_range_returns_size(self):
        (self.root / 'sample.wav').write_bytes(b'1234567890')
        for requested in ['bytes=10-', 'bytes=8-2', 'bytes=-0']:
            with self.subTest(requested=requested), self.assertRaises(HTTPError) as raised:
                urlopen(Request(self.base + '/sample.wav', headers={'Range': requested}))
            self.assertEqual(raised.exception.code, 416)
            self.assertEqual(raised.exception.headers['Content-Range'], 'bytes */10')
        (self.root / 'empty.wav').write_bytes(b'')
        with self.assertRaises(HTTPError) as raised:
            urlopen(Request(self.base + '/empty.wav', headers={'Range': 'bytes=0-'}))
        self.assertEqual(raised.exception.code, 416)

    def test_range_fallback_and_head_preserve_full_response(self):
        (self.root / 'sample.wav').write_bytes(b'1234567890')
        for headers in [{}, {'Range': 'bytes=bad'}, {'Range': 'bytes=0-1,4-5'},
                        {'Range': 'bytes=2-', 'If-Range': '"unknown-version"'}]:
            with self.subTest(headers=headers):
                with urlopen(Request(self.base + '/sample.wav', headers=headers)) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers['Content-Length'], '10')
                    self.assertEqual(response.read(), b'1234567890')
        with urlopen(Request(self.base + '/sample.wav', method='HEAD', headers={'Range': 'bytes=2-'})) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['Accept-Ranges'], 'bytes')
            self.assertEqual(response.headers['Content-Length'], '10')
            self.assertEqual(response.read(), b'')

    def test_atomic_save_and_idempotent_retry(self):
        status, saved = self.post(self.comment)
        self.assertEqual(status, 200)
        status, retried = self.post(self.comment)
        self.assertEqual(status, 200)
        self.assertEqual(saved, retried)
        items = json.loads((self.data / 'comments.json').read_text())
        self.assertEqual(len(items), 1)
        self.assertTrue((self.data / 'screenshots' / 'sample-review-001.png').read_bytes().startswith(b'\x89PNG'))

    def test_edit_conflict_keeps_latest_content(self):
        _, saved = self.post(self.comment)
        original = saved['comment']
        changed = {**original, 'status': 'changed', 'resolution': '已调整按钮文案，请验收'}
        status, latest = self.post(changed, original['updatedAt'])
        self.assertEqual(status, 200)
        self.assertEqual(latest['comment']['screenshot'], original['screenshot'])
        status, _ = self.post({**original, 'text': '旧页面的修改'}, original['updatedAt'])
        self.assertEqual(status, 409)
        self.assertEqual(json.loads((self.data / 'comments.json').read_text())[0]['resolution'], changed['resolution'])

    def test_closed_log_output_does_not_interrupt_save_response(self):
        for index, error in enumerate([BrokenPipeError('launcher pipe closed'), ValueError('closed stream')]):
            with self.subTest(error=type(error).__name__):
                comment = {**self.comment, 'id': f'closed-log-{index:03}'}
                with patch.object(BaseHTTPRequestHandler, 'log_message', side_effect=error):
                    status, saved = self.post(comment)
                    self.assertEqual(status, 200)
                    edited = {**saved['comment'], 'text': '日志不可用时仍能保存修改'}
                    status, updated = self.post(edited, edited['updatedAt'])
                    self.assertEqual(status, 200)
                    self.assertEqual(updated['comment']['text'], edited['text'])
                self.assertEqual(json.loads((self.data / 'comments.json').read_text())[-1]['text'], edited['text'])

    def test_lost_edit_response_can_retry_without_overwriting_other_changes(self):
        _, saved = self.post(self.comment)
        original = saved['comment']
        edited = {**original, 'text': '响应丢失前已经保存的修改'}
        status, updated = self.post(edited, original['updatedAt'])
        self.assertEqual(status, 200)
        before_retry = (self.data / 'comments.json').read_bytes()
        status, retried = self.post(edited, original['updatedAt'])
        self.assertEqual(status, 200)
        self.assertEqual(retried, updated)
        self.assertEqual((self.data / 'comments.json').read_bytes(), before_retry)
        self.assertEqual(retried['comment']['screenshot'], original['screenshot'])

        latest = updated['comment']
        status, resolved = self.post({**latest, 'status': 'resolved'}, latest['updatedAt'])
        self.assertEqual(status, 200)
        status, _ = self.post(edited, original['updatedAt'])
        self.assertEqual(status, 409)
        current = json.loads((self.data / 'comments.json').read_text())[0]
        self.assertEqual(current['status'], 'resolved')
        self.assertEqual(current['updatedAt'], resolved['comment']['updatedAt'])

    def test_invalid_screenshot_does_not_create_record(self):
        status, _ = self.post({**self.comment, 'screenshotData': 'data:image/png;base64,aGVsbG8='})
        self.assertEqual(status, 400)
        self.assertFalse((self.data / 'comments.json').exists())

    def image_comment(self):
        return {**self.comment, 'text': '', 'attachments': [{'id': 'attached-image-001', 'name': '参考图.png', 'dataUrl': self.comment['screenshotData']}]}

    def test_image_only_comment_persists_and_downloads_separately(self):
        status, response = self.post(self.image_comment())
        self.assertEqual(status, 200)
        saved = response['comment']
        image = saved['attachments'][0]
        self.assertNotIn('dataUrl', image)
        self.assertEqual(image['mimeType'], 'image/png')
        image_url = f'http://127.0.0.1:{self.server.server_port}' + image['url']
        with urlopen(image_url) as result:
            self.assertEqual(result.headers['Content-Type'], 'image/png')
            self.assertEqual(result.read(), base64.b64decode(self.comment['screenshotData'].split(',')[1]))
        original = self.data / 'screenshots' / (saved['id'] + '.png')
        self.assertTrue(original.is_file())
        self.assertNotEqual(image['url'], saved['screenshot'])

    def test_attachment_edit_cancel_retry_and_legacy_client_preservation(self):
        request = self.image_comment()
        _, saved = self.post(request)
        status, retried = self.post(request)
        self.assertEqual(status, 200)
        self.assertEqual(saved, retried)
        original = (self.data / 'screenshots' / (self.comment['id'] + '.png')).read_bytes()
        legacy = {k: v for k, v in saved['comment'].items() if k != 'attachments'}
        legacy['status'] = 'changed'
        status, updated = self.post(legacy, legacy['updatedAt'])
        self.assertEqual(status, 200)
        self.assertEqual(updated['comment']['attachments'], saved['comment']['attachments'])
        previous = updated['comment']
        removed = {**previous, 'text': '保留文字，移除附图', 'attachments': []}
        status, latest = self.post(removed, previous['updatedAt'])
        self.assertEqual(status, 200)
        self.assertEqual(latest['comment']['attachments'], [])
        status, _ = self.post({**previous, 'text': '旧窗口的修改'}, previous['updatedAt'])
        self.assertEqual(status, 409)
        self.assertEqual((self.data / 'screenshots' / (self.comment['id'] + '.png')).read_bytes(), original)
        self.assertEqual(len(list((self.data / 'attachments').rglob('*.png'))), 1)

    def test_failed_attachment_validation_does_not_write_comments_or_images(self):
        invalid = [
            {'id': 'attached-image-001', 'name': 'script.svg', 'dataUrl': 'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4='},
            {'id': 'attached-image-001', 'dataUrl': 'data:image/png;base64,aGVsbG8='},
            {'id': '../../escape', 'dataUrl': self.comment['screenshotData']},
            {'id': 'attached-image-001', 'url': '/__review/attachments/another-comment/image.png'},
        ]
        for image in invalid:
            with self.subTest(image=image):
                status, _ = self.post({**self.comment, 'attachments': [image]})
                self.assertEqual(status, 400)
                self.assertFalse((self.data / 'comments.json').exists())
                self.assertFalse((self.data / 'attachments').exists())
                self.assertFalse((self.data / 'screenshots').exists())

    def test_attachment_limits_and_empty_comment(self):
        image = self.image_comment()['attachments'][0]
        for images in [[{**image, 'id': f'image-limit-{i:03}'} for i in range(7)], [image, image], []]:
            status, _ = self.post({**self.comment, 'text': '', 'attachments': images})
            self.assertEqual(status, 400)
        with patch('server.MAX_ATTACHMENT_BYTES', 8):
            self.assertEqual(self.post(self.image_comment())[0], 400)
        with patch('server.MAX_ATTACHMENTS_BYTES', 8):
            self.assertEqual(self.post(self.image_comment())[0], 400)
        self.assertFalse((self.data / 'comments.json').exists())

    def test_attachment_only_edits_obey_conflicts_and_idempotent_retries(self):
        _, response = self.post(self.comment)
        original = response['comment']
        edited = {**original, 'attachments': self.image_comment()['attachments']}
        status, response = self.post(edited, original['updatedAt'])
        self.assertEqual(status, 200)
        committed = (self.data / 'comments.json').read_bytes()
        status, replay = self.post(edited, original['updatedAt'])
        self.assertEqual(status, 200)
        self.assertEqual(replay, response)
        self.assertEqual((self.data / 'comments.json').read_bytes(), committed)
        conflicting = {**original, 'attachments': [{**edited['attachments'][0], 'id': 'different-image-002'}]}
        self.assertEqual(self.post(conflicting, original['updatedAt'])[0], 409)
        self.assertEqual((self.data / 'comments.json').read_bytes(), committed)

    def test_unrelated_web_page_cannot_write_reviews(self):
        status, _ = self.post(self.comment, origin='https://example.com')
        self.assertEqual(status, 403)
        self.assertFalse((self.data / 'comments.json').exists())

    def test_concurrent_reviewers_keep_all_comments_and_unique_numbers(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda n: self.post({**self.comment, 'id': f'reviewer-{n:03}'}), range(10)))
        self.assertTrue(all(status == 200 for status, _ in results))
        saved = json.loads((self.data / 'comments.json').read_text())
        self.assertEqual(sorted(c['number'] for c in saved), list(range(1, 11)))


class DeployedReviewTests(PersistenceTests):
    def setUp(self):
        super().setUp()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.prefix = '/prototype/marketing-workflow'
        self.server = make_server(self.root, self.data, 0, self.prefix, ['https://ikigen.ai', 'https://www.ikigen.ai'])
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}' + self.prefix

    def post(self, comment, expected=None, origin=None):
        request = Request(self.base + '/__review/comments', data=json.dumps({'comment': comment, 'expectedUpdate': expected}).encode(),
                          headers={'Content-Type': 'application/json', 'Host': 'ikigen.ai', 'Origin': origin or 'https://ikigen.ai'})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_deployed_html_and_screenshot_use_prefix(self):
        html = urlopen(self.base + '/brand-new.html').read().decode()
        self.assertIn('data-shared="true"', html)
        self.assertIn('src="' + self.prefix + '/__review/review.js"', html)
        _, saved = self.post(self.comment)
        self.assertTrue(saved['comment']['screenshot'].startswith(self.prefix + '/__review/screenshots/'))
        image_url = self.base.removesuffix(self.prefix) + saved['comment']['screenshot']
        self.assertTrue(urlopen(image_url).read().startswith(b'\x89PNG'))
        stored = json.loads((self.data / 'comments.json').read_text())[0]
        self.assertTrue(stored['screenshot'].startswith('/__review/'))

    def test_public_health_hides_server_paths_and_dotfiles_are_blocked(self):
        health = json.load(urlopen(self.base + '/__review/health'))
        self.assertNotIn('root', health)
        self.assertNotIn('data', health)
        (self.root / '.private').write_text('private')
        for path in ['/.private', '/../reviews/comments.json']:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + path)
            self.assertEqual(error.exception.code, 404)

    def test_unconfigured_host_and_cross_site_write_are_rejected(self):
        for host, origin in [('evil.example', 'https://evil.example'), ('ikigen.ai', 'https://www.ikigen.ai')]:
            request = Request(self.base + '/__review/comments', data=b'{}', headers={'Host': host, 'Origin': origin})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 403)


if __name__ == '__main__':
    unittest.main()
