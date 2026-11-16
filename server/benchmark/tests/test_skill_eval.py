import copy
import json
import unittest
from server.benchmark.skill_eval import compare, metrics


def fixture():
    return dict(sequence='ops', case='start', repeat=0, expected='start_minutes',
        required={'lookback_minutes': 5}, calls=[dict(name='start_minutes', arguments={'lookback_minutes': 5})],
        outputs=[dict(name='start_minutes', value=json.dumps({'recording': True}))],
        requests=[dict(selected=[dict(name='load_capabilities', arguments='{"service_ids":["5"]}'),
            dict(name='execute_capability', arguments='{"tool_id":"start_minutes"}')],
            messages=[], usage={'prompt_tokens': 100}, loaded=[])],
        errors=[], seconds=2, fixture_success=True)


class SkillEvaluationTests(unittest.TestCase):
    def test_call_without_observed_result_is_not_success(self):
        row = fixture()
        self.assertTrue(metrics(row)['operation_success'])
        row['outputs'] = []
        self.assertFalse(metrics(row)['operation_success'])
        self.assertFalse(metrics(row)['missing_operation'])

    def test_wrong_arguments_and_extra_mutation_fail(self):
        row = fixture()
        row['calls'][0]['arguments']['lookback_minutes'] = 0
        self.assertFalse(metrics(row)['operation_success'])
        row = fixture()
        row['calls'].append(dict(name='finish_minutes', arguments={}))
        row['outputs'].append(dict(name='finish_minutes', value='{"recording":false}'))
        self.assertFalse(metrics(row)['operation_success'])

    def test_harmless_status_step_does_not_hide_success(self):
        row = fixture()
        row['calls'].insert(0, dict(name='get_minutes_status', arguments={}))
        row['outputs'].insert(0, dict(name='get_minutes_status', value='{}'))
        row['fixture_success'] = False
        self.assertTrue(metrics(row)['operation_success'])
        self.assertFalse(metrics(row)['strict_trajectory'])

    def test_blocked_proposal_is_distinct_from_executed_operation(self):
        row = fixture()
        row.update(expected=None, calls=[], outputs=[])
        self.assertTrue(metrics(row)['undesired_proposal'])
        self.assertTrue(metrics(row)['unnecessary_load'])
        self.assertTrue(metrics(row)['operation_success'])

    def test_failed_dispatch_is_not_counted_as_executed(self):
        row = fixture()
        row.update(expected=None, outputs=[], errors=['invalid_capability'])
        result = metrics(row)
        self.assertEqual(result['unexpected_operations'], 0)
        self.assertEqual(result['incomplete_dispatches'], 1)
        self.assertFalse(result['operation_success'])

    def test_pairs_and_missing_are_reported(self):
        before = dict(suite={}, trials=[fixture()])
        after = copy.deepcopy(before)
        after['trials'][0]['outputs'] = []
        self.assertEqual(compare(before, after)['regressed'], 1)
        after['trials'][0]['repeat'] = 1
        result = compare(before, after)
        self.assertEqual(result['matched'], 0)
        self.assertEqual(result['missing_after'], 1)
        after['suite'] = {'changed': True}
        with self.assertRaises(ValueError):
            compare(before, after)

    def test_search_must_return_the_original_fact_not_just_echo_query(self):
        row = fixture()
        row.update(expected='search_conversation', required={'query': 'オーロラ'},
            calls=[dict(name='search_conversation', arguments={'query': 'オーロラ'})],
            outputs=[dict(name='search_conversation', value='{"query":"オーロラ","matches":[]}')], outcome='complete')
        self.assertFalse(metrics(row)['operation_success'])
        self.assertTrue(metrics(row)['false_completion'])
        row['outputs'][0]['value'] = json.dumps({'matches': [{'id': 1, 'text': '次の企画名はオーロラです。'}]})
        self.assertTrue(metrics(row)['operation_success'])

    def test_error_feedback_is_not_a_successful_dispatch(self):
        row = fixture()
        row['outputs'][0]['error'] = True
        self.assertFalse(metrics(row)['operation_success'])
