import copy
import unittest
from pathlib import Path
from server.benchmark import repetition as run, repetition_review as review

class PreventionTests(unittest.TestCase):
    def test_question_routing_and_generated_response_only(self):
        spec=dict(user='next',branches=[dict(id='answer',pattern='people',user='two')])
        self.assertEqual(run.user_turn(spec,[dict(role='assistant',content='Two people. Next?')])[0],'next')
        self.assertEqual(run.user_turn(spec,[dict(role='assistant',content='How many people?')])[0],'two')
        self.assertEqual(run.user_turn(spec,[dict(role='user',content='How many people?')])[0],'next')
        broad=dict(user='next',branches=[dict(id='remind',pattern='.',user='stop')])
        self.assertEqual(run.user_turn(broad,[dict(role='assistant',content='体が休むように教えてくれたのです。')])[0],'next')
        self.assertEqual(run.user_turn(broad,[dict(role='assistant',content='人数を教えてください。')])[0],'stop')

    def test_no_seed_and_controls_and_switches(self):
        suite=run.load(Path(run.SUITE).with_name('prevention-suite.json'))
        self.assertEqual(len(suite['cases']),6)
        self.assertTrue(all(not c['messages'] for c in suite['cases']))
        self.assertTrue(all(len(c['dialogue'])==8 for c in suite['cases']))

    def test_onset_censor_and_no_empty_success(self):
        spec=dict(dialogue=[dict(phase='target',switch=False)]*3)
        good=dict(repeat_units=0,repeat_chars=0,followups=0,content=4,control=None,unverified_completion=False)
        ratings=[copy.deepcopy(good) for _ in range(3)]
        a=review.trial_score(spec,[{}]*3,ratings)
        self.assertIsNone(a['first_repeat_turn']);self.assertTrue(a['onset_censored'])
        ratings[1]['repeat_units']=1
        b=review.trial_score(spec,[{}]*3,ratings)
        self.assertEqual(b['first_repeat_turn'],1);self.assertTrue(b['repeat_occurred'])
        self.assertFalse(review.trial_score(spec,[{}]*2,ratings[:2])['complete'])

    def test_branch_audit_required_before_incidence(self):
        t=dict(index=0,status='ok',calls=[],response=[dict(content='OK')])
        spec=dict(id='one',split='dev',family='one',dialogue=[dict(user='hi',phase='target',switch=False,rubric='answer',branches=[dict(id='x')])])
        suite=dict(_file_sha256='hash',cases=[spec])
        report=dict(suite_sha256='hash',case_ids=['one'],split='dev',rounds=1,completion='complete',mode_consistent=True,
                    sampling={},conditions=dict(weights_sha256='w'),prompt_sha256='p',renderer={},trials=[dict(id='one',family='one',repeat=0,seed=1,status='ok',turns=[t])])
        cards=review.prepare(report,suite);cards['evaluator']='test'
        c=cards['cards'][0];c.update(units=[],content_0_4=4,unverified_completion=False,evidence='answer')
        self.assertIsNone(review.score(report,cards,suite)['macro_series_incidence'])
        c['branch_valid']=False
        self.assertFalse(review.score(report,cards,suite)['complete'])
        c['branch_valid']=True
        self.assertEqual(review.score(report,cards,suite)['macro_series_incidence'],0)

if __name__=='__main__':unittest.main()
