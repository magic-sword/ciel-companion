#!/usr/bin/env python3
"""Stage/run/pull CPU-only ASR evaluation in a dedicated home-server directory."""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('benchmark_home',Path(__file__).with_name('benchmark-home.py'))
home=importlib.util.module_from_spec(spec);spec.loader.exec_module(home)

def stage():
    process=subprocess.Popen(home.ssh_args()+['mkdir -p ~/work/ciel-vosk-test && tar -xf - -C ~/work/ciel-vosk-test'],stdin=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdin,mode='w|') as archive:
            for source,name in [('server/agent/vosk_engine.py','vosk_engine.py'),('server/stt/measure.py','measure.py'),('server/stt/Dockerfile','Dockerfile'),('server/agent/vosk_stt.py','vosk_stt.py'),('server/agent/debug_log.py','debug_log.py'),('server/stt/check_livekit.py','check_livekit.py')]:
                archive.add(ROOT/source,arcname=name)
    finally:
        process.stdin.close()
    if process.wait():raise RuntimeError('ASR staging failed')

RUN = r"""
from pathlib import Path
import hashlib,json,os,subprocess,time,urllib.request,zipfile
root=Path.home()/'work/ciel-vosk-test'
models=Path.home()/'models/vosk'
models.mkdir(parents=True,exist_ok=True)
model=models/'vosk-model-small-ja-0.22'
if not model.is_dir():
    archive=root/'vosk-model-small-ja-0.22.zip'
    urllib.request.urlretrieve('https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip',archive)
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            if not (models/entry.filename).resolve().is_relative_to(models.resolve()):raise RuntimeError('Invalid model archive path')
        z.extractall(models)
    (root/'model-sha256.txt').write_text(hashlib.sha256(archive.read_bytes()).hexdigest())
subprocess.run(['docker','build','--network','host','-t','ciel-vosk-eval:0.3.45','.'],cwd=root,check=True)
run=root/'results'/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());run.mkdir(parents=True)
before=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader'],text=True).strip()
subprocess.run(['docker','run','--rm','--name','ciel-vosk-eval','--user',f'{os.getuid()}:{os.getgid()}','--cpus','2','--memory','3g','--network','host',
    '-v',str(models)+':/models:ro','-v',str(run)+':/results','ciel-vosk-eval:0.3.45'],check=True,timeout=240)
report=json.loads((run/'report.json').read_text());report.update(cpu_quota=2,memory_limit_gib=3,source_sha256={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ('vosk_engine.py','measure.py','Dockerfile')},gpu_before=before,
    gpu_after=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader'],text=True).strip())
(run/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
(root/'latest.txt').write_text(str(run))
print('VOSK_RESULT',str(run))
"""

INTEGRATION = r"""
from pathlib import Path
import os,subprocess
root=Path.home()/'work/ciel-vosk-test'
run=Path((root/'latest.txt').read_text())
code="import subprocess,sys,runpy; subprocess.run([sys.executable,'-m','pip','install','vosk==0.3.45'],check=True); sys.path.insert(0,'/eval'); runpy.run_path('/eval/check_livekit.py',run_name='__main__')"
subprocess.run(['docker','run','--rm','--name','ciel-vosk-sdk-eval','--cpus','2','--memory','3g','--network','host',
 '-v',str(root)+':/eval:ro','-v',str(run)+':/results','-v',str(Path.home()/'models/vosk')+':/models:ro',
 '--entrypoint','python','ciel-dev-agent','-c',code],check=True,timeout=180)
"""

def pull():
    code="""from pathlib import Path
import json
root=Path.home()/'work/ciel-vosk-test'
run=Path((root/'latest.txt').read_text())
report=json.loads((run/'report.json').read_text())
conditions=run/'conditions.json'
if conditions.exists():report.update(json.loads(conditions.read_text()))
integration=run/'livekit-integration.json'
if integration.exists():report['livekit_integration']=json.loads(integration.read_text())
print(json.dumps(report,ensure_ascii=False))
"""
    result=subprocess.run(home.ssh_args()+['python3 -'],input=code,text=True,capture_output=True,check=True)
    report=json.loads(result.stdout)
    out=ROOT/'server/benchmark/data/vosk-cpu';out.mkdir(parents=True,exist_ok=True)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(out/'report.json')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','run','integration','pull']);args=p.parse_args()
    if args.action=='stage':stage()
    elif args.action=='run':home.remote(RUN)
    elif args.action=='integration':home.remote(INTEGRATION)
    else:pull()
