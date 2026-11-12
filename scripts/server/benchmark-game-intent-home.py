#!/usr/bin/env python3
"""Compare recorded-only GameIntake requests through the shared home GPU API."""
import argparse
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('benchmark_home', Path(__file__).with_name('benchmark-home.py'))
home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)
sys.path.insert(0, str(ROOT/'server'))
from benchmark.stage1_intake import intent_scenarios, scenarios


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='HEAD')
    parser.add_argument('--case', action='append', default=[])
    args = parser.parse_args()
    cases = intent_scenarios()
    if args.case:
        cohort = scenarios(include_regressions=True)
        if not set(args.case) <= {c['id'] for c in cohort}:
            parser.error('Unknown intake case')
        cases = [c for c in cohort if c['id'] in args.case]
    if any(c.get('reference') for c in cases):
        parser.error('Pointing cases require the dedicated catalog and benchmark-stage1-home.py')
    revision = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options', args.baseline_ref+'^{commit}'], cwd=ROOT, text=True).strip()
    output = ROOT/'server/benchmark/data'/('game-intent-'+str(time.time_ns()))
    output.mkdir(parents=True)
    baseline = subprocess.check_output(['git', 'archive', revision, 'server/agent'], cwd=ROOT)
    (output/'baseline.tar').write_bytes(baseline)
    with tarfile.open(fileobj=io.BytesIO(baseline)) as archive:
        archive.extractall(output/'baseline', filter='data')
    # The same frozen profile is used for both workers. Reading exported static
    # capabilities does not connect a bot, call MCP or issue game operations.
    js = "import {CAPABILITIES} from '/app/src/ciel/tasks.js'; console.log(JSON.stringify({work:{version:1,capabilities:CAPABILITIES}}));"
    code = 'import subprocess,json\nprint(json.dumps({"image":subprocess.check_output(["docker","inspect","ciel-minecraft-body-1","--format","{{.Image}}"],text=True).strip(),"profile":json.loads(subprocess.check_output('+repr(['docker','exec','ciel-minecraft-body-1','node','--input-type=module','-e',js])+',text=True))}))'
    encoded = base64.b64encode(code.encode()).decode()
    result = subprocess.check_output(home.ssh_args()+['python3 -c "import base64;exec(base64.b64decode(\''+encoded+'\'))"'], text=True, encoding='utf-8')
    catalog = json.loads(result)
    (output/'catalog.json').write_text(json.dumps(catalog['profile'], ensure_ascii=False, indent=2), encoding='utf-8')
    (output/'cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding='utf-8')
    with tarfile.open(output/'candidate.tar.gz', 'x:gz') as archive:
        for directory in ('server/agent', 'server/benchmark', 'scripts/server'):
            for path in sorted((ROOT/directory).rglob('*')):
                relative = path.relative_to(ROOT)
                if path.is_file() and not path.is_symlink() and not any(p in ('data','__pycache__') for p in relative.parts) and not path.name.startswith('.env'):
                    archive.add(path, arcname=relative.as_posix(), recursive=False)
    ports = [free_port(), free_port()]
    while ports[1] == ports[0]:
        ports[1] = free_port()
    tunnel = subprocess.Popen(home.ssh_args()[:-1]+['-o','ExitOnForwardFailure=yes','-N',
        '-L',f'127.0.0.1:{ports[0]}:127.0.0.1:8094','-L',f'127.0.0.1:{ports[1]}:127.0.0.1:8095',home.ssh_args()[-1]],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    manifest = dict(scope='shared_model_recorded_actions_no_world_execution', baseline_commit=revision,
        catalog_image=catalog['image'], catalog_sha256=hashlib.sha256((output/'catalog.json').read_bytes()).hexdigest(),
        candidate_archive_sha256=hashlib.sha256((output/'candidate.tar.gz').read_bytes()).hexdigest(),
        selected_cases=[c['id'] for c in cases], total_budget_seconds=600, runs=[], state='running')
    path = output/'comparison.json'
    try:
        deadline = time.monotonic()+20
        while True:
            if tunnel.poll() is not None:
                raise RuntimeError('SSH tunnel exited')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{ports[0]}/props', timeout=1) as response:
                    json.load(response)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Shared API tunnel did not become ready')
                time.sleep(.2)
        environment = {**os.environ, 'PYTHONIOENCODING':'utf-8', 'CIEL_BENCH_LLM_SERVICE':'shared',
            'CIEL_BENCH_LLM_URL':f'http://127.0.0.1:{ports[0]}/v1', 'CIEL_BENCH_LLM_CONTROL':f'http://127.0.0.1:{ports[1]}'}
        deadline = time.monotonic()+600
        for variant in ('baseline', 'candidate'):
            source = output/'baseline/server/agent' if variant=='baseline' else ROOT/'server/agent'
            for index in range(0, len(cases), 3):
                destination = output/f'{variant}-{index//3}.json'
                command = [sys.executable,'-B','-X','utf8','-m','benchmark.stage1_intake','--variant',variant,
                    '--agent-source',str(source),'--catalog',str(output/'catalog.json'),'--output',str(destination)]
                for case in cases[index:index+3]:
                    command += ['--case',case['id']]
                result = subprocess.run(command, cwd=ROOT/'server', env=environment, timeout=max(.1,deadline-time.monotonic()))
                manifest['runs'].append(dict(variant=variant, report=destination.name, exit_code=result.returncode))
                path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
                if result.returncode and (variant=='candidate' or result.returncode!=1):
                    manifest['state']='stopped_for_diagnosis'
                    return 1
        manifest['state']='complete'
        return 0
    except Exception as error:
        manifest.update(state='error', error=type(error).__name__)
        raise
    finally:
        tunnel.terminate()
        tunnel.wait(timeout=10)
        path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(output, flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
