#!/usr/bin/env python3
"""Deploy the complete committed development agent, or compare it with HEAD."""
import argparse
import base64
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def compare_inventory(actual, expected):
    different = [n for n in expected if n in actual and hashlib.sha256(actual[n]).hexdigest() != expected[n]]
    text_extensions = ('.py', '.md', '.toml', '.json', '.txt', '.yaml', '.yml')
    content = [n for n in different if not n.endswith(text_extensions) or
               hashlib.sha256(actual[n].replace(b'\r\n', b'\n')).hexdigest() != expected[n]]
    return {'missing': sorted(set(expected) - set(actual)), 'extra': sorted(set(actual) - set(expected)),
            'different': different, 'content_different': content, 'checked': len(expected)}


def remote(request):
    import gzip
    import io
    import shutil
    import tarfile
    import time
    import urllib.request

    base = Path.home() / 'work/ciel-companion-dev/server'
    name = 'ciel-dev-agent-dev-1'

    def run(args, **kwargs):
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, **kwargs)

    def containers():
        rows = json.loads(run(['docker', 'inspect', *run(['docker', 'ps', '-q']).split()]))
        return {r['Name'].lstrip('/'): {'id': r['Id'], 'image': r['Image'],
                'started': r['State']['StartedAt'], 'restarts': r['RestartCount']} for r in rows}

    def compare(expected):
        program = """import json,hashlib
from pathlib import Path
expected=EXPECTED
actual={str(p.relative_to('/app')):p.read_bytes() for folder in ('tools','summaries','config')
        for p in Path('/app',folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
actual.update({p.name:p.read_bytes() for p in Path('/app').glob('*.py')})
print(json.dumps(compare_inventory(actual,expected)))""".replace('EXPECTED', repr(expected))
        program = 'import hashlib\n' + request['compare_code'] + '\n' + program
        return json.loads(run(['docker', 'exec', name, 'python', '-c', program]))

    if request['check']:
        result = compare(request['expected'])
        print(json.dumps(result), flush=True)
        if any(result[k] for k in ('missing', 'extra', 'content_different')):
            raise RuntimeError('Running source differs from committed source')
        return

    before = containers()
    old = json.loads(run(['docker', 'inspect', name]))[0]
    env = os.environ.copy()
    env.update(dict(entry.split('=', 1) for entry in old['Config']['Env']))
    dest = base / 'data/deployments' / ('agent-' + request['commit'][:12] + '-' + str(time.time_ns()))
    dest.mkdir(parents=True, mode=0o700)
    (dest / 'before.json').write_text(json.dumps(before, indent=2))
    release = dest / 'release'
    release.mkdir()
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(request['archive']))) as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk() or member.name.startswith('/') or '..' in Path(member.name).parts:
                raise ValueError('Unsafe archive member')
        archive.extractall(release)
    source = release / 'server/agent'
    tag = 'ciel-dev-agent:' + request['commit'][:12]
    with (dest / 'build.log').open('w') as log:
        subprocess.run(['docker', 'build', '--label', 'org.opencontainers.image.revision=' + request['commit'],
                        '-t', tag, str(source)], stdout=log, stderr=subprocess.STDOUT, check=True)
    print('Built complete committed agent ' + request['commit'][:12], flush=True)
    # A new agent may perform startup schema maintenance. Preserve the shared database first.
    with gzip.open(dest / 'database.sql.gz', 'wb') as output:
        process = subprocess.Popen(['docker', 'exec', 'ciel-db-1', 'pg_dump', '-U', 'ciel', '-d', 'ciel'], stdout=subprocess.PIPE)
        shutil.copyfileobj(process.stdout, output)
        if process.wait():
            raise RuntimeError('Database backup failed')
    override = base / 'compose.agent-release.json'
    previous_override = override.read_bytes() if override.exists() else None
    old_config = next(m['Source'] for m in old['Mounts'] if m['Destination'] == '/app/config')
    env_file = base / '.env.dev'
    previous_env = env_file.read_bytes()
    (dest / 'env.dev.before').write_bytes(previous_env)
    (dest / 'env.dev.before').chmod(0o600)
    runtime = {'commit': request['commit'], 'sources': request['expected'], 'image': run(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}']).strip()}
    for key, url in [('mode', 'http://127.0.0.1:8095/mode'), ('props', 'http://127.0.0.1:8094/props')]:
        with urllib.request.urlopen(url, timeout=5) as response:
            runtime[key] = json.load(response)
    raw = json.dumps(runtime, sort_keys=True).encode()
    manifest = hashlib.sha256(raw).hexdigest()
    (dest / 'runtime.json').write_bytes(raw)
    env['CIEL_TRACE_RUNTIME_MANIFEST'] = manifest
    compose = ['docker', 'compose', '--env-file', '../../ciel-companion/server/.env.shared',
               '--env-file', '.env.dev', '-f', 'compose.dev.yaml', '-f', str(override)]

    def settings(image, config):
        return {'services': {'agent-dev': {'image': image, 'volumes': [str(config) + ':/app/config:ro']}}}

    def restart():
        with (dest / 'restart.log').open('a') as log:
            subprocess.run(compose + ['up', '-d', '--no-build', '--no-deps', '--force-recreate', 'agent-dev'],
                           cwd=base, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)

    try:
        override.write_text(json.dumps(settings(tag, source / 'config')))
        lines = [line for line in previous_env.decode().splitlines() if not line.startswith('CIEL_TRACE_RUNTIME_MANIFEST=')]
        env_file.write_text('\n'.join(lines + ['CIEL_TRACE_RUNTIME_MANIFEST=' + manifest]) + '\n')
        restart()
        healthy = registered = False
        for attempt in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8091', timeout=2) as response:
                    healthy = response.status == 200
            except Exception:
                healthy = False
            registered = 'registered worker' in run(['docker', 'logs', '--since', '2m', name])
            if healthy and registered:
                break
            time.sleep(1)
        result = compare(request['expected'])
        after = containers()
        unchanged = all(after.get(n) == v for n, v in before.items() if n != name)
        verified = healthy and registered and unchanged and not any(result[k] for k in ('missing', 'extra', 'different'))
        report = {'commit': request['commit'], 'runtime_manifest': manifest, 'comparison': result,
                  'health': healthy, 'worker_registered': registered, 'others_unchanged': unchanged,
                  'image': after[name]['image'], 'restarts': after[name]['restarts'], 'verified': verified}
        (dest / 'verification.json').write_text(json.dumps(report, indent=2))
        (dest / 'after.json').write_text(json.dumps(after, indent=2))
        print(json.dumps({'evidence': str(dest), **report}), flush=True)
        if not verified:
            raise RuntimeError('Deployment verification failed')
    except BaseException:
        rollback_tag = 'ciel-dev-agent:rollback-' + request['commit'][:12]
        run(['docker', 'tag', old['Image'], rollback_tag])
        override.write_text(json.dumps(settings(rollback_tag, old_config)))
        env_file.write_bytes(previous_env)
        env.update(dict(entry.split('=', 1) for entry in old['Config']['Env']))
        restart()
        if previous_override is not None:
            override.write_bytes(previous_override)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dev', action='store_true', required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--host')
    args = parser.parse_args()
    def git(*arguments):
        return subprocess.check_output(['git', *arguments], cwd=ROOT)
    if not args.check and git('status', '--porcelain', '--untracked-files=no').strip():
        parser.error('Commit tracked changes before deploying')
    commit = git('rev-parse', 'HEAD').decode().strip()
    archive = git('archive', 'HEAD', 'server/agent')
    expected = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        for member in source.getmembers():
            name = member.name.removeprefix('server/agent/')
            if member.isfile() and (('/' not in name and name.endswith('.py')) or name.startswith(('tools/', 'summaries/', 'config/'))):
                expected[name] = hashlib.sha256(source.extractfile(member).read()).hexdigest()
    request = {'commit': commit, 'check': args.check, 'expected': expected,
               'compare_code': inspect.getsource(compare_inventory)}
    if not args.check:
        request['archive'] = base64.b64encode(archive).decode()
    config = {}
    for line in (ROOT / 'scripts/server/.env.local').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip().strip('"').strip("'")
    host = args.host or os.environ.get('CIEL_SERVER_HOST') or config.get('CIEL_SERVER_HOST', '')
    if not re.fullmatch(r'[A-Za-z0-9_.@:\[\]-]+', host) or host.startswith('-'):
        parser.error('Invalid SSH target')
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=15']
    key = os.environ.get('CIEL_SSH_KEY', config.get('CIEL_SSH_KEY', ''))
    if key:
        ssh += ['-i', os.path.expanduser(key), '-o', 'IdentitiesOnly=yes']
    code = 'from pathlib import Path\nimport subprocess,json,os,base64,hashlib\n' + inspect.getsource(remote)
    code += '\nremote(json.loads(base64.b64decode(' + repr(base64.b64encode(json.dumps(request).encode()).decode()) + ')))\n'
    subprocess.run(ssh + [host, 'python3 -'], input=code, text=True, encoding='utf-8', check=True)


if __name__ == '__main__':
    main()
