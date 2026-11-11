"""Inspect the isolated pointing benchmark; optionally archive its evaluated source."""
import importlib.util
import argparse
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--snapshot',action='store_true')
parser.add_argument('--reports',action='store_true',help='Summarize recent reports without full conversation logs')
args=parser.parse_args()

spec=importlib.util.spec_from_file_location('benchmark_home',Path(__file__).with_name('benchmark-home.py'))
home=importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)
if args.reports:
    home.remote('''
from pathlib import Path
import json
root=Path.home()/'work/ciel-companion-benchmark/server/benchmark/data/results'
for path in sorted(root.glob('*/report.json'),key=lambda p:p.stat().st_mtime)[-6:]:
    r=json.loads(path.read_text())
    print(json.dumps({'run':path.parent.name,'manifest':r['manifest'],
        'trials':[{k:t.get(k) for k in ('task','status','reason','elapsed_seconds','time_to_goal_seconds','first_action_seconds','body_completion_confirmed')} for t in r['trials']]},ensure_ascii=False))
''')
    raise SystemExit(0)
home.remote('''
from pathlib import Path
import json,subprocess,hashlib
base=Path.home()/'work/ciel-companion-benchmark/server'
for rel in ['benchmark/data/world/ciel-pointing/selection.json',
            'benchmark/data/observations/body-state.json',
            'benchmark/data/observations/point-command.json',
            'benchmark/data/observations/point-ack.json',
            'benchmark/data/world/version_history.json']:
    path=base/rel
    print(rel, path.read_text()[:5000] if path.exists() else 'MISSING')
for name in ['minecraft-bench','owner-bench']:
    r=subprocess.run(['docker','logs','--tail','250','ciel-minecraft-benchmark-'+name+'-1'],capture_output=True,text=True)
    print(name, '\\n'.join(s for s in (r.stdout+r.stderr).splitlines() if any(k in s for k in ['CielPointing','ERROR','Exception','Point fixture','cielpoint'])))
for folder in sorted((base/'benchmark/data/results').glob('smoke-body-*'),key=lambda p:p.stat().st_mtime)[-2:]:
    for path in folder.glob('point*/trace.jsonl'):
        lines=path.read_text().splitlines()
        print(str(path.relative_to(base)), '\\n'.join(lines[-3:])[:5000])
for rel in ['benchmark/data/world/plugins/ciel-pointing.jar','benchmark/data/world/paper-1.21.11.jar']:
    p=base/rel
    if p.is_file(): print(rel,hashlib.sha256(p.read_bytes()).hexdigest())
''')
if args.snapshot:
    home.remote('''
from pathlib import Path
import datetime,hashlib,json,subprocess,tarfile,urllib.request,shutil
base=Path.home()/'work/ciel-companion-benchmark/server'
out=base/'benchmark/data/results'/('pointing-evidence-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
out.mkdir()
with tarfile.open(out/'source.tar.gz','w:gz') as archive:
    for path in sorted(base.rglob('*')):
        rel=path.relative_to(base)
        if any(x in rel.parts for x in ('data','node_modules','__pycache__','.venv','target')): continue
        if path.is_file() and not path.is_symlink() and not (path.name.startswith('.env') and not path.name.endswith('.example')):
            archive.add(path,arcname=str(rel),recursive=False)
names=['ciel-minecraft-benchmark-minecraft-bench-1','ciel-minecraft-benchmark-body-bench-1','ciel-local-llm-1','ciel-agent-1','ciel-dev-agent-dev-1','ciel-minecraft-1']
items=json.loads(subprocess.check_output(['docker','inspect',*names]))
metadata={'containers':[{'name':i['Name'],'image':i['Image'],'started':i['State']['StartedAt'],'restarts':i['RestartCount']} for i in items],
          'inference':json.load(urllib.request.urlopen('http://127.0.0.1:8095/mode',timeout=5)),
          'source_sha256':hashlib.sha256((out/'source.tar.gz').read_bytes()).hexdigest()}
version=base/'benchmark/data/world/version_history.json'
if version.exists(): metadata['minecraft']=json.loads(version.read_text())
jar=base/'benchmark/data/world/plugins/ciel-pointing.jar'
shutil.copyfile(jar,out/'ciel-pointing.jar')
metadata['plugin_sha256']=hashlib.sha256(jar.read_bytes()).hexdigest()
(out/'runtime.json').write_text(json.dumps(metadata,indent=2))
print('Evidence:',out.name)
''')
