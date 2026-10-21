from types import SimpleNamespace
import unittest

from usage import UsageLog


def llm(**tokens):
    return SimpleNamespace(type='llm_usage', provider='openai', model='gpt-realtime-2.1-mini', **tokens)


def event(*usages):
    return SimpleNamespace(usage=SimpleNamespace(model_usage=list(usages)))


class UsageLogTests(unittest.TestCase):
    def test_logs_difference_from_previous_total_per_reply(self):
        log = UsageLog()
        with self.assertLogs('ciel-agent.usage', 'INFO') as seen:
            log.on_usage(event(llm(input_tokens=1000, input_cached_tokens=0, output_tokens=50)))
            log.on_usage(event(llm(input_tokens=2600, input_cached_tokens=900, output_tokens=120)))
        self.assertIn('入力 1,000（キャッシュ 0・0%', seen.output[0])
        self.assertIn('入力 1,600（キャッシュ 900・56%', seen.output[1])
        self.assertIn('出力 70', seen.output[1])
        self.assertEqual(log.replies, 2)

    def test_ignores_updates_without_new_llm_tokens(self):
        log = UsageLog()
        log.on_usage(event(llm(input_tokens=1000, output_tokens=50)))
        tts = SimpleNamespace(type='tts_usage', provider='irodori', model='')
        with self.assertNoLogs('ciel-agent.usage', 'INFO'):
            log.on_usage(event(llm(input_tokens=1000, output_tokens=50), tts))
        self.assertEqual(log.replies, 1)

    def test_summary_reports_totals(self):
        log = UsageLog()
        log.on_usage(event(llm(input_tokens=4000, input_cached_tokens=3000, output_tokens=100)))
        with self.assertLogs('ciel-agent.usage', 'INFO') as seen:
            log.summary()
        self.assertIn('返事 1 回 入力 4,000（キャッシュ 3,000・75%） 出力 100', seen.output[0])


if __name__ == '__main__':
    unittest.main()
