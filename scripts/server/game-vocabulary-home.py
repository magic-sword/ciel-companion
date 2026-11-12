"""Paired synthetic Minecraft vocabulary evaluation on the home CPU Whisper."""
import argparse,base64,importlib.util,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--pull-only',action='store_true');p.add_argument('--reuse-audio');a=p.parse_args()
 if not re.fullmatch('[A-Za-z0-9_-]+',a.label):p.error('Invalid label')
 if a.reuse_audio and not re.fullmatch('[A-Za-z0-9_-]+',a.reuse_audio):p.error('Invalid reuse-audio label')
 s=importlib.util.spec_from_file_location('h',Path(__file__).with_name('weight-space-home.py'));h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
 prefix='from pathlib import Path\nimport subprocess,json,base64\nroot=Path.home()/"work/ciel-vocabulary-evaluation"/'+repr(a.label)+'\n'
 if not a.pull_only:
  sources={'game_vocabulary_probe.py':'server/stt/game_vocabulary_probe.py','speech_vocabulary.py':'server/agent/speech_vocabulary.py','voice_benchmark.py':'server/agent/voice_benchmark.py','expanded.json':'server/minecraft/src/ciel/speech-vocabulary.json'}
  data={n:base64.b64encode((ROOT/f).read_bytes()).decode() for n,f in sources.items()}
  data['baseline.json']=base64.b64encode(subprocess.check_output(['git','-c','safe.directory='+str(ROOT).replace('\\','/'),'show','HEAD:server/minecraft/src/ciel/speech-vocabulary.json'],cwd=ROOT)).decode()
  h.remote(prefix+'reuse='+repr(a.reuse_audio)+'\ndata='+repr(data)+'''
root.mkdir(parents=True,exist_ok=False)
for name,value in data.items():(root/name).write_bytes(base64.b64decode(value))
extra=[]
if reuse:
 import shutil
 source=root.parent/reuse/'output';(root/'audio').mkdir()
 for p in source.glob('*.wav'):shutil.copy2(p,root/'audio'/p.name)
 extra=['--audio-dir','audio']
container='ciel-dev-agent-dev-1';target='/tmp/'+root.name
subprocess.run(['docker','cp',str(root),container+':'+target],check=True)
result=subprocess.run(['docker','exec','-w',target,container,'python','-B','game_vocabulary_probe.py','--vocabulary','expanded.json','--baseline','baseline.json','--output','output',*extra])
subprocess.run(['docker','cp',container+':'+target+'/output',str(root/'output')],check=True)
if result.returncode:raise SystemExit(result.returncode)
''')
 raw=h.remote(prefix+'''print(json.dumps({str(p.relative_to(root)):base64.b64encode(p.read_bytes()).decode() for p in root.rglob('*') if p.is_file()}))''',capture=True)
 out=ROOT/'server/benchmark/data'/a.label;out.mkdir(parents=True,exist_ok=False)
 for name,value in json.loads(raw).items():
  dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(base64.b64decode(value))
 print(out)
if __name__=='__main__':main()
