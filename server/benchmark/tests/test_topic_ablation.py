import copy
from pathlib import Path
import unittest
from server.benchmark import topic_ablation as a, topic_state as s, weight_space as w


class AblationTests(unittest.TestCase):
    def test_input_interventions_preserve_user_and_state_evidence(self):
        parts={n:(w.ROOT/'server/agent/config/prompts'/f'{n}.md').read_text(encoding='utf-8') for n in w.PROMPTS}
        cases=s.load_suite(Path(s.__file__).with_name('weight_space')/'topic-state-suite.json')['cases']
        original=copy.deepcopy(cases)
        for case in cases:
            for arm in a.ARMS:
                c,p=a.branch(case,arm,parts)
                self.assertEqual([m for m in c['messages'] if m['role']=='user'],[m for m in case['messages'] if m['role']=='user'])
                if arm not in ('remove_questions','neutral_failure'):self.assertEqual(c['messages'],case['messages'])
                if arm not in ('neutral_failure','state_hint'):self.assertEqual(c['context'],case['context'])
                if arm=='remove_questions':self.assertFalse(any('？' in m['content'] for m in c['messages'] if m['role']=='assistant'))
                if arm=='base':self.assertEqual(p,'\n'.join(parts[n] for n in w.PROMPTS))
        self.assertEqual(cases,original)
        variants=a.variants(parts)
        self.assertNotIn('張り切りすぎて先回り',variants['remove_traits'])
        self.assertIn('張り切りすぎて先回り',variants['remove_neutral'])
        self.assertLessEqual(abs(len(variants['remove_traits'])-len(variants['remove_neutral'])),10)
