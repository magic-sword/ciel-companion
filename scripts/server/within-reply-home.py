"""Run the within-reply benchmark on the existing shared Qwen; no deployment."""
import argparse,base64,importlib.util,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--log',required=True);p.add_argument('--speech',required=True);p.add_argument('--pull-only',action='store_true');a=p.parse_args()
 if not re.fullmatch('[A-Za-z0-9_-]+',a.label):p.error('Invalid label')
 spec=importlib.util.spec_from_file_location('h',Path(__file__).with_name('weight-space-home.py'));h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
 prefix='from pathlib import Path\nimport subprocess,json,base64,hashlib,urllib.request\nroot=Path.home()/"work/ciel-within-reply"/'+repr(a.label)+'\n'
 if not a.pull_only:
  files=['server/benchmark/'+n for n in ('within_reply.py','repetition.py','weight_space.py')]
  payload={f:base64.b64encode((ROOT/f).read_bytes()).decode() for f in files}
  h.remote(prefix+'payload='+repr(payload)+'\nlog='+repr(a.log)+'\nspeech='+repr(a.speech)+'''
root.mkdir(parents=True,exist_ok=False);root.chmod(0o700)
for name,data in payload.items():
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(data))
raw=Path(log).read_bytes();(root/'incident-original.jsonl').write_bytes(raw)
rows=[json.loads(l) for l in raw.splitlines() if l.strip()]
rows=[r for r in rows if r.get('kind') in ('item','thought_opening','reply_request','speech','mind_output')]
(root/'incident.jsonl').write_text('\\n'.join(json.dumps(r,ensure_ascii=False) for r in rows),encoding='utf-8')
with urllib.request.urlopen('http://127.0.0.1:8095/mode',timeout=5) as r:mode=json.load(r)
weights=Path.home()/'models/llm'/Path(mode['model']).name
digest=hashlib.sha256()
with weights.open('rb') as f:
 for b in iter(lambda:f.read(8*1024*1024),b''):digest.update(b)
conditions={'model':weights.name,'weights_sha256':digest.hexdigest(),'mode':mode,'original_log_sha256':hashlib.sha256(raw).hexdigest(),'shared_load':'normal services running; concurrent demand uncontrolled'}
container='ciel-dev-agent-dev-1';target='/tmp/'+root.name
subprocess.run(['docker','cp',str(root),container+':'+target],check=True)
result=subprocess.run(['docker','exec','-w',target,container,'python','-B','-m','server.benchmark.within_reply','--log','incident.jsonl','--speech',speech,'--output','output'])
subprocess.run(['docker','cp',container+':'+target+'/output',str(root/'output')],check=True)
(root/'output/conditions.json').write_text(json.dumps(conditions,indent=2))
(root/'output/sources').mkdir()
for name in payload:(root/'output/sources'/Path(name).name).write_bytes((root/name).read_bytes())
if result.returncode:raise SystemExit(result.returncode)
''')
 raw=h.remote(prefix+'''print(json.dumps({str(p.relative_to(root/'output')):base64.b64encode(p.read_bytes()).decode() for p in (root/'output').rglob('*') if p.is_file()}))''',capture=True)
 dest=ROOT/'server/benchmark/data'/a.label;dest.mkdir(parents=True,exist_ok=False)
 for name,data in json.loads(raw).items():
  out=dest/name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(base64.b64decode(data))
 print(dest)
if __name__=='__main__':main()
