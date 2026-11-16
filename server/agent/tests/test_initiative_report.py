import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('latency_report', ROOT/'scripts/server/conversation_latency_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


class InitiativeReportTest(unittest.TestCase):
    def test_silent_decision_is_not_attributed_to_the_next_reply(self):
        rows = [
            {'kind': 'speak', 'why': 'initiative'},
            {'kind': 'model_usage', 'role': 'mind', 'input_tokens': 100, 'cached_tokens': 90},
            {'kind': 'model_response', 'role': 'initiative', 'seconds': 2, 'prompt_ms': 300, 'predicted_ms': 700},
            {'kind': 'initiative', 'status': 'silent', 'speaks': False},
            {'kind': 'item', 'role': 'assistant', 'text': 'ordinary reply'},
            {'kind': 'speak', 'why': 'initiative'},
            {'kind': 'initiative', 'status': 'spoken', 'speaks': True},
            {'kind': 'initiative', 'status': 'interrupted', 'overlap': True},
            {'kind': 'item', 'role': 'assistant', 'text': 'self started reply'},
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'trace.jsonl'
            path.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf8')
            report = reporter.report(path)
        self.assertIsNone(report['replies'][0]['input'])
        counts = report['summary']['initiative']
        self.assertEqual(counts['request_seconds'], 2)
        self.assertEqual(counts['model_compute_ms'], 1000)
        self.assertEqual(counts['reply_items'], 1)
        self.assertEqual(counts['overlaps'], 1)


if __name__ == '__main__':
    unittest.main()
