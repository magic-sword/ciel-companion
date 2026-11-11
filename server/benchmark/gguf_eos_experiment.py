"""Home-host pilot: identical isolated CPU runtime for base and edited GGUF.

Run after gguf_eos_edit.py, alongside staged weight_space.py and suite files.
No production restart, no GPU allocation, no real tools. Results are exploratory.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import time
from types import SimpleNamespace
import urllib.request

ROOT = Path.home()/'work/ciel-weight-space-quant'
STAGED = Path.home()/'work/ciel-weight-space-benchmark'
PORT = 18099
NAME = 'ciel-wsp-quant-pilot'


def main():
    spec = importlib.util.spec_from_file_location('wsp', ROOT/'weight_space.py')
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    image = subprocess.check_output(['docker','inspect','ciel-local-llm-1','--format','{{.Image}}'],text=True).strip()
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',PORT)) == 0:
            raise RuntimeError('Pilot port already in use')
    existing = subprocess.check_output(['docker','ps','-a','--format','{{.Names}}'],text=True).splitlines()
    if NAME in existing:
        raise RuntimeError('Pilot container already exists')
    suites = [w.load_suite(ROOT/name) for name in ('conversation-suite.json','suite.json')]
    selected = {'chat-s1-fact-dev','chat-s1-detail-dev','chat-s3-shorten-dev',
                'chat-s2-correction-dev','json-dev','math-dev','stop-dev'}
    cases = [c for suite in suites for c in suite['cases'] if c['id'] in selected]
    if {c['id'] for c in cases} != selected:
        raise ValueError('Missing pilot cases')
    system = '\n'.join((ROOT/(p+'.md')).read_text() for p in w.PROMPTS)
    edit = json.loads((ROOT/'eos105.json').read_text())
    result_dir = ROOT/'pilot-01'
    result_dir.mkdir(exist_ok=False)
    args = SimpleNamespace(timeout=180, model='local',temperature=0, max_tokens=512,
                           thinking=False,base_url=f'http://127.0.0.1:{PORT}/v1')
    for label, model, weight_hash in [('base','/models/Qwen3.5-35B-A3B-Q4_K_M.gguf',edit['base_sha256']),
                                      ('eos105','/work/eos105.gguf',edit['candidate_sha256'])]:
        report = dict(label=label, completion='running', image=image, weights_sha256=weight_hash,
                      prompt_sha256=hashlib.sha256(system.encode()).hexdigest(),
                      source_hashes={p.name:w.digest(p) for p in [ROOT/'weight_space.py',ROOT/'gguf_eos_experiment.py',ROOT/'conversation-suite.json',ROOT/'suite.json']},
                      conditions=dict(mode='cpu',threads=8,context=8192,parallel=1,
                                      temperature=0,seed=1729,max_tokens=512,timeout=180,
                                      shared_load='Normal services continue; activity uncontrolled'), trials=[])
        started = False
        try:
            command = ['docker','run','-d','--name',NAME,'--label','ciel.test=wsp-quant',
                       '--network','host','--memory','40g','--cpus','8','--no-healthcheck',
                       '-v',str(Path.home()/'models/llm')+':/models:ro','-v',str(ROOT)+':/work:ro',
                       '--entrypoint','/app/llama-server',image,'-m',model,'--host','127.0.0.1',
                       '--port',str(PORT),'--alias','local','-ngl','0','-t','8','-tb','8',
                       '-c','8192','--parallel','1','--jinja']
            subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
            started = True
            deadline=time.monotonic()+180
            while True:
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health',timeout=2) as r:
                        if r.status == 200:
                            break
                except Exception:
                    if time.monotonic() > deadline:
                        raise TimeoutError('Pilot startup deadline')
                    time.sleep(1)
            report['ready']=True
            for case in cases:
                row=w.run_case(case,system,args,1729)
                report['trials'].append(row)
                w.write(result_dir/(label+'.json'),report)
                print(label,case['id'],row['status'],round(row['total_ms']/1000,1),flush=True)
            report['completion']='complete'
            report['summary']=w.summary(report['trials'])
        except Exception as exc:
            report['error']=repr(exc)
            raise
        finally:
            w.write(result_dir/(label+'.json'),report)
            if started:
                log=subprocess.run(['docker','logs',NAME],capture_output=True,text=True)
                (result_dir/(label+'.log')).write_text(log.stdout+log.stderr)
                subprocess.run(['docker','rm','-f',NAME],check=True,stdout=subprocess.DEVNULL)
    print('Pilot complete; isolated container removed',flush=True)


if __name__ == '__main__':
    main()
