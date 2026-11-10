#!/usr/bin/env python3
"""Probe local Qwen vision on a disposable API. GPU mode temporarily moves the shared API to CPU."""
import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('benchmark_home', Path(__file__).with_name('benchmark-home.py'))
home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)

CODE = r"""
from pathlib import Path
import base64,hashlib,json,os,socket,struct,subprocess,threading,time,urllib.request,uuid,zlib
phase=PHASE
max_size=MAX_SIZE
root=Path.home()/'work/ciel-companion/server'
models=Path.home()/'models/llm'
projector=models/'mmproj-F16-Qwen3.5-35B-A3B.gguf'
assert projector.is_file(),'Provision the verified matching mmproj first'
assert (models/(projector.name+'.json')).is_file(),'Projector provenance sidecar missing'
with socket.socket() as sock:
    assert sock.connect_ex(('127.0.0.1',8098))!=0,'Trial port 8098 is already occupied'
def get(port,path):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path,timeout=5) as response:return json.load(response)
def mode(value):
    request=urllib.request.Request('http://127.0.0.1:8095/mode',data=json.dumps({'mode':value}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=240) as response:return json.load(response)
before=get(8095,'/mode')
assert before['ready'],'Shared API is not ready'
if phase=='gpu':
    assert before['mode']=='gpu','Do not override an existing CPU lease (for example singing)'
    assert not any(slot['is_processing'] for slot in get(8094,'/slots')),'Shared API is busy; retry later'
obj=json.loads(subprocess.check_output(['docker','inspect','ciel-local-llm-1'],text=True))[0]
name='ciel-vision-probe-'+uuid.uuid4().hex[:10]
out=root/'local-llm/data'/('vision-'+phase+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
out.mkdir(parents=True,exist_ok=False)
(out/'projector.json').write_text((models/(projector.name+'.json')).read_text())
report={'phase':phase,'source':PROVENANCE,'directory':str(out),'image':obj['Image'],'before':before,'requests':[],
        'conditions':'Synthetic geometric fixtures (sizes recorded per request). Image encoder stays on CPU. No application image handling or Minecraft world actions. Other services kept running; whole-GPU samples include their use.'}
stop=threading.Event();samples=[];created=False;switched=False

def png(blank=False,swapped=False,size=256):
    data=bytearray()
    for y in range(size):
        data.append(0)
        for x in range(size):
            sx=x*256/size;sy=y*256/size
            color=(255,255,255)
            if not blank:
                left=(sx-64)**2+(sy-128)**2<=40**2 if not swapped else 24<=sx<104 and 88<=sy<168
                right=152<=sx<232 and 88<=sy<168 if not swapped else (sx-192)**2+(sy-128)**2<=40**2
                if left:color=(255,0,0) if not swapped else (0,180,0)
                if right:color=(0,0,255) if not swapped else (255,0,0)
            data.extend(color)
    def chunk(kind,content):return struct.pack('!I',len(content))+kind+content+struct.pack('!I',zlib.crc32(kind+content)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',size,size,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(data))+chunk(b'IEND',b'')
# The source below is a raw string embedded in the orchestration script.

def sample():
    while not stop.is_set():
        try:
            raw=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(',')
            samples.append({'time':time.time(),'used_mib':int(raw[0]),'free_mib':int(raw[1]),'utilization':int(raw[2])})
        except Exception:pass
        stop.wait(0.5)

def request(label,picture=None,expected=None):
    prompt='Reply only OK.' if picture is None else 'Examine this image. Return JSON only with keys left, right, count. Describe each shape as lowercase English color and shape (circle or square). Count the colored shapes. For a blank image, left and right are null and count is zero.'
    content=prompt if picture is None else [{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(picture).decode()}}]
    body={'model':'vision-probe','messages':[{'role':'user','content':content}],'max_tokens':96 if picture else 8,'temperature':0,'stream':True,'stream_options':{'include_usage':True},'chat_template_kwargs':{'enable_thinking':False}}
    req=urllib.request.Request('http://127.0.0.1:8098/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    began=time.monotonic();first=None;parts=[];usage=timings=None
    with urllib.request.urlopen(req,timeout=120) as response:
        for line in response:
            if not line.startswith(b'data: '):continue
            data=line[6:].strip()
            if data==b'[DONE]':break
            value=json.loads(data)
            for choice in value.get('choices',[]):
                text=choice.get('delta',{}).get('content') or ''
                if text:
                    if first is None:first=time.monotonic()-began
                    parts.append(text)
            usage=value.get('usage') or usage;timings=value.get('timings') or timings
    reply=''.join(parts);result={'label':label,'seconds':round(time.monotonic()-began,3),'first_token_seconds':None if first is None else round(first,3),'reply':reply,'usage':usage,'timings':timings}
    if picture is not None:
        result['image_sha256']=hashlib.sha256(picture).hexdigest();result['expected']=expected
        try:
            parsed=json.loads(reply[reply.index('{'):reply.rindex('}')+1]);result['correct']=parsed==expected
        except (ValueError,KeyError):result['correct']=False
        (out/(label+'.png')).write_bytes(picture)
    assert reply,'Empty generation'
    report['requests'].append(result)
    print(json.dumps(result),flush=True)

thread=threading.Thread(target=sample,daemon=True)
try:
    if phase=='gpu':
        switched=True;mode('cpu');assert get(8095,'/mode')['mode']=='cpu'
        print('Shared API is temporarily serving CPU; GPU trial will be isolated on port 8098.',flush=True)
    context,parallel=(32768,2) if phase=='gpu' else (4096,1)
    cmd=['docker','run','-d','--name',name,'--label','ciel.test=local-vision','--network','host','--memory','48g','--cpus','16' if phase=='gpu' else '8','--no-healthcheck','-v',str(models)+':/models:ro','--entrypoint','/app/llama-server']
    if phase=='gpu':cmd+=['--gpus','all']
    args=['-m','/models/Qwen3.5-35B-A3B-Q4_K_M.gguf','--mmproj','/models/'+projector.name,'--no-mmproj-offload','--host','127.0.0.1','--port','8098','-c',str(context*parallel),'--parallel',str(parallel),'-t','8','-tb','16' if phase=='gpu' else '8','--jinja','--alias','vision-probe','--image-max-tokens','1024']
    args+=['-ngl','99','--n-cpu-moe','99'] if phase=='gpu' else ['-ngl','0']
    report.update(context_per_request=context,parallel=parallel,command_args=args)
    started=time.monotonic();created=True;subprocess.run(cmd+[obj['Image']]+args,check=True,stdout=subprocess.DEVNULL)
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        state=json.loads(subprocess.check_output(['docker','inspect',name,'--format','{{json .State}}'],text=True))
        if not state['Running']:raise RuntimeError('Trial exited; see server.log')
        try:
            props=get(8098,'/props')
            if props.get('modalities',{}).get('vision'):break
        except Exception:pass
        time.sleep(1)
    else:raise TimeoutError('Trial failed to become vision-ready')
    report['load_seconds']=round(time.monotonic()-started,3);thread.start()
    print('Isolated API ready; vision=true',flush=True)
    request('text-baseline')
    request('red-circle-blue-square',png(),{'left':'red circle','right':'blue square','count':2})
    request('blank',png(blank=True),{'left':None,'right':None,'count':0})
    if phase=='gpu':
        request('green-square-red-circle',png(swapped=True),{'left':'green square','right':'red circle','count':2})
        request('repeat-red-circle-blue-square',png(),{'left':'red circle','right':'blue square','count':2})
        if max_size==1024:
            for size in [512,1024]:
                request('red-circle-blue-square-'+str(size),png(size=size),{'left':'red circle','right':'blue square','count':2})
finally:
    stop.set()
    if thread.is_alive():thread.join(timeout=2)
    try:
        exists=subprocess.run(['docker','inspect',name],capture_output=True).returncode==0
        if created and exists:
            logs=subprocess.run(['docker','logs',name],capture_output=True,text=True)
            (out/'server.log').write_text(logs.stdout+'\n'+logs.stderr)
            memory=subprocess.run(['docker','exec',name,'cat','/sys/fs/cgroup/memory.peak'],capture_output=True,text=True)
            report['container_memory_peak_bytes']=int(memory.stdout.strip()) if memory.returncode==0 else None
            label=subprocess.check_output(['docker','inspect',name,'--format','{{index .Config.Labels "ciel.test"}}'],text=True).strip()
            assert label=='local-vision'
            subprocess.run(['docker','rm','-f',name],check=True,stdout=subprocess.DEVNULL)
    finally:
        if switched:mode(before['mode'])
    report.update(after=get(8095,'/mode'),gpu_samples=samples)
    if samples:report['whole_gpu_peak_mib']=max(s['used_mib'] for s in samples)
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print('Report:',out,flush=True)
    print('Shared API final state:',json.dumps(report['after']),flush=True)
if any(r.get('correct') is False for r in report['requests']):
    raise RuntimeError('Some image ground-truth checks failed; see report.json')
"""

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['cpu','gpu'])
    parser.add_argument('--max-size',type=int,choices=[256,1024],default=256,help='Add 512px and 1024px checks in GPU phase')
    args=parser.parse_args()
    import subprocess
    source={'git_commit':subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'rev-parse','HEAD'],text=True,cwd=ROOT).strip(),'script_sha256':__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest()}
    home.remote(CODE.replace('PHASE',repr(args.phase)).replace('MAX_SIZE',str(args.max_size)).replace('PROVENANCE',repr(source)))

if __name__=='__main__':main()
