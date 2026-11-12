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
         'server/benchmark/topic_state.py', 'server/benchmark/weight_space/topic-state-suite.json',
         'server/benchmark/weight_space/conversation-suite.json',
         'server/benchmark/weight_space/failure-loop-suite.json',
         'server/benchmark/weight_space/topic-loop-suite.json',
         'server/benchmark/weight_space/stream-replay-suite.json',
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
    p.add_argument('--conversation', action='store_true', help='Run stage 1-3 conversation suite')
    p.add_argument('--failure-loop', action='store_true', help='Run failure/topic fixation probes (120 seconds per case)')
    p.add_argument('--topic-loop', action='store_true', help='Run multi-turn casual topic fixation probes')
    p.add_argument('--stream-replay', action='store_true', help='Run stream-derived task-switch probes')
    p.add_argument('--topic-state', action='store_true', help='Run all paired state/reply diagnostic cases')
    p.add_argument('--assessment-only', action='store_true', help='With topic-state: separate reading-task follow-up')
    p.add_argument('--prompt-revision', help='stage: Git commit for baseline prompts; code stays current')
    p.add_argument('--prompt-dir', type=Path, help='stage: explicit experimental prompt directory')
    args = p.parse_args()
    if args.assessment_only and not args.topic_state:
        p.error('assessment-only requires topic-state')
    if sum((args.conversation, args.failure_loop, args.topic_loop, args.stream_replay, args.topic_state)) > 1:
        p.error('Choose one conversation suite')
    if args.prompt_revision and args.prompt_dir:
        p.error('Choose prompt-revision OR prompt-dir')
    if args.mode != 'stage' and (args.prompt_revision or args.prompt_dir):
        p.error('Prompt selection applies only to stage')
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
    'python':sys.version.split()[0],
    'memory':[s for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith(('MemTotal:','MemAvailable:'))],
    'disk':subprocess.check_output(['df','-h',str(Path.home()/'models/llm')],text=True)},ensure_ascii=False))
""")
    elif args.mode == 'stage':
        payload = {name: base64.b64encode((ROOT/name).read_bytes()).decode() for name in FILES}
        if args.prompt_dir:
            for name in FILES:
                if name.endswith('.md'):
                    payload[name] = base64.b64encode((args.prompt_dir/Path(name).name).read_bytes()).decode()
        if args.prompt_revision:
            if not re.fullmatch('[a-fA-F0-9]{7,40}', args.prompt_revision):
                p.error('Use an explicit Git commit ID')
            for name in FILES:
                if name.endswith('.md'):
                    data = subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),
                        'show',args.prompt_revision+':'+name],cwd=ROOT)
                    payload[name] = base64.b64encode(data).decode()
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
        if args.conversation:
            command += ['--suite', 'server/benchmark/weight_space/conversation-suite.json', '--timeout', '180']
        if args.failure_loop:
            command += ['--suite', 'server/benchmark/weight_space/failure-loop-suite.json', '--timeout', '120']
        if args.topic_loop:
            command += ['--suite', 'server/benchmark/weight_space/topic-loop-suite.json', '--timeout', '120']
        if args.stream_replay:
            command += ['--suite', 'server/benchmark/weight_space/stream-replay-suite.json', '--timeout', '120']
        if args.topic_state:
            command = ['python3','-B','-m','server.benchmark.topic_state','run',
                       '--conditions','conditions.json','--output','results/'+args.label,'--rounds',str(args.rounds)]
            if args.assessment_only:command += ['--assessment-only']
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
