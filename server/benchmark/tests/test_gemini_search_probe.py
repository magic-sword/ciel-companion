import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('gemini_probe', ROOT / 'scripts/server/probe-gemini-search.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def grounded():
    return dict(modelVersion=probe.MODEL, candidates=[dict(finishReason='STOP',
        content={'parts': [{'text': 'A supported fact'}]}, groundingMetadata=dict(
            webSearchQueries=['official documentation'],
            groundingChunks=[{'web': {'uri': 'https://example.org', 'title': 'Source'}}],
            groundingSupports=[{'segment': {'text': 'A supported fact'}, 'groundingChunkIndices': [0]}]))])


class GeminiSearchProbeTests(unittest.TestCase):
    def test_requires_grounding_not_only_fluent_text(self):
        self.assertTrue(probe.inspect_grounding(grounded())['grounding_present'])
        for field in ('webSearchQueries', 'groundingChunks', 'groundingSupports'):
            data = grounded()
            data['candidates'][0]['groundingMetadata'].pop(field)
            self.assertFalse(probe.inspect_grounding(data)['grounding_present'])

    def test_rejects_truncation_and_other_models(self):
        data = grounded()
        data['candidates'][0]['finishReason'] = 'MAX_TOKENS'
        self.assertFalse(probe.inspect_grounding(data)['grounding_present'])
        data = grounded()
        data['modelVersion'] = 'another-model'
        self.assertFalse(probe.inspect_grounding(data)['grounding_present'])

    def test_requires_free_tier_confirmation_before_network(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(probe.httpx, 'Client') as client:
            args = Obj(env_file=Path(folder) / 'missing', check_config=False, free_tier_confirmed=False)
            with self.assertRaisesRegex(ValueError, 'Free Tier'):
                probe.run(args)
            client.assert_not_called()

    def test_quota_failure_stops_and_redacts_key(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(probe.httpx, 'Client') as factory, \
                patch.dict(probe.os.environ, {'GEMINI_API_KEY': 'fixture-secret'}), patch('builtins.print'):
            args = Obj(env_file=Path(folder) / 'missing', check_config=False, free_tier_confirmed=True,
                       output=Path(folder) / 'report.json', limit=3)
            client = factory.return_value.__enter__.return_value
            client.post.return_value = Obj(status_code=429, json=lambda: {'error': {
                'status': 'RESOURCE_EXHAUSTED', 'message': 'fixture-secret'}})
            self.assertEqual(probe.run(args), 1)
            self.assertEqual(client.post.call_count, 1)
            saved = args.output.read_text(encoding='utf8')
            self.assertNotIn('fixture-secret', saved)
            self.assertEqual(len(json.loads(saved)['trials']), 1)


if __name__ == '__main__':
    unittest.main()
