import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'continuation_report.py'
spec = importlib.util.spec_from_file_location('continuation_report', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def trial(variant, status='complete', text='hello', elapsed=10):
    return dict(case='example', repeat=0, variant=variant, status=status, calls=[],
                turns=[dict(phase=0, spoken=text, elapsed_ms=elapsed, usage={'completion_tokens': 4})],
                trace_sha256='test', transcript=[dict(role='system', content='private'),
                    dict(role='user', content='Hello'), dict(role='user', content='SYSTEM: {}'),
                    dict(role='assistant', content='private decision')])


class ReportTests(unittest.TestCase):
    def report(self, trials):
        return dict(trials=trials, suite_sha256='suite', conditions={})

    def test_pairs_keep_signed_delta_without_calling_it_quality(self):
        result = module.compare(self.report([trial('loop', elapsed=7), trial('baseline')]))
        self.assertEqual(result['comparable_pairs'], 1)
        self.assertEqual(result['pairs'][0]['delta']['elapsed_ms'], -3)
        self.assertIsNone(result['quality'])

    def test_missing_and_failed_samples_are_not_improvements(self):
        for trials in ([trial('loop')], [trial('loop', 'failed'), trial('baseline')]):
            result = module.compare(self.report(trials))
            self.assertEqual(result['missing_or_failed_pairs'], 1)
            self.assertIsNone(result['pairs'][0]['delta'])

    def test_duplicate_trial_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            module.compare(self.report([trial('loop'), trial('loop')]))

    def test_review_hides_condition_and_private_generation(self):
        review, key = module.review_material(self.report([trial('loop')]))
        self.assertNotIn('variant', review[0])
        self.assertEqual(review[0]['conversation'], [dict(phase=0, input='Hello',
            outputs=[dict(spoken='hello', tool_result=None, operation=None)])])
        self.assertEqual(key[0]['variant'], 'loop')
        self.assertIsNone(review[0]['scores'])


if __name__ == '__main__':
    unittest.main()
