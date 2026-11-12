import copy
import json
from pathlib import Path
import unittest
from server.benchmark import question_study as q,topic_state as s,weight_space as w
from server.benchmark.question_study_summary import exclusion

class QuestionStudyTests(unittest.TestCase):
    def test_interventions_and_speaker_counterfactual(self):
        cases=s.load_suite(Path(s.__file__).with_name('weight_space')/'topic-state-suite.json')['cases']
        original=copy.deepcopy(cases)
        parts={n:(w.ROOT/'server/agent/config/prompts'/f'{n}.md').read_text(encoding='utf-8') for n in w.PROMPTS}
        for case in cases:
            for arm in q.ARMS:
                c,p=q.branch(case,arm,parts)
                if arm.endswith('probe'):
                    payload=json.loads(c['messages'][0]['content'])
                    self.assertEqual(payload['messages'][-1],case['messages'][-1])
                    if payload['target_question']:
                        expected='user' if arm=='swapped_probe' else 'assistant'
                        self.assertEqual(c['expected_owner']['speaker'],expected)
                        self.assertTrue(any(m['role']==expected and payload['target_question'] in m['content'] for m in payload['messages']))
                else:
                    self.assertEqual(c['messages'][-1],case['messages'][-1])
                    if arm!='swap_speaker':self.assertEqual([m for m in c['messages'] if m['role']=='user'],[m for m in case['messages'] if m['role']=='user'])
        self.assertEqual(cases,original)

    def test_probe_missing_and_partial(self):
        expected=dict(speaker='assistant',addressee='user',time='past')
        def score(text):return q.owner_score(dict(status='ok',calls=[],messages=[dict(content=text)]),expected)
        self.assertEqual(score(json.dumps(expected))['field_score'],5)
        self.assertIsNone(score('plain reply')['field_score'])
        self.assertAlmostEqual(score('{"speaker":"assistant"}')['field_score'],5/3)

    def test_ambiguous_or_absent_target_is_not_attribution_evidence(self):
        def trial(target,messages):return dict(input=dict(messages=[dict(content=json.dumps(dict(target_question=target,messages=messages)))]))
        self.assertEqual(exclusion(trial(None,[])),'no_target_question')
        self.assertEqual(exclusion(trial('Ready?', [dict(role='user',content='Ready?'),dict(role='assistant',content='Ready?')])),'ambiguous_multiple_speakers')
        self.assertIsNone(exclusion(trial('Ready?', [dict(role='assistant',content='Ready?')])) )
