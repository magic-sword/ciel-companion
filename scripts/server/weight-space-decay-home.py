"""Stage/edit/run/pull the bounded decay WSP experiment via existing home SSH."""
import argparse
import base64
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('wsp_home', Path(__file__).with_name('weight-space-home.py'))
home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('action', choices=('stage','edit','run','pull','status'))
p.add_argument('--model', choices=('base','decay010','decay025','eos110'))
p.add_argument('--phase', choices=('screen','repeat','guard','holdout'))
p.add_argument('--label')
p.add_argument('--output',type=Path)
a = p.parse_args()
import re
if a.label and not re.fullmatch('[a-zA-Z0-9_-]+', a.label):
    p.error('Invalid label')
prefix = "from pathlib import Path\nimport json,subprocess,base64\nroot=Path.home()/'work/ciel-weight-space-quant'\n"
if a.action == 'stage':
    files = ['server/benchmark/'+n for n in ('weight_space.py','gguf_decay_edit.py','gguf_eos_edit.py','gguf_decay_experiment.py')]
    files += ['server/benchmark/weight_space/'+n for n in ('decay-plan.json','stream-replay-suite.json','suite.json','conversation-suite.json')]
    files += ['server/agent/config/prompts/'+n+'.md' for n in ('character','ciel_self','app','tool_discovery','game')]
    payload = {Path(n).name:base64.b64encode((ROOT/n).read_bytes()).decode() for n in files}
    home.remote(prefix + "\nif 'ciel-wsp-decay-test' in subprocess.check_output(['docker','ps','-a','--format','{{.Names}}'],text=True).splitlines(): raise RuntimeError('Experiment active')\nroot.mkdir(exist_ok=True)\npayload="+repr(payload)+"\nfor name,data in payload.items(): (root/name).write_bytes(base64.b64decode(data))\nprint('Staged experiment sources')\n")
elif a.action == 'edit':
    if a.model == 'base':
        p.error('base cannot be edited')
    home.remote(prefix + 'selected='+repr(a.model)+'\n'+"""
image=subprocess.check_output(['docker','inspect','ciel-local-llm-1','--format','{{.Image}}'],text=True).strip()
plan=json.loads((root/'decay-plan.json').read_text())
for name,value in plan['candidates'].items():
    if selected and name != selected: continue
    eos=plan['candidate_methods'][name] == 'eos_scale'
    script='gguf_eos_edit.py' if eos else 'gguf_decay_edit.py'
    option='--factor' if eos else '--shift'
    command=['docker','run','--rm','--network','none','--cpus','2','--memory','3g','-v',str(root)+':/work','-v',str(Path.home()/'models/llm')+':/models:ro','-e','PYTHONPATH=/work/deps','--entrypoint','/opt/vision-venv/bin/python',image,'/work/'+script,'/models/Qwen3.5-35B-A3B-Q4_K_M.gguf','/work/'+name+'.gguf',option,str(value)]
    subprocess.run(command,check=True)
""")
elif a.action == 'run':
    if not all((a.label,a.model,a.phase)):
        p.error('run requires label, model and phase')
    command=['python3','-B','gguf_decay_experiment.py','--label',a.label,'--model',a.model,'--phase',a.phase]
    home.remote(prefix+"subprocess.run("+repr(command)+",cwd=root,check=True)\n")
elif a.action == 'pull':
    if not a.label or not a.output or a.output.exists():
        p.error('pull requires label and a new output directory')
    result=json.loads(home.remote(prefix+"target=root/'results'/"+repr(a.label)+"\nprint(json.dumps({str(f.relative_to(target)):base64.b64encode(f.read_bytes()).decode() for f in target.rglob('*') if f.is_file()}))\n",capture=True))
    a.output.mkdir(parents=True)
    for name,data in result.items():
        target=(a.output/name).resolve()
        if not target.is_relative_to(a.output.resolve()):
            raise ValueError('Unsafe result path')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(base64.b64decode(data))
    print('Saved',len(result),'files to',a.output)
else:
    home.remote(prefix+"print(json.dumps({'containers':subprocess.check_output(['docker','ps','--filter','label=ciel.test=wsp-decay','--format','{{.Names}}'],text=True).splitlines(),'reports':[dict(label=r.get('label'),completion=r.get('completion'),error=r.get('error'),trials=len(r['trials']),automatic_pass=sum(t['automatic_pass'] for t in r['trials'])) for f in sorted((root/'results').glob('*/report.json')) for r in [json.loads(f.read_text())]]}))\n")
