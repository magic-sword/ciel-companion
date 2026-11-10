#!/usr/bin/env python3
"""Compare role-prefix changes with trailing role instructions on the shared API.

Synthetic text/JSON workload, not an evaluation of real memory or personality.
No tools execute. Each round uses a fresh prefix; ordinary caches stay intact.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request


def request(body, base):
    req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(body).encode(),
        headers={'Content-Type':'application/json','X-Ciel-Work-Class':'foreground'})
    start=time.monotonic();text=[];first=None;usage=None;timings=None
    with urllib.request.urlopen(req,timeout=60) as response:
        for line in response:
            if not line.startswith(b'data: '):continue
            value=line[6:].strip()
            if value==b'[DONE]':break
            chunk=json.loads(value)
            usage=chunk.get('usage') or usage;timings=chunk.get('timings') or timings
            for choice in chunk.get('choices',[]):
                delta=choice.get('delta',{}).get('content')
                if delta:
                    if first is None:first=time.monotonic()-start
                    text.append(delta)
    return {'seconds':time.monotonic()-start,'first_delta_seconds':first,
            'text':''.join(text),'usage':usage,'timings':timings}


def payload(common,history,role,layout):
    instruction={'talk':'会話担当。目的地の座標を答える。',
                 'notes':'メモ担当。依頼の目的地を抽出する。',
                 'thought':'内省担当。次の行動で目指す座標を整理する。'}[role]
    instruction+=' JSONだけで {"x":整数,"y":整数,"z":整数} を返す。操作や保存は実行しない。'
    if layout=='separate':
        messages=[{'role':'system','content':instruction+'\n'+common},
                  {'role':'user','content':history}]
    else:
        messages=[{'role':'system','content':common},{'role':'user','content':history},
                  {'role':'user','content':instruction}]
    return {'model':'local','messages':messages,'temperature':0,'seed':1729,'max_tokens':64,
            'response_format':{'type':'json_schema','json_schema':{'name':'destination','strict':True,
                'schema':{'type':'object','properties':{k:{'type':'integer'} for k in ['x','y','z']},
                          'required':['x','y','z'],'additionalProperties':False}}},
            'stream':True,'stream_options':{'include_usage':True},
            'chat_template_kwargs':{'enable_thinking':False}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prompt-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--base-url',default='http://127.0.0.1:8094')
    p.add_argument('--control-url',default='http://127.0.0.1:8095')
    args=p.parse_args()
    if args.output.exists() or args.rounds<1:p.error('New output and positive rounds required')
    def mode():
        with urllib.request.urlopen(args.control_url+'/mode',timeout=5) as r:return json.load(r)
    system='\n\n'.join((args.prompt_dir/(n+'.md')).read_text(encoding='utf8').strip()
                       for n in ['character','emotion','ciel_self','touch','talker','tasks','voice_first_sentence'])
    report={'scope':'Synthetic role switching, JSON extraction only; no actual memory writes, introspection quality or audio',
        'before':mode(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'prompt_sha256':hashlib.sha256(system.encode()).hexdigest(),'trials':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    if not report['before']['ready'] or report['before']['mode']!='gpu':raise RuntimeError('Ready GPU required')
    for repeat in range(args.rounds):
        modes=['talk-only','separate','trailing']
        for layout in modes[repeat%3:]+modes[:repeat%3]:
            tag=hashlib.sha256(f'{args.output}/{repeat}/{layout}'.encode()).hexdigest()[:16]
            common='Evaluation '+tag+'\n'+system
            history='利用者: 目的地は x=-12, y=64, z=7 です。\nシエル: 座標を確認したよ。'
            sequence=['talk','talk','talk','talk'] if layout=='talk-only' else ['talk','notes','thought','talk']
            for step,role in enumerate(sequence):
                # Include a changing suffix so an identical response cache cannot
                # masquerade as reuse of an earlier shared prefix.
                current=history+f'\n今回の処理番号: {step}'
                row={'repeat':repeat,'layout':layout,'role':role,'step':step}
                report['trials'].append(row)
                try:
                    row.update(request(payload(common,current,role,'trailing' if layout=='trailing' else 'separate'),args.base_url))
                    row['passed']=json.loads(row['text'])=={'x':-12,'y':64,'z':7}
                except Exception as e:row.update(passed=False,error=type(e).__name__)
                row['mode']=mode();save()
                if row['mode']['generation']!=report['before']['generation']:raise RuntimeError('Inference generation changed')
                print(repeat,layout,step,role,round(row.get('seconds',0),3),row['passed'],flush=True)
    report['after']=mode();save()


if __name__=='__main__':main()
