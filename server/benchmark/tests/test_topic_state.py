import copy
import json
import unittest
from pathlib import Path
from server.benchmark.topic_state import branch,judgment_score,load_suite,FIELDS


class TopicStateTests(unittest.TestCase):
    def setUp(self):
        self.c=load_suite(Path(__file__).parents[1]/'weight_space/topic-state-suite.json')['cases'][0]

    def test_arms_keep_same_history_and_isolate_hints(self):
        original=copy.deepcopy(self.c)
        base,p=branch(self.c,'reply','persona')
        stale,_=branch(self.c,'stale_reply','persona')
        oracle,_=branch(self.c,'oracle_reply','persona')
        diag,q=branch(self.c,'diagnose','persona')
        self.assertEqual(base['messages'],diag['messages'])
        self.assertEqual(base['messages'],oracle['messages'])
        self.assertEqual(base['context'],diag['context'])
        self.assertNotIn(self.c['oracle'],stale['context'])
        self.assertIn(self.c['stale_memo'],stale['context'])
        self.assertNotEqual(p,q)
        diag['messages'][0]['content']='mutated'
        self.assertEqual(self.c,original)

    def test_missing_invalid_and_partial_are_distinct(self):
        expected=self.c['expected']
        def score(text,status='ok'):
            return judgment_score(dict(status=status,calls=[],messages=[dict(content=text)]),expected)
        self.assertEqual(score(json.dumps(expected))['field_score'],5)
        partial=dict(expected);partial['old_question_answered']=1
        self.assertEqual(score(json.dumps(partial))['field_score'],4)
        del partial['old_task_status']
        self.assertEqual(score(json.dumps(partial))['field_score'],3)
        self.assertIsNone(score('not json')['field_score'])
        self.assertIsNone(score(json.dumps(expected),'token_limit')['field_score'])
        fenced=score('```json\n'+json.dumps(expected)+'\n```')
        self.assertFalse(fenced['strict_json']);self.assertEqual(fenced['field_score'],5)

    def test_assessment_contains_evidence_but_not_answer_hints(self):
        c,p=branch(self.c,'assess','persona marker')
        payload=json.loads(c['messages'][0]['content'].split('\n',1)[1])
        self.assertEqual(payload['messages'],self.c['messages'])
        self.assertEqual(payload['context'],self.c['context'])
        self.assertNotIn('persona marker',p)
        self.assertNotIn(self.c['oracle'],c['messages'][0]['content'])
        stale,_=branch(self.c,'stale_assess','persona marker')
        self.assertIn(self.c['stale_memo'],stale['messages'][0]['content'])
