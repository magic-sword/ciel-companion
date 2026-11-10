"""Harness correctness tests, no model/network/LiveKit required."""
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server.benchmark import weight_space as w


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.suite = w.load_suite(w.DATA / 'suite.json')
        self.args = SimpleNamespace(timeout=5, model='fixture', temperature=0, max_tokens=32, thinking=False, base_url='http://127.0.0.1/v1')

    def case(self, id):
        return copy.deepcopy(next(c for c in self.suite['cases'] if c['id'] == id))

    def test_suite_both_splits(self):
        for split in ('dev', 'holdout'):
            self.assertGreaterEqual(sum(c['split'] == split for c in self.suite['cases']), 20)

    def test_json_rejects_fences_and_extra_text(self):
        case = self.case('json-dev')
        for text in ('```json\n{}\n```', '{"name":"Ciel","count":3,"active":true}\nわふっ！'):
            self.assertFalse(w.score(case, [{'content': text}], [])[1]['pass'])

    def test_prose_tool_name_is_not_call(self):
        case = self.case('stop-dev')
        self.assertFalse(w.score(case, [{'content': 'stop_game_task を実行しました'}], [])[0]['pass'])

    def test_human_stays_pending(self):
        results = w.score(self.case('comfort-dev'), [{'content': 'そばにいます。'}], [])
        self.assertIsNone(results[1]['pass'])

    def test_wrong_arguments_fail(self):
        case = self.case('gesture-failure-dev')
        self.assertFalse(w.score(case, [], [{'name': 'app_gesture', 'arguments': {'gesture': 'nod'}}])[0]['pass'])

    def test_json_scalar_types_are_preserved(self):
        self.assertFalse(w.equal({'count': 1}, {'count': True}))
        self.assertFalse(w.equal({'count': 8}, {'count': 8.0}))
        self.assertTrue(w.equal({'a':1,'b':2}, {'b':2,'a':1}))

    def test_multiturn_history_reaches_model(self):
        case = self.case('multi-name-dev')
        def chat(url, payload, timeout):
            self.assertEqual(len(payload['messages']), len(case['messages'])+1)
            self.assertEqual(payload['chat_template_kwargs'], {'enable_thinking':False})
            self.assertEqual(payload['messages'][1:], case['messages'])
            return {'role':'assistant','content':'あかり'}, {'finish_reason':'stop'}
        self.assertTrue(w.run_case(case, '', self.args, 0, chat)['automatic_pass'])

    def test_dynamic_discovery(self):
        case = self.case('gesture-dev')
        seen = []
        def chat(url, payload, timeout):
            seen.append([t['function']['name'] for t in payload['tools']])
            i = len(seen) - 1
            msg = {'role': 'assistant', 'content': ''}
            if i < len(case['steps']):
                s = case['steps'][i]
                msg['tool_calls'] = [{'id': str(i), 'function': {'name': s['name'], 'arguments': json.dumps(s['arguments'])}}]
            else:
                msg['content'] = 'はいっ！'
            return msg, {'finish_reason': 'stop'}
        row = w.run_case(case, 'system', self.args, 1, chat)
        self.assertTrue(row['automatic_pass'])
        self.assertNotIn('app_gesture', seen[0])
        self.assertIn('app_gesture', seen[1])
        self.assertTrue(row['human_pending'])

    def test_unexpected_tool_refused(self):
        def chat(*args):
            return {'role':'assistant','content':'','tool_calls':[{'id':'a','function':{'name':'delete_world','arguments':'{}'}}]}, {'finish_reason':'tool_calls'}
        row = w.run_case(self.case('stop-dev'), '', self.args, 0, chat)
        self.assertEqual(row['status'], 'error')
        self.assertFalse(row['automatic_pass'])

    def test_length_is_failure_even_correct_answer(self):
        def chat(*args):
            return {'role':'assistant','content':'確認済み'}, {'finish_reason':'length'}
        self.assertFalse(w.run_case(self.case('exact-dev'), '', self.args, 0, chat)['automatic_pass'])

    def test_network_failure_counted(self):
        def chat(*args):
            raise TimeoutError('offline')
        row = w.run_case(self.case('exact-dev'), '', self.args, 0, chat)
        report = w.summary([row])['instruction']
        self.assertEqual(report['errors'], 1)
        self.assertEqual(report['latency_n'], 0)
        self.assertIsNone(report['p95_ms'])

    def test_sse_fragment_assembly(self):
        events = [
            {'choices':[{'delta':{'reasoning_content':'thinking'}}]},
            {'choices':[{'delta':{'tool_calls':[{'index':0,'id':'call-1','function':{'name':'app_', 'arguments':'{"gesture":'}}]}}]},
            {'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'name':'gesture','arguments':'"nod"}'}}]},'finish_reason':'tool_calls'}]},
            {'choices':[], 'usage':{'completion_tokens':10}}]
        raw = b''.join(b'data: ' + json.dumps(e).encode() + b'\n\n' for e in events) + b'data: [DONE]\n'
        with patch.object(w.urllib.request, 'urlopen', return_value=io.BytesIO(raw)):
            message, timing = w.stream_chat('http://127.0.0.1/v1', {}, 3)
        self.assertEqual(message['tool_calls'][0]['function']['name'], 'app_gesture')
        self.assertEqual(json.loads(message['tool_calls'][0]['function']['arguments']), {'gesture':'nod'})
        self.assertIsNone(timing['first_content_ms'])
        self.assertIsNotNone(timing['first_event_ms'])
        self.assertEqual(timing['usage']['completion_tokens'], 10)

    def test_truncated_stream_not_success(self):
        with patch.object(w.urllib.request, 'urlopen', return_value=io.BytesIO(b'data: [DONE]\n')):
            with self.assertRaises(ValueError):
                w.stream_chat('http://127.0.0.1/v1', {}, 3)

    def report(self):
        row = dict(id='a', repeat=0, category='tool', status='ok', automatic_pass=True, human_pending=False, total_ms=1)
        return dict(schema=w.SCHEMA, completion='complete', case_ids=['a'], rounds=1,
                    conditions={'hardware':'h','runtime':'r','shared_load':'quiet'},
                    before={'mode':{'mode':'gpu'}}, after={'mode':'gpu'}, trials=[row])

    def test_compare_regression(self):
        a = self.report()
        b = copy.deepcopy(a)
        b['trials'][0]['automatic_pass'] = False
        self.assertEqual(w.compare(a,b)['decision'], 'reject')

    def test_compare_never_auto_accepts(self):
        a = self.report()
        self.assertEqual(w.compare(a,a)['decision'], 'review_required')

    def test_compare_detects_unpaired_and_incomplete(self):
        a = self.report()
        b = copy.deepcopy(a)
        b['trials'] = []
        self.assertEqual(w.compare(a,b)['decision'], 'incomplete')
        b = copy.deepcopy(a)
        b['completion'] = 'running'
        self.assertEqual(w.compare(a,b)['decision'], 'incomplete')

    def test_compare_mode_and_environment_mismatch(self):
        a = self.report()
        b = copy.deepcopy(a)
        b['after']['mode'] = 'cpu'
        self.assertEqual(w.compare(a,b)['decision'], 'incomparable')
        b = copy.deepcopy(a)
        b['conditions']['runtime'] = 'changed'
        self.assertEqual(w.compare(a,b)['decision'], 'incomparable')

    def test_invalid_suite_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'bad.json'
            w.write(path, {'schema':w.SCHEMA, 'cases':[]})
            with self.assertRaises(ValueError):
                w.load_suite(path)

    def test_encoding_loss_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'corrupted.json'
            case = self.case('greeting-dev')
            case['messages'][0]['content'] = '??????????'
            w.write(path, {'schema':w.SCHEMA, 'cases':[case]})
            with self.assertRaises(ValueError):
                w.load_suite(path)


if __name__ == '__main__':
    unittest.main()
