"""Strict dispatch checks and append-only fixed entrypoint evaluation."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import AsyncMock, patch

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('discovery_benchmark',ROOT/'scripts/server/benchmark-tool-discovery.py')
runner=importlib.util.module_from_spec(spec)
with patch.dict(os.environ):spec.loader.exec_module(runner)


def capture():
    rows=[]
    for case,name in [('name','register_participant_name'),('minutes','start_minutes'),('history','search_conversation')]:
        schema={'name':name,'description':'Tool','parameters':{'type':'object','properties':{
            'name':{'type':'string'},'self_introduction':{'type':'boolean'}},
            'required':['name','self_introduction'],'additionalProperties':False}}
        rows.append({'case':case,'passed':True,'requests':[{'payload':{'tools':[{'type':'function','function':schema}]}}]})
    return {'trials':rows}


class DiscoveryBenchmarkTest(unittest.IsolatedAsyncioTestCase):
    def test_hybrid_exposure_is_stable_and_does_not_unlock_other_memory_tools(self):
        registry=runner.Registry(capture())
        status=copy.deepcopy(registry.tools['register_participant_name'])
        status.update(tool_id='get_speaker_status')
        status['schema']['name']='get_speaker_status'
        registry.tools['get_speaker_status']=status
        before=runner.exposed_schemas('hybrid',registry,set())
        self.assertEqual(before,runner.exposed_schemas('hybrid',registry,{'3','5','6'}))
        self.assertEqual([s['name'] for s in before],['discover','execute',*runner.COMMON])
        values={'name':'田中','self_introduction':True}
        tool=registry.tools['register_participant_name']
        self.assertFalse(registry.invoke(tool['tool_id'],tool['version'],values,set(),direct=runner.COMMON)['executed'])
        with self.assertRaises(ValueError):
            registry.invoke(tool['tool_id'],tool['version'],values,set())
        other=registry.tools['start_minutes']
        with self.assertRaises(ValueError):
            registry.invoke(other['tool_id'],other['version'],values,set(),direct=runner.COMMON)
        sibling=copy.deepcopy(tool);sibling['tool_id']='other_memory_tool'
        registry.tools[sibling['tool_id']]=sibling
        with self.assertRaises(ValueError):
            registry.invoke(sibling['tool_id'],sibling['version'],values,set(),direct=runner.COMMON)

    def test_dispatch_refuses_unknown_unloaded_stale_and_invalid_arguments(self):
        registry=runner.Registry(capture());name='register_participant_name';version=registry.tools[name]['version']
        good={'name':'田中','self_introduction':True}
        for tool,rev,values,loaded in [('unknown',version,good,{'3'}),(name,version,good,set()),
                                      (name,'old',good,{'3'}),(name,version,{'name':'田中'}, {'3'}),
                                      (name,version,{'name':'田中','self_introduction':'true'},{'3'}),
                                      (name,version,{**good,'person_id':'other'},{'3'})]:
            with self.assertRaises((ValueError,runner.fixture.jsonschema.ValidationError)):
                registry.invoke(tool,rev,values,loaded)
        self.assertEqual(registry.invoke(name,version,good,{'3'}),{'status':'validated_only','executed':False})

    async def test_fixed_schema_and_prior_messages_do_not_change_after_discovery(self):
        source=capture();registry=runner.Registry(source);name='register_participant_name'
        values={'name':'田中','self_introduction':True};version=registry.tools[name]['version']
        outputs=[('discover',{'service_id':'3'}),(name,values),(name,values),
                 ('discover',{'service_id':'3'}),('execute',{'tool_id':name,'version':version,'arguments':values}),
                 ('execute',{'tool_id':name,'version':version,'arguments':values})]
        snapshots=[]
        async def create(**kwargs):
            snapshots.append(copy.deepcopy(kwargs));tool,args=outputs.pop(0)
            call=Obj(id='call-'+str(len(snapshots)),function=Obj(name=tool,arguments=json.dumps(args)))
            message=Obj(tool_calls=[call],model_dump=lambda **_:{'role':'assistant','tool_calls':[
                {'id':call.id,'type':'function','function':{'name':tool,'arguments':json.dumps(args)}}]})
            return Obj(usage=Obj(model_dump=lambda:{'prompt_tokens':1}),choices=[Obj(message=message)])
        client=Obj(chat=Obj(completions=Obj(create=create)),close=AsyncMock())
        cases=[[('first','私の名前は田中です。',name,values),('repeat','もう一度同じ仮受付をお願いします。',name,values)]]
        with tempfile.TemporaryDirectory() as directory, patch.object(runner.fixture.models,'create_client',return_value=client),patch.object(runner,'SEQUENCES',cases):
            path=Path(directory)/'capture.json';path.write_text(json.dumps(source))
            output=Path(directory)/'result.json'
            await runner.run(Obj(capture=path,output=output,rounds=1))
            result=json.loads(output.read_text(encoding='utf8'))
        self.assertTrue(all(t['passed'] for t in result['trials']))
        self.assertNotEqual(snapshots[0]['tools'],snapshots[1]['tools'])
        for previous,current in zip(snapshots[3:],snapshots[4:]):
            self.assertEqual(previous['tools'],current['tools'])
            self.assertEqual(previous['messages'],current['messages'][:len(previous['messages'])])
        self.assertEqual(result['trials'][-1]['discoveries'],0)
