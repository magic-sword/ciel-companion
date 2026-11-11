import copy
import unittest
from types import SimpleNamespace

from server.benchmark import weight_space as w


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.suite = w.load_suite(w.DATA / 'conversation-suite.json')
        self.case = copy.deepcopy(next(c for c in self.suite['cases']
                                      if c['id'] == 'chat-s3-shorten-dev'))
        self.args = SimpleNamespace(timeout=10, model='fixture', temperature=0,
                                    max_tokens=512, thinking=False, base_url='unused')

    def test_coverage(self):
        for split in ('dev', 'holdout'):
            for stage in (1, 2, 3):
                cases = [c for c in self.suite['cases'] if c['split'] == split and c['stage'] == stage]
                self.assertGreaterEqual(len(cases), 3)
        self.assertTrue(any(c['family'] == 'repeat-request' for c in self.suite['cases']))

    def test_generated_history_and_review(self):
        replies = ['最初の説明です。', '一つに絞った回答です。', '次の短い回答です。']
        seen = []
        def chat(url, payload, timeout):
            seen.append(copy.deepcopy(payload['messages']))
            return {'role': 'assistant', 'content': replies[len(seen)-1]}, {'finish_reason': 'stop'}
        row = w.run_case(self.case, 'system', self.args, 1, chat)
        self.assertTrue(row['automatic_pass'])
        self.assertTrue(row['human_pending'])
        self.assertIn({'role': 'assistant', 'content': replies[0]}, seen[1])
        self.assertIn({'role': 'assistant', 'content': replies[1]}, seen[2])
        self.assertIsNone(row['turns'][0]['ratings'])
        self.assertEqual(w.summary([row])[row['category']]['conversation']['observed_turns'], 3)

    def test_truncation_and_empty_stop_dialogue(self):
        for content, finish in [('未完了', 'length'), ('', 'stop')]:
            def chat(*args):
                return {'role': 'assistant', 'content': content}, {'finish_reason': finish}
            row = w.run_case(self.case, '', self.args, 1, chat)
            self.assertFalse(row['automatic_pass'])
            self.assertEqual(len(row['turns']), 1)

    def test_exception_is_retained(self):
        def chat(*args):
            raise TimeoutError('fixture deadline')
        row = w.run_case(self.case, '', self.args, 1, chat)
        self.assertFalse(row['automatic_pass'])
        self.assertIn('TimeoutError', row['turns'][0]['error'])

    def test_literal_metrics_do_not_count_short_acknowledgments(self):
        text = '同じ説明を繰り返します。同じ説明を繰り返します。うん。'
        metrics = w.response_metrics(text, ['同じ説明を繰り返します。うん。'])
        self.assertEqual(metrics['repeated_sentences'], 1)
        self.assertEqual(metrics['reused_sentences'], 2)
        self.assertEqual(metrics['chars'], len(text))


if __name__ == '__main__':
    unittest.main()
