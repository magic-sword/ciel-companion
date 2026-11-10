#!/usr/bin/env python3
"""Native dynamic schemas versus fixed entrypoints and append-only schema results.

All inventories come from synthetic actual-pipeline captures. Only validation is
performed; no MCP operation with side effects is executed.
"""
import argparse
import asyncio
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time

spec=importlib.util.spec_from_file_location('fixture',Path(__file__).with_name('benchmark-conversation-tools.py'))
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
ROOT=Path(__file__).resolve().parents[2]
COMMON=('register_participant_name','get_speaker_status')
DISCOVER={'name':'discover','description':'短いサービスIDで道具の定義と使い方を取得する。操作は実行しない。',
          'parameters':{'type':'object','properties':{'service_id':{'type':'string','enum':['3','5','6']}},'required':['service_id'],'additionalProperties':False}}
EXECUTE={'name':'execute','description':'探索結果のtool_id、version、argumentsで道具を呼ぶ。引数はその道具の完全なスキーマで検証される。',
         'parameters':{'type':'object','properties':{'tool_id':{'type':'string'},'version':{'type':'string'},'arguments':{'type':'object'}},
                       'required':['tool_id','version','arguments'],'additionalProperties':False}}
SEQUENCES=[
    [('name','私の名前は田中です。','register_participant_name',{'name':'田中','self_introduction':True}),
     ('status','私の名前は保存されている？','get_speaker_status',{}),
     ('history','この会話の最初に私が何と言ったか、履歴を検索して。','search_conversation',{'query':'','first_id':0,'last_id':0}),
     ('status_again','もう一度、私の名前が保存されているか道具で確認して。','get_speaker_status',{}),
     ('history_again','この会話の最初の発言を、もう一度履歴の道具で検索して。','search_conversation',{'query':'','first_id':0,'last_id':0})],
    [('minutes','今から議事録を取り始めてください。','start_minutes',{'template':'meeting','lookback_minutes':0}),
     ('negation','議事録という言葉を聞いたけど、今は何も始めないでね。',None,None)],
    [('greeting','こんにちは、シエル。',None,None)],
]


class Registry:
    def __init__(self,capture):
        self.services={};self.tools={}
        for case,sid in [('name','3'),('minutes','5'),('history','6')]:
            trial=next(t for t in capture['trials'] if t['case']==case)
            if not trial['passed']: raise ValueError('Capture failed')
            schemas=[t['function'] for t in trial['requests'][-1]['payload']['tools']
                     if t['function']['name'] not in ('load_capabilities','current_time')]
            self.services[sid]=[]
            for schema in schemas:
                name=schema['name'];version=hashlib.sha256(json.dumps(schema,sort_keys=True).encode()).hexdigest()[:12]
                self.tools[name]={'tool_id':name,'version':version,'schema':schema,'service_id':sid}
                self.services[sid].append(name)

    def invoke(self,name,version,arguments,loaded,*,direct=()):
        if name not in self.tools: raise ValueError('unknown_tool')
        tool=self.tools[name]
        if tool['service_id'] not in loaded and name not in direct: raise ValueError('not_discovered')
        if version!=tool['version']: raise ValueError('stale_version')
        fixture.jsonschema.validate(arguments,tool['schema']['parameters'])
        return {'status':'validated_only','executed':False}


def exposed_schemas(mode,registry,loaded):
    if mode=='hybrid':
        return [DISCOVER,EXECUTE]+[registry.tools[n]['schema'] for n in COMMON]
    if mode=='fixed':
        return [DISCOVER,EXECUTE]
    return [DISCOVER]+[registry.tools[n]['schema'] for sid in sorted(loaded) for n in registry.services[sid]]


async def run(args):
    if args.output.exists(): raise ValueError('Output must be new')
    capture=json.loads(args.capture.read_text(encoding='utf8'));registry=Registry(capture)
    prompt=ROOT/'server/benchmark/voice/tool-discovery-comparison.md'
    result={'scope':'Synthetic multi-turn selection and validation only; no real tool execution',
        'capture_sha256':hashlib.sha256(args.capture.read_bytes()).hexdigest(),
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'prompt_sha256':hashlib.sha256(prompt.read_bytes()).hexdigest(),'trials':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    client=fixture.models.create_client('mind')
    try:
        for repeat in range(args.rounds):
            modes=getattr(args,'modes',['native','fixed'])
            for mode in modes[repeat%len(modes):]+modes[:repeat%len(modes)]:
                for sequence_id,sequence in enumerate(SEQUENCES):
                    tag=hashlib.sha256(f'{args.output.resolve()}/{repeat}/{mode}/{sequence_id}'.encode()).hexdigest()[:16]
                    transport_path=ROOT/f'server/benchmark/voice/tool-discovery-{mode}.md'
                    transport=transport_path.read_text(encoding='utf8')
                    result.setdefault('transport_sha256',{})[mode]=hashlib.sha256(transport_path.read_bytes()).hexdigest()
                    messages=[{'role':'system','content':f'Evaluation ID: {tag}\n'+prompt.read_text(encoding='utf8')+'\n'+transport}]
                    loaded=set()
                    for case,text,expected,expected_args in sequence:
                        messages.append({'role':'user','content':text})
                        trial={'repeat':repeat,'mode':mode,'case':case,'requests':[],'calls':[],'discoveries':0,'invalid':[]}
                        started=time.monotonic()
                        try:
                            for step in range(4):
                                schemas=exposed_schemas(mode,registry,loaded)
                                began=time.monotonic()
                                response=await client.chat.completions.create(model=fixture.models.LOCAL_MODEL,
                                    messages=messages,tools=[{'type':'function','function':s} for s in schemas],
                                    temperature=0,seed=1729,max_tokens=180,timeout=60,
                                    extra_body={'chat_template_kwargs':{'enable_thinking':False}})
                                trial['requests'].append({'seconds':time.monotonic()-began,'usage':response.usage.model_dump(),
                                    'tools_sha256':hashlib.sha256(json.dumps(schemas,sort_keys=True).encode()).hexdigest()})
                                msg=response.choices[0].message;calls=msg.tool_calls or []
                                messages.append(msg.model_dump(exclude_none=True))
                                if not calls: break
                                executed=False
                                for call in calls:
                                    try:
                                        arguments=json.loads(call.function.arguments)
                                        published={s['name']:s for s in schemas}
                                        fixture.jsonschema.validate(arguments,published[call.function.name]['parameters'])
                                        if call.function.name=='discover':
                                            sid=arguments['service_id'];loaded.add(sid);trial['discoveries']+=1
                                            output={'service_id':sid,'executed':False,'tools':[
                                                registry.tools[n] if mode!='native' else {'tool_id':n,'published':True}
                                                for n in registry.services[sid]]}
                                        else:
                                            if call.function.name=='execute':
                                                name=arguments['tool_id'];version=arguments['version'];values=arguments['arguments']
                                            else:
                                                name=call.function.name;version=registry.tools[name]['version'];values=arguments
                                            direct=COMMON if mode=='hybrid' and call.function.name in COMMON else ()
                                            output=registry.invoke(name,version,values,loaded,direct=direct)
                                            trial['calls'].append({'name':name,'arguments':values});executed=True
                                    except Exception as error:
                                        trial['invalid'].append(type(error).__name__)
                                        output={'error':str(error)[:500],'executed':False}
                                    messages.append({'role':'tool','tool_call_id':call.id,'content':json.dumps(output,ensure_ascii=False)})
                                if executed: break
                        except Exception as error:
                            trial['error']=type(error).__name__
                        trial['seconds']=time.monotonic()-started
                        trial['passed']=not trial.get('error') and not trial['invalid'] and trial['calls']==(
                            [{'name':expected,'arguments':expected_args}] if expected else [])
                        if not expected and trial['discoveries']: trial['passed']=False
                        result['trials'].append(trial)
                        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
                        print(repeat,mode,case,trial['passed'],round(trial['seconds'],3),flush=True)
    finally:
        await client.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,default=3)
    parser.add_argument('--modes',nargs='+',choices=['native','fixed','hybrid'],default=['native','fixed'])
    args=parser.parse_args()
    if args.rounds<1: parser.error('rounds must be positive')
    asyncio.run(run(args))
