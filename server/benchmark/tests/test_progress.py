import copy
import unittest
from server.benchmark import progress as p


class ProgressTests(unittest.TestCase):
    def test_exact_distance_is_diagnostic(self):
        c={'checks':[{'type':'exact','value':'20'}]}
        a=p.diagnostics(c,dict(status='ok',messages=[{'content':'20です'}]))
        b=p.diagnostics(c,dict(status='ok',messages=[{'content':'20'}]))
        self.assertEqual(a['check_0_exact_edit_distance']['value'],2)
        self.assertEqual(b['check_0_exact_edit_distance']['value'],0)

    def test_json_parts_and_extra_fields(self):
        self.assertEqual(p.structure({'a':1,'b':2},{'a':1,'b':3}),(1,2))
        self.assertEqual(p.structure({'a':1},{'a':True}),(0,1))
        self.assertEqual(p.structure({'a':1},{'a':1,'extra':2}),(1,2))

    def test_invalid_json_is_unknown_not_perfect(self):
        d=p.diagnostics({'checks':[{'type':'json','value':{'a':1}}]},dict(status='ok',messages=[{'content':'oops'}]))
        self.assertIsNone(d['check_0_json_fields']['value'])

    def test_bad_tool_arguments_have_partial_credit(self):
        case={'checks':[{'type':'calls'}], 'steps':[{'name':'go','arguments':{'x':2,'y':3}}]}
        row=dict(status='error',messages=[],calls=[{'name':'go','arguments':{'x':2,'y':4}}])
        d=p.diagnostics(case,row)
        self.assertAlmostEqual(d['check_0_calls_structure']['value'],10/3)

    def fixture(self):
        case=dict(id='a',messages=[{'role':'user','content':'hi'}],checks=[{'type':'human'}])
        turn=dict(index=0,status='ok',response=[{'content':'あ'*120}],max_chars=80,rubric='short')
        turn.update(over_length=True,metrics={'chars':120,'repeated_sentences':0,'reused_sentences':0})
        row=dict(id='a',repeat=0,category='chat',status='ok',messages=turn['response'],turns=[turn],
                 automatic_pass=True,human_pending=True,total_ms=1)
        report=dict(schema='ciel-weight-space-v1',completion='complete',case_ids=['a'],rounds=1,
                    conditions={'hardware':'h','runtime':'r','shared_load':'quiet'},
                    before={'mode':{'mode':'cpu'}},after={'mode':'cpu'},trials=[row])
        return report,dict(cases=[case])

    def test_paired_conversation_improvement_and_missing_semantics(self):
        a,suite=self.fixture()
        b=copy.deepcopy(a)
        b['trials'][0]['turns'][0]['response']=[{'content':'あ'*90}]
        sa,_=p.score_report(a,suite)
        sb,_=p.score_report(b,suite)
        result=p.compare_scores(sa,sb)
        rows={r['metric']:r for r in result['summary']}
        self.assertEqual(rows['excess_chars']['delta'],-30)
        self.assertGreater(rows['length_budget']['delta'],0)
        self.assertEqual(rows['review_content']['paired'],0)
        self.assertIsNone(rows['review_content']['delta'])

    def test_review_binding_and_evidence(self):
        report,suite=self.fixture()
        _,template=p.score_report(report,suite)
        template['evaluator']='reviewer-1/rubric-v1'
        template['items'][0]['ratings']['content']=3
        with self.assertRaises(ValueError): p.score_report(report,suite,template)
        template['items'][0]['evidence']['content']='Required fact present.'
        scored,_=p.score_report(report,suite,template)
        self.assertEqual(scored['observations'][1]['metrics']['review_content']['value'],3.75)
        template['report_hash']='wrong'
        with self.assertRaises(ValueError): p.score_report(report,suite,template)

    def test_truncated_output_not_length_improvement(self):
        report,suite=self.fixture()
        report['trials'][0]['turns'][0]['status']='token_limit'
        scored,_=p.score_report(report,suite)
        self.assertIsNone(scored['observations'][1]['metrics']['length_budget']['value'])


if __name__=='__main__': unittest.main()
