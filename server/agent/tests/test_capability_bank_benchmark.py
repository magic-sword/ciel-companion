"""Bank preparation cannot use user messages or execute a stale continuation."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('bank_benchmark',ROOT/'scripts/server/benchmark-capability-bank.py')
bank = importlib.util.module_from_spec(spec)
with patch.dict(os.environ):
    spec.loader.exec_module(bank)


def response(name):
    return Obj(usage=Obj(model_dump=lambda:{'prompt_tokens':1}), choices=[Obj(message=Obj(
        tool_calls=[Obj(function=Obj(name=name,arguments='{}'))]))])


def capture():
    rows=[]
    for case,service,name in [('minutes','minutes','start'),('name','memory','register'),
                              ('history','history','search'),('status','memory','status')]:
        names=['register','status'] if service=='memory' else [name]
        def request(loaded,tool_names,expected):
            return {'loaded':loaded,'fixed':'fixed','warmup':'warmup only',
                'expected_calls':[{'name':expected,'arguments':{}}],
                'payload':{'messages':[{'role':'system','content':'fixed\ndynamic'},
                    {'role':'user','content':'private input '+case}],
                    'tools':[{'type':'function','function':{'name':n,'parameters':{'type':'object'}}} for n in tool_names]}}
        rows.append({'case':case,'passed':True,'requests':[request([],['load','alternate'],'load'),request([service],names,name)]})
    return {'trials':rows}


class BankBenchmarkTest(unittest.IsolatedAsyncioTestCase):
    async def test_all_profiles_precede_requests_and_exclude_user_context(self):
        sequence=['load','start','load','register','load','search','load','status']
        create=AsyncMock(side_effect=[response(n) for n in sequence+['never_execute']*3+sequence])
        client=Obj(chat=Obj(completions=Obj(create=create)),close=AsyncMock())
        with tempfile.TemporaryDirectory() as directory, patch.object(bank.fixture.models,'create_client',return_value=client):
            source=Path(directory)/'capture.json';source.write_text(json.dumps(capture()))
            output=Path(directory)/'result.json'
            await bank.run(Obj(capture=source,output=output,rounds=1))
            result=json.loads(output.read_text())
        self.assertEqual(result['profiles'],3)
        self.assertTrue(all(t['passed'] for r in result['rounds'] for t in r['trials']))
        for call in create.call_args_list[8:11]:
            self.assertEqual(call.kwargs['max_tokens'],1)
            text=json.dumps(call.kwargs['messages'])
            self.assertNotIn('private input',text)
            self.assertNotIn('dynamic',text)
        self.assertEqual(len(create.call_args_list),19)

    async def test_changed_route_does_not_replay_captured_continuation(self):
        create=AsyncMock(return_value=response('alternate'))
        client=Obj(chat=Obj(completions=Obj(create=create)),close=AsyncMock())
        with tempfile.TemporaryDirectory() as directory, patch.object(bank.fixture.models,'create_client',return_value=client):
            source=Path(directory)/'capture.json';source.write_text(json.dumps(capture()))
            output=Path(directory)/'result.json'
            await bank.run(Obj(capture=source,output=output,rounds=1))
            result=json.loads(output.read_text())
        self.assertTrue(all(not t['passed'] for r in result['rounds'] for t in r['trials']))
        self.assertEqual(create.await_count,11)  # 8 routing requests and 3 preparations only
