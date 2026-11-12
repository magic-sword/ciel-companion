import unittest
from pathlib import Path
from server.benchmark.weight_space import load_suite
from server.benchmark.loop_probe import metrics
from server.benchmark.progress import score_report


class StreamReplayTests(unittest.TestCase):
    def setUp(self):
        self.suite=load_suite(Path(__file__).parents[1]/'weight_space/stream-replay-suite.json')
        self.case=self.suite['cases'][0]

    def report(self,text):
        return {'trials':[dict(id=self.case['id'],category=self.case['category'],repeat=0,status='ok',messages=[],calls=[],
                        turns=[dict(index=0,status='ok',response=[{'content':text}])])]}

    def test_state_control_does_not_change_history_or_probes(self):
        a,b=self.suite['cases'][:2]
        self.assertEqual(a['messages'],b['messages'])
        self.assertEqual(a['dialogue'],b['dialogue'])
        self.assertNotEqual(a['context'],b['context'])

    def test_long_plan_has_multiple_units_without_double_counting_chars(self):
        r=self.report('原木を10個集めます。オークが7本あります。どんな拠点を作りたいですか？木を植えて成長を待ちましょう。')
        _,turns=metrics(self.case,r['trials'][0])
        m=turns[0]['metrics']
        self.assertEqual(m['loop_unit_types'][0],4)
        self.assertLessEqual(m['loop_unit_char_fraction'][0],1)
        self.assertEqual(m['loop_unit_types'][1],'neutral')

    def test_review_distinguishes_negation_from_unwanted_repetition(self):
        r=self.report('原木集めは始めません。整地の範囲を教えてください。')
        _,review=score_report(r,self.suite)
        item=review['items'][0]
        self.assertEqual(item['context'],self.case['context'])
        review['evaluator']='test/rubric-v1'
        for name in item['unnecessary_units']:
            item['unnecessary_units'][name]=0
            item['unit_evidence'][name]='Declines the old task and asks about the requested clearing area.'
        scored,_=score_report(r,self.suite,review)
        self.assertEqual(scored['observations'][1]['metrics']['review_plan_focus']['value'],5)
        item['unnecessary_units']['collection_plan']=1
        scored,_=score_report(r,self.suite,review)
        self.assertEqual(scored['observations'][1]['metrics']['review_plan_focus']['value'],3.75)
        item['unnecessary_units']['growth_explanation']=None
        scored,_=score_report(r,self.suite,review)
        self.assertIsNone(scored['observations'][1]['metrics']['review_plan_focus']['value'])
        item['unnecessary_units']['growth_explanation']=1
        item['unit_evidence']['growth_explanation']=''
        with self.assertRaises(ValueError):score_report(r,self.suite,review)
