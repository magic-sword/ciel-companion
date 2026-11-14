"""Prepare actual SDK wire messages locally; compare on the existing shared GPU."""
import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import time
import types
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from server.benchmark import weight_space as w


def prepare(path):
    sys.path.insert(0,str(ROOT/'server/agent'))
    import mind
    from livekit.agents import llm
    old=subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'show','HEAD:server/agent/mind.py'],cwd=ROOT)
    before=types.ModuleType('context_layout_before');before.__file__=mind.__file__
    exec(compile(old,'mind-before.py','exec'),before.__dict__)
    prompts=[ROOT/'server/agent/config/prompts'/f'{n}.md' for n in w.PROMPTS]
    system='\n'.join(p.read_text(encoding='utf-8') for p in prompts)
    topic=w.read(ROOT/'server/benchmark/weight_space/topic-state-suite.json')['cases']
    guard_ids={'json-dev','exact-dev','math-dev','stop-dev','status-dev','gesture-dev','gesture-failure-dev','submit-dev','injection-dev','negation-dev','comfort-dev','chat-no-tool-dev'}
    guards=[c for c in w.read(ROOT/'server/benchmark/weight_space/suite.json')['cases'] if c['id'] in guard_ids]
    jobs=[]
    for case in topic+guards:
        context=case.get('context','') or '[作業状態] 外部操作は未接続。'
        catalog=''
        if context.startswith('利用可能サービス:'):
            catalog,context=context.split('。',1)
            if '正式な能力定義:' in context:
                context,definitions=context.split('正式な能力定義:',1)
                catalog+='。正式な能力定義:'+definitions
        ctx=llm.ChatContext();ctx.add_message(role='system',content=system+('\n'+catalog if catalog else ''))
        messages=case['messages']
        for i,m in enumerate(messages):
            if i==len(messages)-1:ctx.add_message(role='system',content=context)
            ctx.add_message(role=m['role'],content=m['content'])
        # HEAD against the working tree: both send notes after the fixed system, so only the note format differs.
        for arm,convert in [('head',lambda c,source:before.local_context(c,source=source)),('candidate',lambda c,source:mind.local_context(c,source=source))]:
            wire,_=convert(ctx,source=ctx).to_provider_format('openai')
            jobs.append(dict(id=case['id'],arm=arm,group='topic' if case in topic else 'guard',case=case,wire=wire))
    sources={'mind-before.py':old.decode('utf-8'),'mind-after.py':Path(mind.__file__).read_text(encoding='utf-8')}
    sources.update({p.name:p.read_text(encoding='utf-8') for p in prompts})
    w.write(path,dict(jobs=jobs,sources=sources,source_hashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()}))
    print('Prepared actual SDK requests:',len(jobs))


def run(path,output):
    data=w.read(path);output.mkdir(parents=True,exist_ok=False)
    report=dict(schema='ciel-context-layout-v1',input_sha256=w.digest(path),source_hashes=data['source_hashes'],
                before=w.probe('http://127.0.0.1:8095','/mode'),completion='running',trials=[],cache=[])
    if report['before'].get('mode')!='gpu' or not report['before'].get('ready'):raise ValueError('GPU not ready')
    report['conditions']=w.read(ROOT/'conditions.json')
    report['conditions']['weights_sha256']=w.digest(Path.home()/'models/llm'/Path(report['before']['model']).name)
    report['conditions']['runtime']['props']=w.probe('http://127.0.0.1:8094','/props')
    args=SimpleNamespace(timeout=90,model='local',temperature=0,max_tokens=384,thinking=False,base_url='http://127.0.0.1:8094/v1')
    jobs=list(data['jobs']);random.Random(1733).shuffle(jobs);deadline=time.monotonic()+1800
    try:
        for j in jobs:
            if time.monotonic()+90>deadline:raise TimeoutError('Wall budget')
            c=dict(j['case']);c.setdefault('category',j['group']);c.setdefault('checks',[dict(type='no_calls')]);c.update(context='',messages=j['wire'][1:])
            row=w.run_case(c,j['wire'][0]['content'],args,1733)
            row.update(arm=j['arm'],group=j['group'],input=j['wire']);report['trials'].append(row)
            w.write(output/'report.json',report);print(j['id'],j['arm'],row['status'],flush=True)
        # Paired synthetic prefix probes: only state changes, no tools execute.
        marker='cache-layout-'+str(time.time_ns())
        for arm in ('head','candidate'):
            wire=next(j['wire'] for j in jobs if j['id']=='pending' and j['arm']==arm)
            for i in range(4):
                messages=json.loads(json.dumps(wire))
                messages[0]['content']=marker+'\n'+messages[0]['content']
                at=len(messages)-2
                messages[at]['content']+='\n[state version '+str(i)+']'
                payload=dict(model='local',messages=messages,temperature=0,max_tokens=1,seed=1733,
                             id_slot=0,cache_prompt=True,chat_template_kwargs={'enable_thinking':False})
                _,measure=w.stream_chat(args.base_url,payload,90)
                report['cache'].append(dict(arm=arm,index=i,measurements=measure))
        report['completion']='complete'
    finally:
        report['after']=w.probe('http://127.0.0.1:8095','/mode')
        report['mode_consistent']=report['before'].get('generation')==report['after'].get('generation') and all(report[k].get('mode')=='gpu' and report[k].get('ready') for k in ('before','after'))
        w.write(output/'report.json',report)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','remote','run'));a=p.parse_args()
    path=ROOT/'server/benchmark/data/context-layout-input.json';label='context-layout-06'
    if a.mode=='prepare':prepare(path)
    elif a.mode=='run':run(path,ROOT/'results'/label)
    else:
        spec=importlib.util.spec_from_file_location('home',Path(__file__).with_name('weight-space-home.py'));h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
        payload={str(f.relative_to(ROOT)).replace('\\','/'):base64.b64encode(f.read_bytes()).decode() for f in (Path(__file__),path)}
        h.remote('from pathlib import Path\nimport base64,subprocess\nroot='+h.DEST+'\npayload='+repr(payload)+'''
for name,value in payload.items():
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(base64.b64decode(value))
raise SystemExit(subprocess.run(['python3','-B','scripts/server/benchmark-context-layout.py','run'],cwd=root).returncode)
''')


if __name__=='__main__':main()
