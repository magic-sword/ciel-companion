"""Isolated baseline/candidate workers using the running image and staged source."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.request
import concurrent.futures
import threading

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('measurement', Path(__file__).with_name('voice_measure_home.py'))
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


def reuse(identity):
    source = (ROOT/'results'/identity).resolve()
    if source.parent != (ROOT/'results').resolve():
        raise ValueError('Invalid corpus run ID')
    folder = ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-refactor')
    folder.mkdir()
    for name in ['corpus.jsonl','smoke.jsonl','conditions.json']:
        shutil.copy2(source/name, folder/name)
    rows = [json.loads(line) for line in (source/'corpus.jsonl').read_text().splitlines()]
    for row in rows:
        name = row['audio']
        if Path(name).name != name:
            raise ValueError('Corpus audio must be a local filename')
        shutil.copy2(source/name, folder/name)
    (ROOT/'latest.txt').write_text(str(folder))
    measure.dump(folder/'before.json', measure.snapshot())
    print(folder)


def start(variant):
    (ROOT/'server/agent/data').mkdir(exist_ok=True)
    name = 'ciel-voice-'+variant
    port = 8098 if variant == 'baseline' else 8099
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',port)) == 0:
            raise RuntimeError('Evaluation worker port already in use')
    existing = measure.inspect(measure.DEV)
    env = dict(v.split('=',1) for v in existing['Config']['Env'] if '=' in v)
    env.update(CIEL_AGENT_NAME='ciel-voice-bench', CIEL_AGENT_PORT=str(port),
               CIEL_VOICE_FAST='1' if variant == 'fast' else '0',
               CIEL_DEBUG_LOG='1', CIEL_MINUTES_DISCORD_WEBHOOK='',
               CIEL_LOCAL_LLM_URL='http://127.0.0.1:8097/v1', CIEL_LOCAL_LLM_CONTROL='http://127.0.0.1:8096')
    folder = Path((ROOT/'latest.txt').read_text())/'workers'/variant
    folder.mkdir(parents=True, exist_ok=True)
    child_env = dict(os.environ, **env)
    command = ['docker','run','-d','--name',name,'--label','ciel.voice-evaluation=1','--network','host',
               '-v',str(ROOT/'server/agent')+':/app:ro','-v',str(folder)+':/app/data',
               '-v',str(measure.MODEL.parent)+':/models:ro']
    if existing['Config'].get('User'):
        command += ['--user',existing['Config']['User']]
    for key in env:
        command += ['-e',key]
    command.append(existing['Image'])
    subprocess.run(command,env=child_env,check=True,timeout=60)
    for _ in range(60):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port)) == 0:
                return
        if not measure.inspect(name)['State']['Running']:
            raise RuntimeError('Evaluation worker exited during startup')
        time.sleep(1)
    raise TimeoutError('Evaluation worker did not open its health port')


def stop(variant):
    name = 'ciel-voice-'+variant
    worker = measure.inspect(name)
    if worker['Config'].get('Labels',{}).get('ciel.voice-evaluation') != '1':
        raise RuntimeError('Not an evaluation worker')
    subprocess.run(['docker','stop','--time','90',name],check=True,timeout=110)
    subprocess.run(['docker','rm',name],check=True)


def proxy_start():
    for port in (8096,8097):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port)) == 0:
                raise RuntimeError('Evaluation ingress port already in use')
    image = measure.inspect('ciel-local-llm-1')['Image']
    subprocess.run(['docker','run','-d','--name','ciel-voice-proxy','--label','ciel.voice-evaluation=1',
                    '--network','host','-v',str(ROOT/'server/local-llm')+':/eval:ro',
                    '--entrypoint','/opt/vision-venv/bin/python',image,'/eval/evaluation_gateway.py'],check=True)
    for _ in range(30):
        try:
            info=measure.get(8096,'mode')
            if info.get('ready') and info.get('generation_scope')=='evaluation_ingress':
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError('Evaluation ingress did not start')


def proxy_stop():
    name='ciel-voice-proxy'
    info=measure.inspect(name)
    if info['Config'].get('Labels',{}).get('ciel.voice-evaluation')!='1':
        raise RuntimeError('Not an evaluation ingress')
    subprocess.run(['docker','stop',name],check=True)
    subprocess.run(['docker','rm',name],check=True)


def contention(variant):
    """Two bounded background generations plus one foreground, no model reload."""
    folder=Path((ROOT/'latest.txt').read_text())
    output=folder/('contention-'+variant+'.json')
    if output.exists():raise FileExistsError(output)
    fixtures=json.loads((ROOT/'server/benchmark/voice/contention.json').read_text())
    started=[threading.Event(),threading.Event()]
    def request(kind,signal=None):
        began=time.monotonic()
        work='background' if kind=='background' and variant=='fast' else 'foreground'
        req=urllib.request.Request('http://127.0.0.1:8097/v1/chat/completions',
            data=json.dumps(fixtures[kind]).encode(),
            headers={'Content-Type':'application/json','X-Ciel-Work-Class':work})
        with urllib.request.urlopen(req,timeout=30) as response:
            first=None
            for line in response:
                if not line.startswith(b'data: '):continue
                if line.strip()==b'data: [DONE]':break
                chunk=json.loads(line[6:])
                if any(c.get('delta',{}).get('content') for c in chunk.get('choices',[])):
                    if first is None:
                        first=time.monotonic()-began
                        if signal:signal.set()
            return dict(work_class=work,first_text_ms=None if first is None else first*1000,
                        total_ms=(time.monotonic()-began)*1000,
                        admission_ms=response.headers.get('X-Ciel-Admission-Ms'))
    before=measure.snapshot()
    if before['shared_api'].get('mode')!='gpu' or not before['shared_api'].get('ready'):
        raise RuntimeError('Contention trial requires ready GPU mode')
    if any(slot.get('is_processing') for slot in measure.get(8094,'slots')):
        raise RuntimeError('Shared inference is busy; do not inject competing load')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        background=[pool.submit(request,'background',event) for event in started]
        if not started[0].wait(25):raise TimeoutError('Background did not start')
        if variant=='baseline' and not started[1].wait(25):raise TimeoutError('Second background did not start')
        foreground=pool.submit(request,'foreground').result(timeout=30)
        rows=[future.result(timeout=30) for future in background]
    measure.dump(output,dict(variant=variant,foreground=foreground,background=rows,
                            before=before,after=measure.snapshot(),
                            limits='One contention trial; 2x128-token background + 4-token foreground; not voice end-to-end'))
    print(json.dumps(dict(variant=variant,foreground=foreground)))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['reuse','start','stop','live','proxy-start','proxy-stop','contention'])
    parser.add_argument('--variant',choices=['baseline','fast'],default='fast')
    parser.add_argument('--corpus-run',default='20261110T020907Z')
    parser.add_argument('--rounds',type=int,default=3)
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--tag')
    args=parser.parse_args()
    if args.action=='reuse':reuse(args.corpus_run)
    elif args.action=='proxy-start':proxy_start()
    elif args.action=='proxy-stop':proxy_stop()
    elif args.action=='contention':contention(args.variant)
    elif args.action=='start':start(args.variant)
    elif args.action=='stop':stop(args.variant)
    else:
        measure.DEV='ciel-voice-'+args.variant
        raise SystemExit(measure.run('live',args.rounds,args.smoke,True,variant=args.variant,tag=args.tag))
