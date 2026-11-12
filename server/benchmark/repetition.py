"""Multi-turn recurrence benchmark using the actual local context renderer and SDK."""
import argparse
import copy
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlparse
from . import weight_space as w

SUITE=Path(__file__).with_name('weight_space')/'repetition-suite.json'


def load(path):
    suite=w.read(path);ids=set()
    if suite.get('schema')!='ciel-repetition-v1':raise ValueError('Unknown suite')
    for c in suite['cases']:
        if c['id'] in ids or not c['dialogue'] or not c.get('family'):raise ValueError('Invalid case')
        ids.add(c['id'])
        if c['split'] not in ('dev','validation'):raise ValueError('Invalid split')
        for t in c['dialogue']:
            if t['phase'] not in ('target','control') or type(t['switch']) is not bool or not t['rubric']:raise ValueError('Invalid turn')
    return suite


def renderer(agent_dir):
    sys.path.insert(0,str(agent_dir))
    import mind
    from livekit.agents import llm
    def render(system,history,context):
        ctx=llm.ChatContext();ctx.add_message(role='system',content=system)
        for i,m in enumerate(history):
            if i==len(history)-1 and context:ctx.add_message(role='system',content=context)
            ctx.add_message(role=m['role'],content=m.get('content',''))
        wire,_=mind.local_context(ctx,source=ctx).to_provider_format('openai')
        return wire
    return render,dict(mind_sha256=w.digest(mind.__file__),sdk_version=importlib.metadata.version('livekit-agents'))


def series(case,system,args,seed,render,chat=w.stream_chat):
    history=copy.deepcopy(case['messages']);turns=[]
    def sampled(url,payload,timeout):
        payload=dict(payload)
        # run_case appends an empty context newline; preserve the exact SDK system.
        payload['messages']=copy.deepcopy(payload['messages']);payload['messages'][0]=copy.deepcopy(wire[0])
        if args.sampling=='production':payload.pop('temperature',None)
        return chat(url,payload,timeout)
    for i,t in enumerate(case['dialogue']):
        if time.monotonic()+args.timeout>args.deadline:break
        history.append(dict(role='user',content=t['user']))
        wire=render(system,history,case.get('context',''))
        child=dict(id=case['id'],category='repetition',context='',messages=wire[1:],checks=[dict(type='no_calls')])
        row=w.run_case(child,wire[0]['content'],args,seed+i,chat=sampled)
        turns.append(dict(index=i,input=wire,phase=t['phase'],switch=t['switch'],rubric=t['rubric'],
                          response=row['messages'],status=row['status'],calls=row['calls'],measurements=row['measurements']))
        if row['status']!='ok' or row['calls'] or not any(m.get('content','').strip() for m in row['messages']):break
        history.extend(copy.deepcopy(row['messages']))
    ok=len(turns)==len(case['dialogue']) and all(t['status']=='ok' and not t['calls'] and any(m.get('content','').strip() for m in t['response']) for t in turns)
    return dict(id=case['id'],family=case['family'],seed=seed,status='ok' if ok else 'incomplete',turns=turns,expected_turns=len(case['dialogue']))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('validate','run'))
    p.add_argument('--suite',type=Path,default=SUITE);p.add_argument('--output',type=Path);p.add_argument('--conditions',type=Path)
    p.add_argument('--agent-dir',type=Path,default=w.ROOT/'server/agent');p.add_argument('--prompt-dir',type=Path)
    p.add_argument('--split',choices=('dev','validation'),default='dev');p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--sampling',choices=('production','deterministic'),default='production');p.add_argument('--case',action='append',dest='selected')
    p.add_argument('--base-url',default='http://127.0.0.1:8094/v1');p.add_argument('--wall-seconds',type=int,default=2700)
    a=p.parse_args();suite=load(a.suite)
    if not 1<=a.rounds<=10 or not 90<=a.wall_seconds<=7200:p.error('Invalid budget')
    cases=[c for c in suite['cases'] if c['split']==a.split]
    if a.selected:
        if set(a.selected)-{c['id'] for c in cases}:p.error('Unknown case in split')
        cases=[c for c in cases if c['id'] in a.selected]
    if a.mode=='validate':
        print(json.dumps(dict(cases=len(cases),series=len(cases)*a.rounds,requests=sum(len(c['dialogue']) for c in cases)*a.rounds,suite_sha256=w.digest(a.suite))));return
    if not a.output or not a.conditions:p.error('conditions and new output required')
    if urlparse(a.base_url).hostname not in ('127.0.0.1','localhost','::1'):p.error('Use loopback or SSH tunnel')
    conditions=w.read(a.conditions)
    if not conditions.get('weights_sha256') or len(conditions['weights_sha256'])!=64 or any(c not in '0123456789abcdef' for c in conditions['weights_sha256']):p.error('Actual weight hash required')
    render,source=renderer(a.agent_dir);directory=a.prompt_dir or a.agent_dir/'config/prompts'
    prompts={n:(directory/f'{n}.md').read_text(encoding='utf-8') for n in w.PROMPTS};system='\n'.join(prompts.values())
    a.output.mkdir(parents=True,exist_ok=False);snap=a.output/'sources';snap.mkdir()
    for f in (Path(__file__),Path(w.__file__),a.suite,a.agent_dir/'mind.py'):(snap/f.name).write_bytes(f.read_bytes())
    for n,text in prompts.items():(snap/f'{n}.md').write_text(text,encoding='utf-8')
    props=w.probe(a.base_url.removesuffix('/v1'),'/props');before=w.probe('http://127.0.0.1:8095','/mode')
    if not before.get('ready') or before.get('mode')!='gpu':raise ValueError('Require ready GPU')
    report=dict(schema='ciel-repetition-report-v1',created_utc=datetime.now(timezone.utc).isoformat(),suite_sha256=w.digest(a.suite),
        conditions=conditions,renderer=source,source_hashes={f.name:w.digest(f) for f in snap.iterdir()},
        prompt_sha256=hashlib.sha256(system.encode()).hexdigest(),split=a.split,rounds=a.rounds,case_ids=[c['id'] for c in cases],
        sampling=dict(mode=a.sampling,temperature=0 if a.sampling=='deterministic' else props.get('default_generation_settings',{}).get('params',{}).get('temperature'),
                      server_defaults=props.get('default_generation_settings'),max_tokens=384,timeout=90,seed=1729),
        template_sha256=hashlib.sha256(props.get('chat_template','').encode()).hexdigest(),before=before,completion='running',trials=[])
    args=SimpleNamespace(timeout=90,model='local',temperature=0,max_tokens=384,thinking=False,base_url=a.base_url,sampling=a.sampling,deadline=time.monotonic()+a.wall_seconds)
    try:
        for repeat in range(a.rounds):
            order=cases[:];random.Random(1729+repeat).shuffle(order)
            for c in order:
                if time.monotonic()+args.timeout>args.deadline:raise TimeoutError('Registered wall budget')
                seed=1729+repeat*1009+int(hashlib.sha256(c['id'].encode()).hexdigest()[:6],16)
                row=series(c,system,args,seed,render);row['repeat']=repeat;report['trials'].append(row)
                w.write(a.output/'report.json',report);print(c['id'],repeat,row['status'],flush=True)
        report['completion']='complete'
    finally:
        if report['completion']=='running':report['completion']='incomplete'
        report['after']=w.probe('http://127.0.0.1:8095','/mode')
        report['mode_consistent']=before.get('generation')==report['after'].get('generation') and report['after'].get('mode')=='gpu' and report['after'].get('ready') is True
        w.write(a.output/'report.json',report)


if __name__=='__main__':main()
