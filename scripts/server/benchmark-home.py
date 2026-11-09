#!/usr/bin/env python3
"""Stage and smoke-test the benchmark on the configured home server.

Uses scripts/server/.env.local; never deploys or restarts production services.
"""
import argparse
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server'))
from benchmark.run import provenance, load_tasks


def ssh_args():
    config = {}
    for line in (ROOT/'scripts/server/.env.local').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key,value = line.split('=',1)
            config[key.strip()] = value.strip().strip('"').strip("'")
    target = os.environ.get('CIEL_SERVER_HOST') or config.get('CIEL_SERVER_HOST','')
    if not target or target.startswith('-') or not re.fullmatch(r'[A-Za-z0-9_.@:\[\]-]+',target):
        raise ValueError('Invalid or missing configured SSH target')
    args = ['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o','ConnectTimeout=15']
    key = os.environ.get('CIEL_SSH_KEY',config.get('CIEL_SSH_KEY',''))
    if key:
        args += ['-i',os.path.expanduser(key),'-o','IdentitiesOnly=yes']
    return args+[target]


def remote(code):
    result = subprocess.run(ssh_args()+['python3 -'],input=code,text=True)
    if result.returncode:
        raise SystemExit(result.returncode)


INSPECT = '''
from pathlib import Path
import json, socket, subprocess, sys
base=Path.home()/'work/ciel-companion/server'
accepted=False
p=base/'.env.minecraft'
if p.exists():
    accepted=any(s.strip().upper()=='MINECRAFT_EULA=TRUE' for s in p.read_text().splitlines())
ports={}
for port in (25566,25576,8772,8773,3008,8092,8096,8097):
    with socket.socket() as s:
        s.settimeout(1)
        ports[port]=s.connect_ex(('127.0.0.1',port))!=0
names=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
print(json.dumps({'python':sys.version.split()[0],'existing_eula_consent':accepted,
    'agent_credentials_present':(base/'agent/.env').is_file(),'benchmark_ports_free':ports,'containers':names},indent=2))
'''

SETUP = '''
from pathlib import Path
import os, secrets, subprocess, json
base=Path.home()/'work/ciel-companion/server'
dest=Path.home()/'work/ciel-companion-benchmark/server'
consent=base/'.env.minecraft'
if not consent.is_file() or not any(s.strip().upper()=='MINECRAFT_EULA=TRUE' for s in consent.read_text().splitlines()):
    raise SystemExit('Existing home-server EULA consent was not found; benchmark server was not started')
credentials=dest/'agent/.env'
if not credentials.exists():
    credentials.symlink_to(base/'agent/.env')
settings=dest/'.env.benchmark'
if not settings.exists():
    model='unspecified'
    try:
        env=json.loads(subprocess.check_output(['docker','inspect','ciel-local-llm-1','--format','{{json .Config.Env}}'],text=True))
        values=dict(s.split('=',1) for s in env if '=' in s)
        model=Path(values.get('LOCAL_LLM_MODEL','unspecified')).name
    except (subprocess.CalledProcessError,ValueError):
        pass
    fd=os.open(settings,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        f.write('MINECRAFT_EULA=TRUE\\nCIEL_BENCH_RCON_PASSWORD='+secrets.token_hex(24)+
                '\\nCIEL_BENCH_BACKEND=local\\nCIEL_BENCH_LOCAL_MODEL=local\\nCIEL_BENCH_LOCAL_TIMEOUT=600\\nCIEL_BENCH_MODEL_ID='+model+
                '\\nCIEL_BENCH_LLM_FILE='+model+'\\nCIEL_BENCH_LLM_CTX=32768\\nCIEL_BENCH_LLM_URL=http://127.0.0.1:8096/v1\\n')
print('Benchmark staged separately; home-server consent reused, credentials linked, dedicated configuration ready')
'''


def stage():
    command = 'mkdir -p ~/work/ciel-companion-benchmark/server && tar -xf - -C ~/work/ciel-companion-benchmark/server'
    process = subprocess.Popen(ssh_args()+[command],stdin=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdin,mode='w|') as archive:
            for path in sorted((ROOT/'server').rglob('*')):
                relative = path.relative_to(ROOT/'server')
                if any(part in ('data','node_modules','__pycache__','.venv') for part in relative.parts):
                    continue
                if path.is_file() and not path.is_symlink() and not (path.name.startswith('.env') and not path.name.endswith('.example')):
                    archive.add(path,arcname=relative.as_posix(),recursive=False)
            payload=json.dumps(provenance()).encode()
            info=tarfile.TarInfo('benchmark/staged-provenance.json')
            info.size=len(payload)
            archive.addfile(info,io.BytesIO(payload))
    finally:
        process.stdin.close()
        if process.wait():
            raise RuntimeError('Benchmark staging failed')
    remote(SETUP)


def smoke(mode, task_id='gather_logs', seconds=240):
    # Use a new result directory, and only the dedicated compose project/services.
    code = '''
from pathlib import Path
import subprocess, time, urllib.request
root=Path.home()/'work/ciel-companion-benchmark/server'
compose=['docker','compose','--env-file','.env.benchmark','-f','compose.benchmark.yaml','--profile','runner','--profile','conversation','--profile','local']
def run(*args):
    result=subprocess.run(compose+list(args),cwd=root)
    if result.returncode:
        raise SystemExit(result.returncode)
run('build','body-bench','benchmark-runner' MODE_BUILD)
LLM_START
run('up','-d','minecraft-bench','body-bench' MODE_UP)
# Wait for the bot to join before asking the scorer to reset the arena.
for attempt in range(90):
    output=subprocess.check_output(compose+['exec','-T','minecraft-bench','rcon-cli','list'],cwd=root,text=True)
    if 'Ciel_Debug' in output:
        break
    time.sleep(1)
else:
    raise SystemExit('Benchmark bot did not join')
run('run','--rm','--no-deps','-T','benchmark-runner','--mode','MODE_VALUE','--task','TASK_ID',
    '--seed','11','--repeats','1','--seconds','SECONDS_VALUE','--output','/workspace/server/benchmark/data/results/smoke-MODE_VALUE-'+str(time.time_ns()))
'''
    code=code.replace('MODE_BUILD',",'agent-bench','llm-bench'" if mode=='conversation' else '')
    code=code.replace('MODE_UP',",'agent-bench'" if mode=='conversation' else '')
    code=code.replace('LLM_START', '''run('up','-d','llm-bench')
for attempt in range(180):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8096/health',timeout=2) as response:
            if response.status==200:
                break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit('Dedicated CPU LLM did not become ready')
''' if mode=='conversation' else '')
    remote(code.replace('MODE_VALUE',mode).replace('TASK_ID',task_id).replace('SECONDS_VALUE',str(seconds)))


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['inspect','stage','body','conversation','logs','status','pull','recover','stop'])
    ap.add_argument('--task',choices=[t['id'] for t in load_tasks()],default='gather_logs')
    ap.add_argument('--seconds',type=int,default=240)
    ap.add_argument('--service',choices=['minecraft-bench','body-bench','agent-bench','llm-bench'],default='minecraft-bench')
    args=ap.parse_args()
    if not 1 <= args.seconds <= 3600:
        ap.error('--seconds must be between 1 and 3600')
    if args.action=='inspect':
        remote(INSPECT)
    elif args.action=='stage':
        stage()
    elif args.action=='logs':
        subprocess.run(ssh_args()+[f'docker logs --tail 60 ciel-minecraft-benchmark-{args.service}-1'],check=True)
    elif args.action=='status':
        remote('''
from pathlib import Path
import json
root=Path.home()/'work/ciel-companion-benchmark/server/benchmark/data/results'
reports=list(root.rglob('report.json'))
if reports:
    path=max(reports,key=lambda p:p.stat().st_mtime)
    report=json.loads(path.read_text())
    print(json.dumps({'path':str(path),'completion':report['manifest'].get('completion'),
        'run_error':report['manifest'].get('run_error'),'summary':report['summary'],'trials':report['trials']},ensure_ascii=False,indent=2))
    for trace in path.parent.glob('*/trace.jsonl'):
        rows=[json.loads(s) for s in trace.read_text().splitlines()]
        print(json.dumps(rows[-3:],ensure_ascii=False,indent=2))
        requests=[e['event'] for e in rows if e['kind']=='agent_event' and e['event'].get('kind')=='model_request']
        print(json.dumps({'model_requests':requests},ensure_ascii=False,indent=2))
''')
    elif args.action=='pull':
        import time
        destination=ROOT/'server/benchmark/data'/('home-import-'+str(time.time_ns()))
        destination.mkdir(parents=True)
        process=subprocess.Popen(ssh_args()+['tar -cf - -C ~/work/ciel-companion-benchmark/server/benchmark/data results'],stdout=subprocess.PIPE)
        with tarfile.open(fileobj=process.stdout,mode='r|') as archive:
            archive.extractall(destination,filter='data')
        # tarfile stops at the end marker; drain the remaining block padding so
        # tar/ssh cannot block on a full pipe while we wait for their exit.
        while process.stdout.read(65536):
            pass
        process.stdout.close()
        if process.wait():
            raise RuntimeError('Result download failed')
        print(destination)
    elif args.action=='recover':
        remote('''
from pathlib import Path
import subprocess
running=subprocess.check_output(['docker','ps','--filter','label=com.docker.compose.project=ciel-minecraft-benchmark',
    '--filter','label=com.docker.compose.service=benchmark-runner','--format','{{.ID}}'],text=True).strip()
if running:
    raise SystemExit('A benchmark runner is still active; recovery refused')
root=Path.home()/'work/ciel-companion-benchmark/server'
compose=['docker','compose','--env-file','.env.benchmark','-f','compose.benchmark.yaml','--profile','conversation']
subprocess.run(compose+['stop','agent-bench','body-bench'],cwd=root,check=True)
subprocess.run(compose+['exec','-T','minecraft-bench','rcon-cli','data remove storage ciel_benchmark:meta active'],cwd=root,check=True)
''')
    elif args.action=='stop':
        remote('''
from pathlib import Path
import subprocess
running=subprocess.check_output(['docker','ps','--filter','label=com.docker.compose.project=ciel-minecraft-benchmark',
    '--filter','label=com.docker.compose.service=benchmark-runner','--format','{{.ID}}'],text=True).strip()
if running:
    raise SystemExit('A benchmark runner is still active; stop refused')
root=Path.home()/'work/ciel-companion-benchmark/server'
subprocess.run(['docker','compose','--env-file','.env.benchmark','-f','compose.benchmark.yaml',
    '--profile','runner','--profile','conversation','--profile','local','down'],cwd=root,check=True)
''')
    else:
        smoke(args.action,args.task,args.seconds)
