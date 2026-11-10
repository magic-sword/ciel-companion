#!/usr/bin/env python3
"""Configure and measure the shared GPU API; never redeploy Ciel agents.

Uses benchmark-home.py's private SSH settings. Inference stays on loopback;
another host can use an authenticated SSH tunnel to port 8094.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('benchmark_home',Path(__file__).with_name('benchmark-home.py'))
home=importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)

COMMON='''from pathlib import Path
import json,subprocess,time,urllib.request
root=Path.home()/'work/ciel-companion/server'
def get(path):
    with urllib.request.urlopen('http://127.0.0.1:'+path,timeout=5) as response:
        return json.load(response)
def gpu():
    return subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,memory.free,utilization.gpu','--format=csv,noheader'],text=True).strip()
def status():
    props=get('8094/props')
    return dict(get('8095/mode'),context=props['default_generation_settings']['n_ctx'],parallel=props['total_slots'],gpu=gpu())
'''

CONFIGURE='''
import hashlib
container=json.loads(subprocess.check_output(['docker','inspect','ciel-local-llm-1'],text=True))[0]
assert container['Config']['Labels']['com.docker.compose.service']=='local-llm'
assert container['Config']['Labels']['com.docker.compose.project']=='ciel'
if any(s['is_processing'] for s in get('8094/slots')):
    raise SystemExit('Shared API is in use; retry after current requests finish')
before=status()
if before['mode']!='gpu':
    raise SystemExit('Shared API is temporarily in CPU mode; retry after GPU use becomes available')
out=root/'local-llm/data'/('shared-gpu-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
out.mkdir(parents=True,exist_ok=False)
files=['compose.yaml','.env','local-llm/supervisor.py','local-llm/gateway.py','local-llm/Dockerfile']
original={name:(root/name).read_bytes() if (root/name).exists() else None for name in files}
for name,content in original.items():
    if content is None:continue
    backup=out/'backup'/name
    backup.parent.mkdir(parents=True,exist_ok=True)
    backup.write_bytes(content)
    backup.chmod(0o600)
compose=['docker','compose','--env-file','.env.shared','--env-file','.env','--profile','local-llm']
def command(*args):
    subprocess.run(compose+list(args),cwd=root,check=True,timeout=300)
def wait_ready(context,parallel,mode='gpu'):
    for _ in range(120):
        try:
            info=status()
            if info['ready'] and info['mode']==mode and info['context']==context and info['parallel']==parallel:
                return info
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError('Shared GPU API did not reach requested capacity')
try:
    for name,content in PAYLOAD.items():
        (root/name).write_text(content)
    text=(root/'compose.yaml').read_text()
    text=text.replace('LOCAL_LLM_CTX=${LOCAL_LLM_CTX:-12288}','LOCAL_LLM_CTX=${LOCAL_LLM_CTX:-32768}')
    anchor='      - LOCAL_LLM_CONTROL_PORT=8095'
    assert text.count(anchor)==1, 'Unexpected local-llm service definition'
    for key,default in (('LOCAL_LLM_CTX','32768'),('LOCAL_LLM_PARALLEL','2'),('LOCAL_LLM_MODE','gpu'),('LOCAL_LLM_UBATCH','512')):
        if key+'=' not in text:
            text=text.replace(anchor,anchor+'\\n      - '+key+'=${'+key+':-'+default+'}')
    for key,value in [('LOCAL_LLM_INFERENCE_PORT','18094'),('LOCAL_LLM_MMPROJ','${LOCAL_LLM_MMPROJ-/models/mmproj-F16-Qwen3.5-35B-A3B.gguf}'),('LOCAL_LLM_IMAGE_MAX_EDGE','${LOCAL_LLM_IMAGE_MAX_EDGE:-256}')]:
        if key+'=' not in text:text=text.replace(anchor,anchor+'\\n      - '+key+'='+value)
    (root/'compose.yaml').write_text(text)
    settings={'LOCAL_LLM_CTX':str(CONTEXT),'LOCAL_LLM_PARALLEL':str(PARALLEL),'LOCAL_LLM_MODE':'gpu','LOCAL_LLM_UBATCH':str(UBATCH)}
    lines=(root/'.env').read_text().splitlines()
    lines=[line for line in lines if line.split('=',1)[0].strip() not in settings]
    lines += [key+'='+value for key,value in settings.items()]
    (root/'.env').write_text('\\n'.join(lines)+'\\n')
    (root/'.env').chmod(0o600)
    print('Building and restarting only local-llm; backup saved',flush=True)
    command('build','local-llm')
    command('up','-d','--no-deps','local-llm')
    after=wait_ready(CONTEXT,PARALLEL)
    assert after.get('ubatch') == UBATCH, 'Inference microbatch setting was not applied'
    info={'directory':str(out),'before':before,'after':after,'source':PROVENANCE,
          'source_sha256':{name:hashlib.sha256(content.encode()).hexdigest() for name,content in PAYLOAD.items()}}
    (out/'configuration.json').write_text(json.dumps(info,indent=2))
    print(json.dumps(info))
except BaseException:
    for name,content in original.items():
        if content is None:(root/name).unlink(missing_ok=True)
        else:(root/name).write_bytes(content)
    subprocess.run(['docker','tag',container['Image'],container['Config']['Image']],check=True)
    command('up','-d','--no-deps','--no-build','local-llm')
    restored=wait_ready(before['context'],before['parallel'],before['mode'])
    (out/'rollback.json').write_text(json.dumps(restored,indent=2))
    print('Restored previous GPU API configuration',flush=True)
    raise
'''

PROBE='''
import concurrent.futures,threading
out=root/'local-llm/data'/('capacity-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
out.mkdir(parents=True,exist_ok=False)
before=status()
assert before['ready'] and before['mode']=='gpu' and before['context']>=32768
samples=[]
stop=threading.Event()
def sample():
    while not stop.is_set():
        samples.append({'t':time.time(),'gpu':gpu()})
        stop.wait(0.5)
thread=threading.Thread(target=sample,daemon=True)
thread.start()
def request(label,repetitions):
    content='sample='+out.name+'/'+label+'\\n'+('oak_log=0 cobblestone=0 wooden_pickaxe=0 stone_pickaxe=0\\n'*repetitions)+'\\nReply only OK.'
    body={'model':'local','messages':[{'role':'system','content':'The following is synthetic state. Reply only OK.'},{'role':'user','content':content}],
          'temperature':0,'max_tokens':32,'stream':True,'stream_options':{'include_usage':True},'chat_template_kwargs':{'enable_thinking':False}}
    req=urllib.request.Request('http://127.0.0.1:8094/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    started=time.monotonic()
    first=usage=timings=None
    result=[]
    with urllib.request.urlopen(req,timeout=240) as response:
        for line in response:
            if not line.startswith(b'data: '): continue
            value=line[6:].strip()
            if value==b'[DONE]': break
            chunk=json.loads(value)
            for choice in chunk.get('choices',[]):
                text=choice.get('delta',{}).get('content') or ''
                if text:
                    if first is None: first=time.monotonic()-started
                    result.append(text)
            usage=chunk.get('usage') or usage
            timings=chunk.get('timings') or timings
    if not result: raise RuntimeError('Empty generation')
    return {'label':label,'seconds':round(time.monotonic()-started,3),'first_token_seconds':None if first is None else round(first,3),'usage':usage,'timings':timings,'reply':''.join(result)}
results=[]
try:
    results.append(request('short',20))
    print('Short request finished',flush=True)
    results.append(request('long-single',LONG_REPEATS))
    print('Long single request finished',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results.extend(pool.map(lambda label:request(label,LONG_REPEATS),['long-concurrent-a','long-concurrent-b']))
finally:
    stop.set()
    thread.join(timeout=3)
    report={'before':before,'after':status(),'requests':results,'gpu_samples':samples,
            'conditions':'Existing Ciel, Minecraft and Irodori kept running; synthetic requests; distinct prefixes; cache retained; two concurrent API clients. Not a full Minecraft benchmark.'}
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'directory':str(out),'before':before,'after':report['after'],'requests':results,'samples':len(samples)}))
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['status','configure','probe','pull'])
    ap.add_argument('--context',type=int,default=32768,choices=[16384,32768])
    ap.add_argument('--parallel',type=int,default=2,choices=[1,2,4])
    ap.add_argument('--ubatch',type=int,default=512,choices=[128,256,512])
    ap.add_argument('--long-repeats',type=int,default=1400,choices=[700,1400],help='Synthetic input size: about 14.7k or 29.4k tokens')
    args=ap.parse_args()
    if args.action=='pull':
        import tarfile,time
        dest=ROOT/'server/benchmark/data'/('shared-api-import-'+str(time.time_ns()))
        dest.mkdir(parents=True)
        p=subprocess.Popen(home.ssh_args()+['tar --exclude=backup --exclude=*.env -cf - -C ~/work/ciel-companion/server/local-llm data'],stdout=subprocess.PIPE)
        with tarfile.open(fileobj=p.stdout,mode='r|') as archive:
            archive.extractall(dest,filter='data')
        while p.stdout.read(65536): pass
        p.stdout.close()
        if p.wait(): raise RuntimeError('Download failed')
        print(dest)
        return
    if args.action=='status':
        home.remote(COMMON+"\nprint(json.dumps(status()))\n")
    elif args.action=='probe':
        home.remote(COMMON+'\nLONG_REPEATS='+str(args.long_repeats)+'\n'+PROBE)
    else:
        payload={name:(ROOT/'server'/name).read_text(encoding='utf-8') for name in ('local-llm/supervisor.py','local-llm/gateway.py','local-llm/Dockerfile')}
        provenance={'git_commit':subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'working_tree':True}
        home.remote(COMMON+'\nPAYLOAD='+repr(payload)+'\nPROVENANCE='+repr(provenance)+'\nCONTEXT='+str(args.context)+'\nPARALLEL='+str(args.parallel)+'\nUBATCH='+str(args.ubatch)+'\n'+CONFIGURE)

if __name__=='__main__':
    main()
