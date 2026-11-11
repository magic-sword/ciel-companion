"""Run recorded-action target probes against the currently staged dedicated intake.

Stage the desired implementation with benchmark-home.py first. Only the probe
module is copied here, so baseline and candidate use identical test cases.
"""
import argparse
import base64
import importlib.util
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--label', choices=['baseline', 'candidate'], required=True)
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('home', Path(__file__).with_name('benchmark-home.py'))
home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)
probe = base64.b64encode((home.ROOT/'server/benchmark/target_intake.py').read_bytes()).decode()
home.remote('''
from pathlib import Path
import base64,subprocess,time,json,urllib.request
root=Path.home()/'work/ciel-companion-benchmark/server'
with urllib.request.urlopen('http://127.0.0.1:8095/mode',timeout=5) as r: mode=json.load(r)
if not mode.get('ready') or mode.get('mode')!='gpu': raise SystemExit('Shared GPU API is not ready')
running=subprocess.check_output(['docker','ps','--filter','label=com.docker.compose.project=ciel-minecraft-benchmark',
    '--filter','label=com.docker.compose.service=benchmark-runner','--format','{{.ID}}'],text=True).strip()
if running: raise SystemExit('A benchmark runner is active')
(root/'benchmark/target_intake.py').write_bytes(base64.b64decode(PROBE))
name='target-intake-'+LABEL+'-'+str(time.time_ns())
out=root/'benchmark/data/results'/name
out.mkdir()
(out/'inference.json').write_text(json.dumps(mode,indent=2))
compose=['docker','compose','--env-file','.env.benchmark','-f','compose.benchmark.yaml','--profile','runner']
subprocess.run(compose+['build','benchmark-runner'],cwd=root,check=True)
r=subprocess.run(compose+['run','--rm','--no-deps','--entrypoint','python','benchmark-runner',
    '-m','benchmark.target_intake','--output','/workspace/server/benchmark/data/results/'+name+'/report.json'],cwd=root)
print('Result:',name)
raise SystemExit(r.returncode)
'''.replace('PROBE', repr(probe)).replace('LABEL', repr(args.label)))
