import copy
import time
import unittest
from types import SimpleNamespace
from server.benchmark import repetition as run,repetition_review as review


class RepetitionTests(unittest.TestCase):
    def test_real_renderer_and_generated_history_and_sampling(self):
        # Real SDK serialization; network is replaced, generated replies must flow back.
        render,_=run.renderer(run.w.ROOT/'server/agent')
        case=dict(id='test',family='test',messages=[],context='state',dialogue=[dict(user='first',phase='target',switch=True,rubric='respond'),dict(user='second',phase='target',switch=False,rubric='respond')])
        original=copy.deepcopy(case);seen=[]
        def chat(url,payload,timeout):
            seen.append(copy.deepcopy(payload))
            return dict(role='assistant',content='generated reply'),dict(finish_reason='stop')
        args=SimpleNamespace(timeout=5,deadline=time.monotonic()+30,sampling='production',temperature=0,max_tokens=20,model='local',base_url='http://localhost/v1',thinking=False)
        row=run.series(case,'fixed',args,1,render,chat)
        self.assertEqual(row['status'],'ok');self.assertNotIn('temperature',seen[0])
        self.assertEqual(seen[1]['messages'][0]['content'],'fixed')
        self.assertIn(dict(role='assistant',content='generated reply'),seen[1]['messages'])
        self.assertEqual(case,original)
        def failed(*args):return dict(role='assistant',content=''),dict(finish_reason='length')
        self.assertEqual(run.series(case,'fixed',args,1,render,failed)['status'],'incomplete')

    def test_progress_recovery_and_censoring(self):
        spec=dict(dialogue=[dict(phase='target',switch=i==0) for i in range(5)])
        def rating(repeats):return dict(repeat_units=repeats,repeat_chars=repeats*10,followups=0,content=4,control=None,unverified_completion=False)
        ratings=[rating(x) for x in (1,1,0,0,1)]
        score=review.trial_score(spec,[{}]*5,ratings)
        self.assertEqual(score['longest_run'],2);self.assertEqual(score['repeat_units'],3)
        self.assertEqual(score['recovery'][0]['delay'],2);self.assertEqual(score['recovery'][0]['relapses'],1)
        self.assertEqual(score['repetition_free_0_5'],2)
        ratings[3]['unverified_completion']=True
        self.assertTrue(review.trial_score(spec,[{}]*5,ratings)['recovery'][0]['censored'])
        ratings[3]=None
        self.assertIsNone(review.trial_score(spec,[{}]*5,ratings)['repeat_units'])

    def test_evidence_and_controls_and_missing_series(self):
        turn=dict(status='ok',calls=[],response=[dict(content='Repeat?')])
        c=dict(text='Repeat?',response_sha256=review.digest(turn['response']),units=[],content_0_4=4,control_0_4=4,phase='control',unverified_completion=False,evidence='necessary recap')
        self.assertEqual(review.turn_score(c,turn)['repeat_units'],0)
        c['units']=[dict(start=0,end=7,text='Repeat?',kind='same_question')]
        self.assertEqual(review.turn_score(c,turn)['repeat_chars'],7)
        longer=copy.deepcopy(turn);longer['response']=[dict(content='Repeat? Repeat?')]
        longer_card=copy.deepcopy(c);longer_card.update(text='Repeat? Repeat?',response_sha256=review.digest(longer['response']),units=[dict(start=0,end=7,text='Repeat?',kind='same_question'),dict(start=8,end=15,text='Repeat?',kind='same_question')])
        self.assertEqual(review.turn_score(longer_card,longer)['repeat_units'],2)
        self.assertEqual(review.turn_score(longer_card,longer)['repeat_chars'],14)
        c['units'].append(c['units'][0])
        with self.assertRaises(ValueError):review.turn_score(c,turn)
        c['units']=[];c['content_0_4']=None
        self.assertIsNone(review.turn_score(c,turn))
        c['content_0_4']=4;turn['response'][0]['content']='altered'
        with self.assertRaises(ValueError):review.turn_score(c,turn)

    def test_pairing_rejects_uncontrolled_change(self):
        row=dict(id='x',repeat=0,seed=1,metrics=dict(repeat_units=2,repeat_chars=10,repeat_turn_fraction=.5,content_0_5=5,control_0_5=None,premature_followups=0,unverified_completions=0))
        base=dict(complete=True,protocol=dict(sampling='production'),context=dict(weights='a',prompt='p',renderer='r'),rows=[row])
        other=copy.deepcopy(base);other['context']['weights']='b';other['rows'][0]['metrics']['repeat_units']=1
        self.assertEqual(review.compare(base,other)['pairs'][0]['delta']['repeat_units'],-1)
        other['context']['renderer']='new'
        with self.assertRaises(ValueError):review.compare(base,other)

    def test_missing_whole_series_prevents_macro_score(self):
        dialogue=[dict(phase='target',switch=True,rubric='respond')]
        suite=dict(_file_sha256='hash',cases=[dict(id=id,split='dev',family='family',dialogue=dialogue) for id in ('one','two')])
        turn=dict(index=0,status='ok',calls=[],response=[dict(content='OK')])
        report=dict(suite_sha256='hash',case_ids=['one','two'],split='dev',rounds=1,completion='complete',mode_consistent=True,
                    sampling={},conditions=dict(weights_sha256='weight'),prompt_sha256='prompt',renderer={},
                    trials=[dict(id='one',family='family',repeat=0,seed=1,status='ok',turns=[turn])])
        cards=review.prepare(report,suite);cards['evaluator']='test'
        cards['cards'][0].update(units=[],content_0_4=4,unverified_completion=False,evidence='responds')
        score=review.score(report,cards,suite)
        self.assertFalse(score['complete']);self.assertIsNone(score['macro_repeat_fraction'])


if __name__=='__main__':unittest.main()
