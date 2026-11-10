#!/usr/bin/env python3
"""Reproduce isolated capability-selection comparisons against the existing shared model."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def get(path, port=8095):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=3) as response:
        return json.load(response)


def remote(args):
    folder = ROOT/'results'/('capability-cache-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    folder.mkdir(parents=True)
    print(folder, flush=True)
    before = get('/mode')
    if not before.get('ready') or before.get('mode') != 'gpu':
        raise RuntimeError('Shared GPU model must be ready')
    image = subprocess.check_output(['docker','inspect','--format','{{.Image}}','ciel-dev-agent-dev-1'], text=True).strip()
    provenance = json.loads((ROOT/'source-provenance.json').read_text())
    with tarfile.open(folder/'sources.tar.gz', 'w:gz') as archive:
        for name in [*provenance['source_sha256'], 'source-provenance.json']:
            archive.add(ROOT/name, arcname=name)
    conditions = {'before':before, 'image':image, 'rounds':args.rounds, 'variants':args.variants,
                  'cases':args.cases, 'fresh_loaded_prefix':args.fresh_loaded_prefix, 'source':provenance,
                  'scope':'Synthetic actual-pipeline selection; no side-effecting tool execution; shared load uncontrolled'}
    (folder/'conditions.json').write_text(json.dumps(conditions,indent=2))
    stopped = threading.Event()
    def sample():
        with (folder/'load.jsonl').open('w') as stream:
            while not stopped.is_set():
                row = {'utc':datetime.now(timezone.utc).isoformat()}
                try:
                    row['mode'] = get('/mode')
                    row['slots'] = [{k:s.get(k) for k in ('id','is_processing')} for s in get('/slots',18094)]
                except Exception as error:
                    row['error'] = type(error).__name__
                stream.write(json.dumps(row)+'\n'); stream.flush()
                stopped.wait(2)
    monitor = threading.Thread(target=sample,daemon=True)
    monitor.start()
    try:
        for repeat in range(args.rounds):
            # Rotate order; never clear the shared model's live cache or slots.
            variants = args.variants[repeat % len(args.variants):]+args.variants[:repeat % len(args.variants)]
            for variant in variants:
                print(repeat, variant, flush=True)
                cmd = ['docker','run','--rm','--name','ciel-capability-cache-eval',
                       '--label','ciel.voice-evaluation=1','--network','host',
                       '-v',str(ROOT)+':/eval','-w','/eval',
                       '-e','CIEL_LOCAL_LLM_URL=http://127.0.0.1:8094/v1',image,
                       'python','scripts/server/benchmark-conversation-tools.py',
                       '--variant',variant,'--rounds','1','--output',f'/eval/results/{folder.name}/{variant}-{repeat}.json',
                       '--cases',*args.cases]
                if args.fresh_loaded_prefix:
                    cmd.append('--fresh-loaded-prefix')
                subprocess.run(cmd, check=True)
    finally:
        stopped.set(); monitor.join(timeout=8)
        (folder/'after.json').write_text(json.dumps(get('/mode'),indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remote',action='store_true')
    parser.add_argument('--rounds',type=int,default=3)
    parser.add_argument('--fresh-loaded-prefix',action='store_true')
    parser.add_argument('--variants',nargs='+',default=['baseline','prepared','specialist'],
                        choices=['baseline','compact','prepared','compact-prepared','specialist','specialist-prepared'])
    parser.add_argument('--cases',nargs='+',default=['minutes','name','status','history'],
                        choices=['greeting','mention','minutes','name','status','history'])
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('rounds must be positive')
    if args.remote:
        remote(args)
    else:
        spec = importlib.util.spec_from_file_location('home',Path(__file__).with_name('benchmark-home.py'))
        home = importlib.util.module_from_spec(spec);spec.loader.exec_module(home)
        command = ['python3','work/ciel-voice-evaluation/scripts/server/benchmark-capability-cache-home.py','--remote',
                   '--rounds',str(args.rounds),'--variants',*args.variants,'--cases',*args.cases]
        if args.fresh_loaded_prefix:
            command.append('--fresh-loaded-prefix')
        raise SystemExit(subprocess.run(home.ssh_args()+[shlex.join(command)]).returncode)
