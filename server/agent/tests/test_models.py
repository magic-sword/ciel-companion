import types
import unittest
from unittest import mock

import models


class CostTest(unittest.TestCase):
    def test_text_model(self):
        # 入力 1,000（キャッシュ 400）・出力 100 の gpt-5.4-mini
        usd = models.cost('gpt-5.4-mini', 1000, 400, 100)
        self.assertAlmostEqual(usd, (600 * 0.75 + 400 * 0.075 + 100 * 4.50) / 1e6)

    def test_realtime_audio_input(self):
        # 入力 1,000 のうち音声 300（キャッシュ 800 のうち音声 100）
        usd = models.cost('gpt-realtime-2.1-mini', 1000, 800, 50, audio_input=300, audio_cached=100)
        expected = (0 * 0.60 + 700 * 0.06 + 200 * 10.00 + 100 * 0.30 + 50 * 2.40) / 1e6
        self.assertAlmostEqual(usd, expected)

    def test_unknown_model_costs_nothing(self):
        self.assertEqual(models.cost('unknown', 1000, 0, 1000), 0.0)

    def test_role_reads_environment(self):
        with mock.patch.dict('os.environ', {'CIEL_THOUGHT_MODEL': 'gpt-5.4'}):
            self.assertEqual(models.model('thought'), 'gpt-5.4')


class RecordTest(unittest.TestCase):
    def test_chat_and_responses_usage(self):
        chat = types.SimpleNamespace(prompt_tokens=100, completion_tokens=20,
                                     prompt_tokens_details=types.SimpleNamespace(cached_tokens=50),
                                     completion_tokens_details=types.SimpleNamespace(reasoning_tokens=5))
        resp = types.SimpleNamespace(input_tokens=200, output_tokens=30,
                                     input_tokens_details=types.SimpleNamespace(cached_tokens=0),
                                     output_tokens_details=None)
        with mock.patch('debug_log.record') as rec:
            models.record('thought', 'gpt-5.4-mini', chat)
            models.record('research', 'gpt-5.4-mini', resp)
            models.record('notes', 'gpt-5.4-mini', None)
        self.assertEqual(rec.call_count, 2)
        first = rec.call_args_list[0].kwargs
        self.assertEqual((first['role'], first['input_tokens'], first['cached_tokens'], first['reasoning_tokens']),
                         ('thought', 100, 50, 5))
        self.assertEqual(rec.call_args_list[1].kwargs['input_tokens'], 200)


if __name__ == '__main__':
    unittest.main()
