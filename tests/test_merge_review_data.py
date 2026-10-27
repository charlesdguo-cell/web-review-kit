"""Attachment imports use temporary directories and never touch real review data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('merge_review_data', Path(__file__).resolve().parents[1] / 'runtime/merge_review_data.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AttachmentImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source'
        self.target = Path(self.temp.name) / 'target'
        self.image = b'\x89PNG\r\n\x1a\nfixture'
        identity = 'test-comment-001'
        self.relative = Path('attachments') / identity / (hashlib.sha256(self.image).hexdigest() + '.png')
        self.attachment = self.source / self.relative
        self.attachment.parent.mkdir(parents=True)
        self.attachment.write_bytes(self.image)
        snapshot = self.source / 'screenshots' / (identity + '.png')
        snapshot.parent.mkdir()
        snapshot.write_bytes(self.image)
        self.comment = {'id': identity, 'number': 1, 'text': '', 'attachments': [{'id': 'test-image-001', 'url': '/__review/' + self.relative.as_posix()}]}
        self.write_source()

    def write_source(self):
        (self.source / 'comments.json').write_text(json.dumps([self.comment]))

    def test_import_copies_images_and_preserves_existing_server_version(self):
        result = module.merge(self.source, self.target)
        self.assertEqual(result['imported'], [self.comment['id']])
        self.assertEqual((self.target / self.relative).read_bytes(), self.image)
        original = (self.target / 'comments.json').read_bytes()
        self.comment.update(text='Old local version', attachments=[])
        self.write_source()
        result = module.merge(self.source, self.target)
        self.assertEqual(result['keptServerVersion'], [self.comment['id']])
        self.assertEqual((self.target / 'comments.json').read_bytes(), original)

    def test_missing_or_modified_image_aborts_before_any_write(self):
        self.attachment.unlink()
        with self.assertRaises(FileNotFoundError):
            module.merge(self.source, self.target)
        self.assertFalse(self.target.exists())
        self.attachment.write_bytes(b'changed')
        with self.assertRaisesRegex(AssertionError, 'content differs'):
            module.merge(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_foreign_comment_attachment_is_rejected(self):
        self.comment['attachments'][0]['url'] = self.comment['attachments'][0]['url'].replace('test-comment-001', 'other-comment-001')
        self.write_source()
        with self.assertRaisesRegex(AssertionError, 'Invalid attachment path'):
            module.merge(self.source, self.target)
        self.assertFalse(self.target.exists())


if __name__ == '__main__':
    unittest.main()
