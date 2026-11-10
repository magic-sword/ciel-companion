"""Preparation must not execute model output or hide its cost."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('cache_benchmark', ROOT/'scripts/server/benchmark-conversation-tools.py')
runner = importlib.util.module_from_spec(spec)
with patch.dict(os.environ):
    spec.loader.exec_module(runner)


class CacheBenchmarkTest(unittest.IsolatedAsyncioTestCase):
    def test_shortening_preserves_nested_argument_constraints(self):
        schema = {'name':'test', 'description':'Short\nDetails', 'parameters':{
            'type':'object', 'additionalProperties':False, 'required':['count'],
            'properties':{'count':{'type':'integer','minimum':1,'description':'Count\nMore'}}}}
        short = runner.compact_schema(schema)
        runner.jsonschema.validate({'count':1}, short['parameters'])
        for invalid in ({}, {'count':0}, {'count':'1'}, {'count':1,'other':True}):
            with self.assertRaises(runner.jsonschema.ValidationError):
                runner.jsonschema.validate(invalid, short['parameters'])
        self.assertEqual(schema['description'], 'Short\nDetails')

    async def test_preparation_output_is_discarded_and_cost_separated(self):
        def response(name, arguments):
            return Obj(usage=Obj(model_dump=lambda: {'prompt_tokens':10}), choices=[Obj(message=Obj(
                content=None, tool_calls=[Obj(id='fixture',function=Obj(name=name,arguments=json.dumps(arguments)))]))])
        create = AsyncMock(side_effect=[
            response('must_not_execute', {}),
            response('load_capabilities', {'service_ids':['3']}),
            response('must_not_execute', {}),
            response('register_participant_name', {'name':'田中','self_introduction':True}),
        ])
        client = Obj(chat=Obj(completions=Obj(create=create)), close=AsyncMock())
        with tempfile.TemporaryDirectory() as directory, patch.object(runner.models,'create_client',return_value=client), \
                patch.object(runner.models,'LOCAL_TEST',True), patch.object(runner.models,'is_local',return_value=True):
            path = Path(directory)/'result.json'
            await runner.run(Obj(output=path, rounds=1, variant='prepared', cases=['name'],fresh_loaded_prefix=True))
            trial = json.loads(path.read_text(encoding='utf8'))['trials'][0]
        self.assertTrue(trial['passed'])
        self.assertEqual([c['name'] for c in trial['calls']], ['load_capabilities','register_participant_name'])
        self.assertEqual(len(trial['requests']), 2)
        self.assertTrue(all(r['preparation'] is not None for r in trial['requests']))
        self.assertGreaterEqual(trial['seconds'], sum(r['seconds']+r['preparation']['seconds'] for r in trial['requests']))
        prime = create.call_args_list[0].kwargs
        self.assertEqual(prime['max_tokens'],1)
        self.assertNotIn('田中',prime['messages'][1]['content'])
        self.assertNotIn('"loaded":',prime['messages'][0]['content'])
        second_prime = create.call_args_list[2].kwargs['messages'][0]['content']
        second_request = create.call_args_list[3].kwargs['messages'][0]['content']
        self.assertTrue(second_prime.startswith('Evaluation context ID:'))
        self.assertTrue(second_request.startswith(second_prime))

    async def test_specialist_keeps_dynamic_catalog_and_user_message(self):
        def response(name, arguments):
            return Obj(usage=Obj(model_dump=lambda: {'prompt_tokens':10}), choices=[Obj(message=Obj(
                content=None, tool_calls=[Obj(id='fixture',function=Obj(name=name,arguments=json.dumps(arguments)))]))])
        create = AsyncMock(side_effect=[
            response('load_capabilities', {'service_ids':['3']}),
            response('register_participant_name', {'name':'田中','self_introduction':True}),
        ])
        client = Obj(chat=Obj(completions=Obj(create=create)), close=AsyncMock())
        with tempfile.TemporaryDirectory() as directory, patch.object(runner.models,'create_client',return_value=client), \
                patch.object(runner.models,'LOCAL_TEST',True), patch.object(runner.models,'is_local',return_value=True):
            await runner.run(Obj(output=Path(directory)/'result.json', rounds=1, variant='specialist', cases=['name'],fresh_loaded_prefix=False))
        request = create.call_args_list[1].kwargs
        self.assertTrue(request['messages'][0]['content'].startswith('あなたはシエルの道具選択係です。'))
        self.assertIn('"services":', request['messages'][0]['content'])
        self.assertIn('私の名前は田中です。', '\n'.join(m.get('content','') or '' for m in request['messages']))
        self.assertTrue(any(m['role']=='tool' for m in request['messages']))


if __name__ == '__main__':
    unittest.main()
