import importlib.util
import json
from pathlib import Path
import time
from types import SimpleNamespace
import unittest

import httpx

path = Path(__file__).resolve().parents[1] / 'continuation.py'
spec = importlib.util.spec_from_file_location('continuation_benchmark', path)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class BenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def simulate(self, decisions, case=None, finish='stop'):
        self.requests = []
        def handler(request):
            self.requests.append(json.loads(request.content))
            value = decisions.pop(0)
            return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(value)},
                'finish_reason': finish}], 'usage': {'completion_tokens': 10}})
        args = SimpleNamespace(model='local', max_steps=8, max_tokens=300, temperature=0,
                               base_url='http://localhost')
        case = case or dict(id='example', events=[dict(role='user', content='Hello')])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await bench.sample(client, args, case, 'loop', 0, time.monotonic()+10)

    async def test_wait_ends_generation_and_unknown_quality_remains_missing(self):
        trace = await self.simulate([dict(say=[], act=dict(kind='none'), next='wait')])
        self.assertEqual(trace['status'], 'complete')
        self.assertEqual(len(self.requests), 1)
        self.assertIsNone(trace['quality'])
        self.assertIsNone(bench.summarize({'trials': [trace]})[0]['cached_tokens'])

    async def test_continuation_keeps_existing_messages_as_prefix(self):
        def answer(text, next):
            return dict(say=[dict(feeling='neutral', text=text)], act=dict(kind='none'), next=next)
        trace = await self.simulate([answer('First.', 'continue'), answer('Last.', 'wait')])
        self.assertEqual(trace['status'], 'complete')
        first, second = [r['messages'] for r in self.requests]
        self.assertEqual(first, second[:len(first)])
        self.assertEqual(trace['checks']['first_phase_spoken_turns'], 2)

    async def test_tool_wait_still_reviews_result_and_completes(self):
        trace = await self.simulate([
            dict(say=[], act=dict(kind='load', service_ids=['research']), next='wait'),
            dict(say=[], act=dict(kind='call', tool_id='search_fixture', arguments={'query': 'garden'}), next='wait'),
            dict(say=[dict(feeling='neutral', text='Nine.')], act=dict(kind='complete', evidence=['r2']), next='wait')
        ], dict(id='search', fixture=dict(status='ok', summary='Nine.'),
                events=[dict(role='user', content='Search opening time.')]))
        self.assertEqual(trace['status'], 'complete')
        self.assertEqual(len(trace['calls']), 1)
        self.assertTrue(trace['checks']['successful_result_observed'])
        self.assertEqual(len(self.requests), 3)

    async def test_truncation_is_failure_not_a_short_good_answer(self):
        trace = await self.simulate([dict(say=[], act=dict(kind='none'), next='wait')], finish='length')
        self.assertEqual(trace['status'], 'failed')
        self.assertIn('generation_truncated', trace['error'])
        self.assertIsNone(trace['quality'])

    async def test_invalid_decision_does_not_retry_or_dispatch(self):
        trace = await self.simulate([dict(say=[], act=dict(kind='call', tool_id='anything'), next='continue')])
        self.assertEqual(trace['status'], 'failed')
        self.assertEqual(trace['calls'], [])
        self.assertEqual(len(self.requests), 1)

    def test_suite_ids_unique_and_holdout_present(self):
        cases = bench.load_cases()
        self.assertEqual(len(cases), len({c['id'] for c in cases}))
        self.assertEqual({c['split'] for c in cases}, {'dev', 'holdout'})


if __name__ == '__main__':
    unittest.main()
