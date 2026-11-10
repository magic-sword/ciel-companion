#!/usr/bin/env python3
"""Stage/run/pull the isolated WSP harness using existing private home SSH settings."""
import argparse
import base64
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('benchmark_home', Path(__file__).with_name('benchmark-home.py'))
home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)
DEST = "Path.home()/'work/ciel-weight-space-benchmark'"
FILES = ['server/benchmark/weight_space.py', 'server/benchmark/weight_space/suite.json',
         'server/benchmark/weight_space/conditions.example.json'] + [
             'server/agent/config/prompts/' + p + '.md' for p in ('character','ciel_self','app','tool_discovery','game')]


def remote(code, capture=False):
    result = subprocess.run(home.ssh_args() + ['python3 -'], input=code, text=True, encoding='utf-8',
                            stdout=subprocess.PIPE if capture else None)
    if result.returncode:
        raise SystemExit(result.returncode)
    return result.stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('inspect', 'stage', 'run', 'pull'))
    p.add_argument('--label', default='baseline-smoke')
    p.add_argument('--split', choices=('dev','holdout'), default='dev')
    p.add_argument('--rounds', type=int, default=1)
    p.add_argument('--limit', type=int, default=1)
    p.add_argument('--output', type=Path)
    p.add_argument('--case', action='append', dest='selected')
    args = p.parse_args()
    import re
    if not re.fullmatch('[a-zA-Z0-9_-]+', args.label) or args.rounds < 1 or args.limit < 1:
        p.error('Invalid label/trial count')
    prefix = 'from pathlib import Path\nimport json,subprocess,sys,urllib.request,hashlib,platform,base64\nroot=' + DEST + '\n'
    if args.mode == 'inspect':
        remote(prefix + """
def get(url):
    with urllib.request.urlopen(url,timeout=5) as r:return json.load(r)
print(json.dumps({'mode':get('http://127.0.0.1:8095/mode'),
    'models':get('http://127.0.0.1:8094/v1/models'),
    'model_files':[p.name for p in (Path.home()/'models/llm').glob('*') if p.is_file()],
    'python':sys.version.split()[0]},ensure_ascii=False))
""")
    elif args.mode == 'stage':
        payload = {name: base64.b64encode((ROOT/name).read_bytes()).decode() for name in FILES}
        remote(prefix + 'payload=' + repr(payload) + '\n' + """
for name,data in payload.items():
    target=root/name
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(base64.b64decode(data))
print('Staged harness and prompt fixtures only:',root)
""")
    elif args.mode == 'run':
        # Hash real mounted weights; do not load .env or include container secrets in output.
        command = ['python3','-B','-m','server.benchmark.weight_space','run',
                   '--conditions','conditions.json','--output','results/'+args.label,
                   '--split',args.split,'--rounds',str(args.rounds),'--limit',str(args.limit)]
        for id in args.selected or []:
            command += ['--case', id]
        remote(prefix + 'command=' + repr(command) + '\n' + """
with urllib.request.urlopen('http://127.0.0.1:8095/mode',timeout=5) as r:mode=json.load(r)
if not mode.get('ready'):raise SystemExit('Shared API is not ready')
model=Path(mode['model']).name
weights=Path.home()/'models/llm'/model
if not weights.is_file():raise SystemExit('Expected weights not found; inspect actual mount before running')
print('Hashing actual baseline weights before evaluation',flush=True)
h=hashlib.sha256()
with weights.open('rb') as f:
    for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
with urllib.request.urlopen('http://127.0.0.1:8094/props',timeout=5) as r:props=json.load(r)
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],text=True).strip()
cpu=subprocess.check_output(['lscpu','-J'],text=True)
conditions={'model_id':model,'weights_sha256':h.hexdigest(),
    'hardware':{'platform':platform.platform(),'gpu':gpu,'cpu':json.loads(cpu)},
    'runtime':{'props':props,'mode':mode['mode'],'context':mode.get('context'),'parallel':mode.get('parallel')},
    'shared_load':'normal shared service; concurrent activity not controlled; no load generation'}
(root/'conditions.json').write_text(json.dumps(conditions,ensure_ascii=False,indent=2))
sys.exit(subprocess.run(command,cwd=root).returncode)
""")
    else:
        if not args.output:
            p.error('pull requires new --output directory')
        data = json.loads(remote(prefix + 'label=' + repr(args.label) + '\n' + """
folder=root/'results'/label
print(json.dumps({p.name:json.loads(p.read_text()) for p in folder.glob('*.json')}))
""", capture=True))
        if 'report.json' not in data:
            p.error('Remote report not found')
        args.output.mkdir(parents=True, exist_ok=False)
        for name, value in data.items():
            (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(args.output)


if __name__ == '__main__':
    main()
