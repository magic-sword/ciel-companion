#!/usr/bin/env python3
"""Task-vs-chat routing on the shared home GPU API: a committed baseline against the working tree.

Reads the body's MCP catalog without linking a bot, opens a tunnel to the shared model API, and
runs server/benchmark/intent_routing.py for both sources. Nothing is executed in a world.
"""
import argparse
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

# Lists tools and the play prompt through an in-memory MCP client; no hub is claimed.
CATALOG_JS = """
import { makeServer, profile } from '/app/src/ciel/mcp.js';
import { Client } from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import { InMemoryTransport } from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/inMemory.js';
const hub = { link: null, claim: () => null, release: () => {}, controller: null, busy: false, fingerprint: () => '' };
const server = makeServer(hub, () => 'bench');
const [a, b] = InMemoryTransport.createLinkedPair();
await server.connect(a);
const client = new Client({ name: 'bench', version: '1' });
await client.connect(b);
const tools = (await client.listTools()).tools;
const play = (await client.getPrompt({ name: 'play' })).messages.map((m) => m.content.text).join(String.fromCharCode(10));
console.log(JSON.stringify({ profile: profile(), tools, play }));
process.exit(0);
"""


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='HEAD')
    parser.add_argument('--baseline-system', default='intake', choices=['intake', 'mind'])
    parser.add_argument('--candidate-system', default='mind', choices=['intake', 'mind'])
    parser.add_argument('--split', action='append', choices=['dev', 'real'])
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--only', choices=['baseline', 'candidate'])
    parser.add_argument('--candidate-catalog', type=Path,
                        help='Catalog JSON for the candidate (a game-side change not yet deployed); default: the live body')
    args = parser.parse_args()
    if args.candidate_catalog:
        args.candidate_catalog = args.candidate_catalog.resolve()
    output = ROOT/'.local/intent-routing'/('run-'+time.strftime('%Y%m%dT%H%M%S'))
    output.mkdir(parents=True)
    revision = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options', args.baseline_ref+'^{commit}'],
                                       cwd=ROOT, text=True).strip()
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git', 'archive', revision, 'server/agent'], cwd=ROOT))) as archive:
        archive.extractall(output/'baseline', filter='data')
    remote = "docker exec -i -w /app ciel-minecraft-body-1 sh -c 'cat > /tmp/ciel-catalog.mjs && node /tmp/ciel-catalog.mjs; rm -f /tmp/ciel-catalog.mjs'"
    catalog = subprocess.run(home.ssh_args()+[remote], input=CATALOG_JS.encode(), capture_output=True, check=True).stdout
    json.loads(catalog)
    (output/'catalog.json').write_bytes(catalog)
    port = free_port()
    tunnel = subprocess.Popen(home.ssh_args()[:-1]+['-o', 'ExitOnForwardFailure=yes', '-N',
                              '-L', f'127.0.0.1:{port}:127.0.0.1:8094', home.ssh_args()[-1]],
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        deadline = time.monotonic()+20
        while True:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/props', timeout=1):
                    break
            except OSError:
                if time.monotonic() >= deadline or tunnel.poll() is not None:
                    raise RuntimeError('Shared API tunnel did not become ready')
                time.sleep(.2)
        runs = [('baseline', output/'baseline/server/agent', args.baseline_system),
                ('candidate', ROOT/'server/agent', args.candidate_system)]
        for name, source, system in runs:
            if args.only and name != args.only:
                continue
            command = [sys.executable, '-B', '-X', 'utf8', '-m', 'benchmark.intent_routing', '--system', system,
                       '--agent-source', str(source),
                       '--catalog', str(args.candidate_catalog if name == 'candidate' and args.candidate_catalog else output/'catalog.json'),
                       '--llm-url', f'http://127.0.0.1:{port}/v1', '--repeat', str(args.repeat),
                       '--output', str(output/f'{name}.json')]
            for split in args.split or ['dev']:
                command += ['--split', split]
            subprocess.run(command, cwd=ROOT/'server', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, check=True)
        (output/'manifest.json').write_text(json.dumps({'baseline_commit': revision, 'runs': runs and [
            {'name': n, 'source': str(s), 'system': y} for n, s, y in runs]}, ensure_ascii=False, indent=1), encoding='utf-8')
    finally:
        tunnel.terminate()
        tunnel.wait(timeout=10)
        print(output, flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
