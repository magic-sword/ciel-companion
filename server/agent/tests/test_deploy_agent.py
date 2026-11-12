"""Release comparison must distinguish newline changes from changed binary assets."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('deploy_agent', Path(__file__).resolve().parents[3] / 'scripts/server/deploy-agent.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class ReleaseComparisonTests(unittest.TestCase):
    def test_identical_binary_with_crlf_bytes_is_equal(self):
        data = b'RIFF\r\n\x00\xff'
        result = deploy.compare_inventory({'a.wav': data}, {'a.wav': hashlib.sha256(data).hexdigest()})
        self.assertFalse(result['different'])
        self.assertFalse(result['content_different'])

    def test_only_text_can_normalize_newlines(self):
        expected = {n: hashlib.sha256(b'a\nb').hexdigest() for n in ('a.py', 'a.wav')}
        result = deploy.compare_inventory({n: b'a\r\nb' for n in expected}, expected)
        self.assertEqual(result['different'], ['a.py', 'a.wav'])
        self.assertEqual(result['content_different'], ['a.wav'])

    def test_deleted_and_stale_files_are_detected(self):
        result = deploy.compare_inventory({'obsolete.py': b'old'}, {'new.py': 'hash'})
        self.assertEqual(result['missing'], ['new.py'])
        self.assertEqual(result['extra'], ['obsolete.py'])
