import copy
import json
from pathlib import Path
import unittest
from server.benchmark import question_disposition as q,topic_state as s,weight_space as w
from server.benchmark.question_study_summary import summarize_need

class DispositionTests(unittest.TestCase):
    def test_summary_keeps_missing_and_controls_separate(self):
        def row(case,text):
            value=dict(status='ok',calls=[],messages=[dict(content=text)])
            return dict(id=case,arm='need_probe',judgment=q.score(value,dict(answered=False,necessary_now=False,ask_now=False)))
        report=dict(trials=[row('pending','not json'),row('needed-question','{"answered":false,"necessary_now":false,"ask_now":false}')])
        result=summarize_need(report)['need_probe']
        self.assertEqual(result['targets']['missing'],1)
        self.assertIsNone(result['targets']['mean_score'])
        self.assertEqual(result['controls']['scorable'],1)

    def test_answer_closure_and_controls_are_separate(self):
        suite=s.load_suite(Path(s.__file__).with_name('weight_space')/'topic-state-suite.json')
        parts={n:(w.ROOT/'server/agent/config/prompts'/f'{n}.md').read_text(encoding='utf-8') for n in w.PROMPTS}
        for case in suite['cases']:
            if case['id'] not in q.CASES:continue
            original=copy.deepcopy(case)
            for arm in q.ARMS:
                c,p=q.branch(case,arm,parts)
                if arm.endswith('probe'):
                    payload=json.loads(c['messages'][0]['content'])
                    self.assertEqual(payload['messages'][-1],case['messages'][-1])
                    if case['id'] in q.TARGETS:
                        self.assertEqual(c['expected_need']['answered'],arm=='answered_need_probe')
                        self.assertFalse(c['expected_need']['ask_now'])
                else:
                    self.assertEqual(c['messages'][-1],case['messages'][-1])
                    if case['id'] not in q.TARGETS:self.assertEqual(c['messages'],case['messages'])
                    elif arm!='base':self.assertEqual(len(c['messages']),len(case['messages'])+2)
            self.assertEqual(case,original)
