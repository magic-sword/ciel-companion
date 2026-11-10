#!/usr/bin/env python3
"""Temporarily compare cache settings on the shared GPU, restoring its container.

Synthetic inference only: no game tools execute and no microphone audio is used.
An idle GPU-mode service is required. Existing image, weights and capacity stay
fixed. The experiment briefly replaces only the inference container on 8094.
"""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('home', Path(__file__).with_name('benchmark-home.py'))
home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)

REMOTE = r'''
import hashlib,json,signal,subprocess,time,urllib.request,uuid
from pathlib import Path
def docker(*args):
    return subprocess.check_output(['docker',*args],text=True).strip()
def get(port,path):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/{path}',timeout=5) as r:return json.load(r)
def wait_ready():
    end=time.monotonic()+180
    while time.monotonic()<end:
        try:
            value=get(8095,'mode')
            if value.get('ready'):return value
        except Exception:pass
        time.sleep(1)
    raise RuntimeError('Inference readiness timeout')
original='ciel-local-llm-1'
before=get(8095,'mode')
if before['mode']!='gpu' or not before['ready']:
    raise RuntimeError('Idle GPU mode required; do not interrupt singing')
if any(s['is_processing'] for s in get(8094,'slots')):
    raise RuntimeError('Inference in use; retry later')
info=json.loads(docker('inspect',original))[0]
assert info['Config']['Labels']['com.docker.compose.service']=='local-llm'
name='ciel-cache-evaluation-'+uuid.uuid4().hex[:10]
out=Path.home()/'work/ciel-voice-evaluation/results'/name
out.mkdir(parents=True,exist_ok=False)
supervisor=out/'supervisor.py'
supervisor.write_text(SUPERVISOR)
report={'scope':'Synthetic tool generation and prefix reuse; no tool execution or audio',
        'image':info['Image'],'before':before,'runner_sha256':RUNNER_SHA,
        'supervisor_sha256':hashlib.sha256(SUPERVISOR.encode()).hexdigest(),
        'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),'trials':[]}
def save(): (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
def interrupted(signum,frame):raise KeyboardInterrupt()
signal.signal(signal.SIGTERM,interrupted)
signal.signal(signal.SIGINT,interrupted)
env=[v for v in info['Config']['Env'] if v.startswith('LOCAL_LLM_') and not v.startswith(('LOCAL_LLM_CACHE_RAM=','LOCAL_LLM_CHECKPOINT_STEP='))]
tool={'type':'function','function':{'name':'move_to','description':'指定座標へ移動する。',
      'parameters':{'type':'object','properties':{k:{'type':'integer'} for k in ['x','y','z']},'required':['x','y','z'],'additionalProperties':False}}}
stopped=False
try:
    docker('stop','--time','30',original);stopped=True
    for variant,cache,spacing in [('baseline',8192,8192),('checkpoints',8192,512),('capacity',32768,512)]:
        args=['run','-d','--name',name,'--network','host','--gpus','all','--volumes-from',original+':ro',
              '--mount',f'type=bind,src={supervisor},dst=/opt/local-llm/supervisor.py,readonly']
        for value in env+[f'LOCAL_LLM_CACHE_RAM={cache}',f'LOCAL_LLM_CHECKPOINT_STEP={spacing}']:args+=['-e',value]
        args+=[info['Image']]
        docker(*args)
        identity=wait_ready()
        if identity['mode']!='gpu' or identity['model']!=before['model']:raise RuntimeError('Mode/model changed')
        if identity.get('cache_ram_mib')!=cache or identity.get('checkpoint_step')!=spacing:
            raise RuntimeError('Requested cache settings were not applied')
        for repeat in range(ROUNDS):
            # Same fresh prefix per round across configurations; servers restart,
            # so each configuration starts without the prior configuration's cache.
            fixed=f'Evaluation {out.name} round {repeat}.\n'+PROMPT
            for phase,notice in [('prime','A'),('changed','B'),('changed-again','C')]:
                body={'model':'local','messages':[{'role':'system','content':fixed+'\n現在の状態: '+notice},
                    {'role':'user','content':'座標 x=-12, y=64, z=7 に移動して。'}],
                    'tools':[tool],'temperature':0,'seed':1729,'max_tokens':96,
                    'stream':True,'stream_options':{'include_usage':True},
                    'chat_template_kwargs':{'enable_thinking':False}}
                row={'variant':variant,'cache_mib':cache,'checkpoint_step':spacing,'repeat':repeat,'phase':phase}
                report['trials'].append(row)
                started=time.monotonic();calls={};first=None
                try:
                    req=urllib.request.Request('http://127.0.0.1:8094/v1/chat/completions',data=json.dumps(body).encode(),
                        headers={'Content-Type':'application/json','X-Ciel-Work-Class':'foreground'})
                    with urllib.request.urlopen(req,timeout=60) as response:
                        for line in response:
                            if not line.startswith(b'data: '):continue
                            value=line[6:].strip()
                            if value==b'[DONE]':break
                            chunk=json.loads(value)
                            if chunk.get('usage'):row['usage']=chunk['usage']
                            if chunk.get('timings'):row['timings']=chunk['timings']
                            for choice in chunk.get('choices',[]):
                                delta=choice.get('delta',{})
                                if first is None and (delta.get('content') or delta.get('tool_calls')):first=time.monotonic()-started
                                for call in delta.get('tool_calls',[]):
                                    item=calls.setdefault(call['index'],{'name':'','arguments':''})
                                    for k in item:item[k]+=call.get('function',{}).get(k,'') or ''
                    row['calls']=[{'name':c['name'],'arguments':json.loads(c['arguments'])} for c in calls.values()]
                    row['passed']=row['calls']==[{'name':'move_to','arguments':{'x':-12,'y':64,'z':7}}]
                except Exception as e:row.update(passed=False,error=type(e).__name__)
                row.update(seconds=time.monotonic()-started,first_delta_seconds=first)
                row['mode']=get(8095,'mode')
                if row['mode']['generation']!=identity['generation']:raise RuntimeError('Inference generation changed')
                save();print(variant,repeat,phase,round(row['seconds'],3),row['passed'],flush=True)
        logs=subprocess.run(['docker','logs',name],capture_output=True,text=True)
        (out/(variant+'.log')).write_text(logs.stdout+logs.stderr)
        docker('rm','-f',name)
finally:
    subprocess.run(['docker','rm','-f',name],capture_output=True)
    if stopped:
        docker('start',original)
        report['restored']=wait_ready()
        if report['restored']['model']!=before['model'] or report['restored']['mode']!=before['mode']:
            raise RuntimeError('Original inference state was not restored')
    save();print('RESULT',out,flush=True)
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds',type=int,default=3)
    args=parser.parse_args()
    if not 1 <= args.rounds <= 3:parser.error('rounds must be 1..3')
    import hashlib
    prompts=ROOT/'server/agent/config/prompts'
    names=['character','emotion','ciel_self','touch','talker','tasks','voice_first_sentence']
    prompt='\n\n'.join((prompts/(n+'.md')).read_text(encoding='utf8').strip() for n in names)
    supervisor=(ROOT/'server/local-llm/supervisor.py').read_text(encoding='utf8')
    values={'SUPERVISOR':supervisor,'PROMPT':prompt,'ROUNDS':args.rounds,
            'RUNNER_SHA':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    home.remote('\n'.join(k+'='+repr(v) for k,v in values.items())+'\n'+REMOTE)

if __name__=='__main__':main()
