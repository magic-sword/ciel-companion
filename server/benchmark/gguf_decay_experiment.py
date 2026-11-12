"""Run a registered GGUF candidate in an isolated CPU server, never production.

Stage beside weight_space.py, fixtures and the five deployed prompt files.
All reports use the normal comparison schema. CPU baselines are mandatory.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import shutil
import socket
import subprocess
import time
from types import SimpleNamespace
import urllib.request

ROOT = Path(__file__).resolve().parent
NAME = 'ciel-wsp-decay-test'
PORT = 18099
FILES = ['weight_space.py', 'gguf_decay_edit.py', 'gguf_eos_edit.py', 'gguf_decay_experiment.py', 'decay-plan.json',
         'stream-replay-suite.json', 'conversation-suite.json', 'suite.json',
         'character.md', 'ciel_self.md', 'app.md', 'tool_discovery.md', 'game.md']


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--label', required=True)
    p.add_argument('--model', choices=('base', 'decay010', 'decay025', 'eos110'), required=True)
    p.add_argument('--phase', choices=('screen', 'repeat', 'guard', 'holdout'), required=True)
    a = p.parse_args()
    if not re.fullmatch('[a-zA-Z0-9_-]+', a.label):
        p.error('Invalid label')
    plan = json.loads((ROOT/'decay-plan.json').read_text())
    phase = plan['phases'][a.phase]
    out = ROOT/'results'/a.label
    out.mkdir(parents=True, exist_ok=False)
    sources = out/'sources'
    sources.mkdir()
    for name in FILES:
        shutil.copyfile(ROOT/name, sources/name)
    spec = importlib.util.spec_from_file_location('wsp', sources/'weight_space.py')
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    suite = dict(schema=w.SCHEMA, cases=[])
    for name in phase['suites']:
        suite['cases'].extend(c for c in w.load_suite(sources/name)['cases'] if c['split'] == phase['split'])
    w.write(out/'suite.json', suite)
    system = '\n'.join((sources/(name+'.md')).read_text(encoding='utf-8') for name in w.PROMPTS)
    image = subprocess.check_output(['docker','inspect','ciel-local-llm-1','--format','{{.Image}}'],text=True).strip()
    model = Path.home()/'models/llm/Qwen3.5-35B-A3B-Q4_K_M.gguf' if a.model == 'base' else ROOT/(a.model+'.gguf')
    weight_hash = digest(model)
    if a.model == 'base':
        expected = plan['base_sha256']
    else:
        manifest = json.loads(model.with_suffix('.json').read_text())
        expected = manifest['candidate_sha256']
        if manifest['base_sha256'] != plan['base_sha256'] or not manifest['other_bytes_identical']:
            raise ValueError('Invalid edit manifest')
        w.write(out/'edit.json', manifest)
    if weight_hash != expected:
        raise ValueError('Model hash mismatch')
    args = SimpleNamespace(timeout=phase['timeout'], model='local', temperature=0,
                           max_tokens=512, thinking=False, base_url=f'http://127.0.0.1:{PORT}/v1')
    runtime = dict(image=image, threads=8, context=8192, parallel=1, gpu_layers=0,
                   memory_limit='40g', cpus=8)
    report = dict(schema=w.SCHEMA, created_utc=datetime.now(timezone.utc).isoformat(),
        label=a.label, model_label=a.model, phase=a.phase, commit=None, dirty=None,
        suite_sha256=w.digest(out/'suite.json'), runner_sha256=w.digest(sources/'weight_space.py'),
        experiment_sha256=w.digest(sources/'gguf_decay_experiment.py'),
        prompt_sha256=hashlib.sha256(system.encode()).hexdigest(), prompt_mode='deployed', prompt_chars=len(system),
        split=phase['split'], sampling=dict(temperature=0,max_tokens=512,timeout=args.timeout,seed=1729,thinking=False),
        rounds=phase['rounds'], case_ids=[c['id'] for c in suite['cases']],
        conditions=dict(model_id='Qwen3.5-35B-A3B-Q4_K_M', weights_sha256=weight_hash,
                        hardware='same home host CPU, 8 threads, no GPU', runtime=runtime,
                        shared_load='Normal services continue; activity uncontrolled'),
        source_hashes={name:w.digest(sources/name) for name in FILES},
        before=dict(mode=dict(mode='cpu'),shared=w.probe('http://127.0.0.1:8095','/mode')),
        completion='running', trials=[])
    w.write(out/'report.json',report)
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',PORT)) == 0:
            raise RuntimeError('Dedicated port in use')
    if NAME in subprocess.check_output(['docker','ps','-a','--format','{{.Names}}'],text=True).splitlines():
        raise RuntimeError('Dedicated container exists')
    started = False
    deadline = time.monotonic() + phase['wall_seconds']
    try:
        command = ['docker','run','-d','--name',NAME,'--label','ciel.test=wsp-decay',
                   '--network','host','--memory','40g','--cpus','8','--no-healthcheck',
                   '-v',str(model)+':/model.gguf:ro','--entrypoint','/app/llama-server',image,
                   '-m','/model.gguf','--host','127.0.0.1','--port',str(PORT),'--alias','local',
                   '-ngl','0','-t','8','-tb','8','-c','8192','--parallel','1','--jinja']
        subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
        started = True
        startup = time.monotonic()+180
        while True:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health',timeout=2) as r:
                    if r.status == 200:
                        break
            except Exception:
                if time.monotonic() > startup:
                    raise TimeoutError('Startup deadline')
                time.sleep(1)
        report['props'] = w.probe(f'http://127.0.0.1:{PORT}', '/props')
        for repeat in range(phase['rounds']):
            cases = suite['cases'][:]
            random.Random(1729+repeat).shuffle(cases)
            for case in cases:
                if time.monotonic()+args.timeout > deadline:
                    raise TimeoutError('Registered total wall-time budget')
                row = w.run_case(case, system, args, 1729+repeat)
                row['repeat'] = repeat
                report['trials'].append(row)
                report['summary'] = w.summary(report['trials'])
                w.write(out/'report.json',report)
                print(a.label,case['id'],repeat,row['status'],row['automatic_pass'],round(row['total_ms']/1000,1),flush=True)
        report['completion']='complete'
    except Exception as exc:
        report['error']=repr(exc)
        raise
    finally:
        report['after']=dict(mode='cpu',shared=w.probe('http://127.0.0.1:8095','/mode'))
        if started:
            log=subprocess.run(['docker','logs',NAME],capture_output=True,text=True)
            (out/'server.log').write_text(log.stdout+log.stderr)
            subprocess.run(['docker','rm','-f',NAME],check=True,stdout=subprocess.DEVNULL)
        report['dedicated_container_removed'] = started
        w.write(out/'report.json',report)


if __name__ == '__main__':
    main()
