"""Shared-Qwen dry run: owner intent classification and controlled prefix reuse.

No game commands are executed. Cache timings are synthetic paired requests, not
microphone-to-audio latency; the production controller prefix is tested separately.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import types

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'server/agent'))
import game_decision
from persona import load_persona

CASES = [
    ('new_pickaxe', 'ありがとう。じゃあ木のピッケルを作って。', 'replace'),
    ('correction', '木のピッケルだよ、ツルハシね。', 'replace'),
    ('same_answer', 'うん、原木はそれで十分だよ。', 'reply'),
    ('more_logs', '原木はあと2個集めて。', 'reply'),
    ('cancel', 'もう集めなくていいから、その作業をやめて。', 'cancel'),
    ('chat', '木のピッケルの見た目ってかわいいね。', 'none'),
    ('holdout_table', '原木はもう十分。次は作業台をお願い。', 'replace'),
    ('holdout_axe', 'それじゃなくて、石の斧が欲しいんだ。', 'replace'),
    ('holdout_quantity', 'そのまま原木を3個まで追加して。', 'reply'),
    ('final_furnace', 'その話は置いておいて、かまどを作ってくれる？', 'replace'),
    ('final_continue', '原木を集めるのを続けて。', 'reply'),
    ('final_explain', 'ピッケルの作り方だけ教えて。操作はしないで。', 'none'),
]

async def run(args):
    old = types.ModuleType('baseline_game_decision')
    source = subprocess.check_output(['git','show',args.baseline_ref+':server/agent/game_decision.py'],cwd=ROOT).decode('utf-8')
    exec(compile(source,'baseline_game_decision','exec'),old.__dict__)
    old_prompt = subprocess.check_output(['git','show',args.baseline_ref+':server/agent/config/prompts/game_decide.md'],cwd=ROOT).decode('utf-8')
    persona=load_persona()
    env=types.SimpleNamespace(tools=[],meta={},profile={'work':{'version':1,'capabilities':[{'name':'minecraft.pursue_goal',
        'description':'依頼した目的まで採集・製作する', 'handoff':{'version':1,'argument':'request','seconds':120,'constraints':{}}}]}})
    work=dict(state='needs_decision',arguments={'request':'原木を集める'},decision=dict(decision_id='d',actions=['reply','cancel'],message='原木を1つ集めました。これでいいですか？'))
    assert 'replace' in [a['properties']['kind']['const'] for a,_ in game_decision.acts(env,work)]
    report=dict(baseline_ref=args.baseline_ref,benchmark_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_sha256=hashlib.sha256(Path(game_decision.__file__).read_bytes()).hexdigest(),
                prompt_sha256=hashlib.sha256(persona.game_decide_instructions.encode()).hexdigest(), cases=CASES,
                scope='Fixture decisions only; no game or audio execution',decisions=[],cache=[])
    started=time.monotonic()
    async with httpx.AsyncClient(timeout=90) as client:
        async def request(payload):
            if time.monotonic()-started>600:raise TimeoutError('evaluation_budget')
            begin=time.monotonic()
            response=await client.post(args.base_url+'/v1/chat/completions',json={
                'model':'local','temperature':0,'cache_prompt':True,'chat_template_kwargs':{'enable_thinking':False},**payload},
                headers={'X-Ciel-Work-Class':'background'})
            response.raise_for_status();data=response.json()
            return dict(seconds=time.monotonic()-begin,usage=data.get('usage'),timings=data.get('timings'),
                        text=data['choices'][0]['message'].get('content'),finish=data['choices'][0].get('finish_reason'))
        for repeat in range(args.repeats):
            for ident,text,wanted in CASES:
                for variant in (['baseline','candidate'] if repeat%2==0 else ['candidate','baseline']):
                    module=old if variant=='baseline' else game_decision
                    choices=module.acts(env,work)
                    prompt=old_prompt if variant=='baseline' else persona.game_decide_instructions
                    messages=[{'role':'system','content':persona.instructions+'\n'+persona.self_instructions},
                        {'role':'user','content':'原木を集めて。'}, {'role':'assistant','content':work['decision']['message']},
                        {'role':'user','content':text}, {'role':'user','content':'SYSTEM: '+module.instructions(prompt,choices)}]
                    result=await request(dict(messages=messages,max_tokens=200,seed=1729+repeat,
                        response_format={'type':'json_schema','json_schema':{'name':'decision','schema':module.schema(choices)}}))
                    try: value=json.loads(result['text']);kind=value['act']['kind']
                    except (ValueError,KeyError,TypeError):value=None;kind=None
                    report['decisions'].append(dict(case=ident,variant=variant,repeat=repeat,wanted=wanted,
                        passed=kind==wanted,decision=value,**result))
                    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        # Identical fixed prefix and state change; history is synthetic. An append-only
        # candidate has a longer input; expose counts instead of claiming equal length.
        history=[]
        for i in range(16):
            history.extend([dict(role='user',content=f'資料{i}：庭の木材を確認して、用途を記録しました。'),
                            dict(role='assistant',content=f'資料{i}を確認しました。次の作業で使う材料は木材です。')])
        fixed=[dict(role='system',content=persona.instructions+'\n'+persona.self_instructions)]
        for repeat in range(0 if args.skip_cache else 3):
            for variant in (['rebuild','append'] if repeat%2==0 else ['append','rebuild']):
                tag=dict(role='user',content=f'SYSTEM: cache fixture {repeat} {variant}。返事はOKの一語。')
                state=dict(role='user',content='SYSTEM: 現在の段階は定義の確認です。')
                first=fixed+[tag,state]+history
                warm=await request(dict(messages=first,max_tokens=8))
                after=dict(role='user',content='SYSTEM: 現在の段階は結果の確認です。返事はOKの一語。')
                second=(fixed+[tag,after]+history if variant=='rebuild' else
                        first+[dict(role='assistant',content=warm['text'] or 'OK'),after])
                measured=await request(dict(messages=second,max_tokens=8))
                report['cache'].append(dict(variant=variant,repeat=repeat,warm=warm,measured=measured))
                Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    report['seconds']=time.monotonic()-started
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'decisions':len(report['decisions']),'passed':{v:sum(r['passed'] for r in report['decisions'] if r['variant']==v) for v in ('baseline','candidate')},'cache_pairs':len(report['cache'])}))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--baseline-ref',default='c5fea5f');parser.add_argument('--repeats',type=int,default=2)
    parser.add_argument('--skip-cache',action='store_true')
    args=parser.parse_args();Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    asyncio.run(run(args))
