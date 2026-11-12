"""Deploy the committed Minecraft body image, preserving the world and other services."""
import base64
import importlib.util
import inspect
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def remote(request):
    import hashlib
    import os
    import time
    base = Path.home() / 'work/ciel-companion/server'
    name = 'ciel-minecraft-body-1'
    def run(args, **kw):
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, **kw)
    def states():
        rows = json.loads(run(['docker', 'inspect', *run(['docker', 'ps', '-q']).split()]))
        return {r['Name'].lstrip('/'): {'id': r['Id'], 'image': r['Image'], 'started': r['State']['StartedAt']}
                for r in rows}
    before = states()
    old = json.loads(run(['docker', 'inspect', name]))[0]
    env = os.environ.copy()
    env.update(dict(v.split('=', 1) for v in old['Config']['Env']))
    dest = base / 'data/deployments' / ('body-' + request['commit'][:12] + '-' + str(time.time_ns()))
    dest.mkdir(parents=True, mode=0o700)
    (dest / 'before.json').write_text(json.dumps(before, indent=2))
    release = dest / 'release'
    release.mkdir()
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(request['archive']))) as tf:
        for member in tf.getmembers():
            if member.issym() or member.islnk() or member.name.startswith('/') or '..' in Path(member.name).parts:
                raise ValueError('Unsafe archive member')
        tf.extractall(release)
    source = release / 'server/minecraft'
    tag = 'ciel-minecraft-body:' + request['commit'][:12]
    with (dest / 'build.log').open('w') as log:
        subprocess.run(['docker', 'build', '--network', 'host', '--label',
                        'org.opencontainers.image.revision=' + request['commit'], '-t', tag, str(source)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    with (dest / 'test.log').open('w') as log:
        subprocess.run(['docker', 'run', '--rm', '--entrypoint', 'node', '-v', str(source / 'test') + ':/app/test:ro',
                        tag, '--test', 'test/ciel-model.test.js', 'test/mindcraft-runtime.test.js', 'test/tasks.test.js'],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    print('Committed body built and tested', flush=True)
    override = base / 'compose.body-release.json'
    previous = override.read_bytes() if override.exists() else None
    if previous:
        (dest / 'override-before.json').write_bytes(previous)
    compose = ['docker', 'compose', '-p', 'ciel', '--env-file', '.env.shared', '--env-file', '.env',
               '--env-file', '.env.minecraft', '-f', 'compose.yaml', '-f', str(override)]
    def restart():
        with (dest / 'restart.log').open('a') as log:
            subprocess.run(compose + ['up', '-d', '--no-build', '--no-deps', '--force-recreate', 'minecraft-body'],
                           cwd=base, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    try:
        override.write_text(json.dumps({'services': {'minecraft-body': {'image': tag}}}))
        restart()
        for _ in range(40):
            row = json.loads(run(['docker', 'inspect', name]))[0]
            listing = run(['docker', 'exec', 'ciel-minecraft-1', 'rcon-cli', 'list'])
            if row['State']['Running'] and 'Ciel' in listing:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Ciel did not join')
        js = """const fs=require('fs'),p=require('path'),c=require('crypto');let o={};
function w(d){for(const n of fs.readdirSync(d)){const f=p.join(d,n);if(fs.statSync(f).isDirectory())w(f);
else o[p.relative('/app/src',f)]=c.createHash('sha256').update(fs.readFileSync(f)).digest('hex')}}
w('/app/src');console.log(JSON.stringify(o))"""
        actual = json.loads(run(['docker', 'exec', name, 'node', '-e', js]))
        expected = {p.relative_to(source / 'src').as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (source / 'src').rglob('*') if p.is_file()}
        assert actual == expected, 'Body source mismatch'
        after = states()
        assert all(after.get(n) == state for n, state in before.items() if n != name), 'Other service changed'
        report = {'commit': request['commit'], 'image': after[name]['image'], 'source_files': len(expected),
                  'source_match': True, 'others_unchanged': True, 'joined': True, 'evidence': str(dest)}
        (dest / 'verification.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    except BaseException:
        rollback = 'ciel-minecraft-body:rollback-' + request['commit'][:12]
        run(['docker', 'tag', old['Image'], rollback])
        override.write_text(json.dumps({'services': {'minecraft-body': {'image': rollback}}}))
        restart()
        if previous:
            override.write_bytes(previous)
        raise


def main():
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise SystemExit('Commit changes before deploying')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', 'HEAD', 'server/minecraft'], cwd=ROOT)
    spec = importlib.util.spec_from_file_location('home', ROOT / 'scripts/server/weight-space-home.py')
    home = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(home)
    request = {'commit': commit, 'archive': base64.b64encode(archive).decode()}
    code = 'from pathlib import Path\nimport subprocess,json,base64,io,tarfile\n' + inspect.getsource(remote)
    home.remote(code + '\nremote(' + repr(request) + ')\n', capture=False)


if __name__ == '__main__':
    main()
