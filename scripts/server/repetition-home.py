"""Run the recurrence harness in the existing development image; no deployment or game actions."""
import argparse
import base64
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--label',required=True);p.add_argument('--smoke',action='store_true')
    p.add_argument('--split',choices=('dev','validation'),default='dev');p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--sampling',choices=('production','deterministic'),default='production');p.add_argument('--pull-only',action='store_true');a=p.parse_args()
    if not re.fullmatch('[A-Za-z0-9_-]+',a.label) or not 1<=a.rounds<=10:p.error('Invalid label or rounds')
    if a.smoke and a.split!='dev':p.error('Smoke uses dev controls')
    spec=importlib.util.spec_from_file_location('home',Path(__file__).with_name('weight-space-home.py'));h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    files=['server/benchmark/'+n for n in ('weight_space.py','repetition.py','repetition_review.py','weight_space/repetition-suite.json')]
    payload={name:base64.b64encode((ROOT/name).read_bytes()).decode() for name in files}
    prefix='from pathlib import Path\nimport json,base64,subprocess,hashlib,urllib.request,platform\nlabel='+repr(a.label)+"\nroot=Path.home()/'work/ciel-repetition-evaluation'/label\n"
    if not a.pull_only:
        command=['python','-B','-m','server.benchmark.repetition','run','--agent-dir','/app','--prompt-dir','/app/config/prompts',
                 '--conditions','conditions.json','--output','output','--split',a.split,'--rounds',str(1 if a.smoke else a.rounds),'--sampling',a.sampling]
        if a.smoke:command+=['--case','necessary-question-control','--case','requested-recap-control']
        h.remote(prefix+'payload='+repr(payload)+'\ncommand='+repr(command)+'''
root.mkdir(parents=True,exist_ok=False)
for name,value in payload.items():
    f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(base64.b64decode(value))
with urllib.request.urlopen('http://127.0.0.1:8095/mode',timeout=5) as r:mode=json.load(r)
if not mode.get('ready') or mode.get('mode')!='gpu':raise RuntimeError('Shared GPU unavailable')
weights=Path.home()/'models/llm'/Path(mode['model']).name
h=hashlib.sha256()
with weights.open('rb') as f:
    for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
conditions=dict(model_id=weights.name,weights_sha256=h.hexdigest(),hardware=platform.platform(),shared_load='normal shared service, concurrency uncontrolled',runtime=mode)
(root/'conditions.json').write_text(json.dumps(conditions))
container='ciel-dev-agent-dev-1';destination='/tmp/ciel-repetition-'+label
subprocess.run(['docker','cp',str(root),container+':'+destination],check=True)
result=subprocess.run(['docker','exec','-w',destination,container,*command])
subprocess.run(['docker','cp',container+':'+destination+'/output',str(root/'output')],check=True)
if result.returncode:raise SystemExit(result.returncode)
''')
    raw=h.remote(prefix+'''
folder=root/'output'
print(json.dumps({'report':json.loads((folder/'report.json').read_text()),'sources':{p.name:base64.b64encode(p.read_bytes()).decode() for p in (folder/'sources').iterdir()}}))
''',capture=True)
    data=json.loads(raw);out=ROOT/'server/benchmark/data'/a.label;out.mkdir(exist_ok=False)
    (out/'report.json').write_text(json.dumps(data['report'],ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'sources').mkdir()
    for name,value in data['sources'].items():(out/'sources'/name).write_bytes(base64.b64decode(value))
    print(out)


if __name__=='__main__':main()
