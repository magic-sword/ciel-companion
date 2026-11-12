"""Rebuild the vendored Mindcraft tree from the CIEL fork and import it with git subtree.

The fork (magic-sword/mindcraft) keeps the CIEL patches as commits on its `ciel`
branch, rebased onto upstream `develop`. This script turns that branch into the
`ciel-vendor` branch, which holds only the files CIEL ships (LF-normalized, with
provenance.json), then runs `git subtree add/pull --squash` into this repository.

Usage (from the ciel-companion root, with a clean working tree):
  python scripts/server/update-mindcraft-vendor.py --fork-dir ../mindcraft
Options:
  --no-push      build ciel-vendor locally and import from the fork directory
  --build-only   only build ciel-vendor in the fork directory
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'server/minecraft/src/vendor/mindcraft'
UPSTREAM_URL = 'https://github.com/mindcraft-bots/mindcraft'
VENDOR_BRANCH = 'ciel-vendor'
# Upstream task definitions used by the CIEL body benchmark (data only, no runners).
TASK_FILES = ('tasks/basic/single_agent.json', 'tasks/single_agent/crafting_train.json')
SCOPE = ('Upstream src, profiles, templates, settings, package metadata and selected '
         'single-agent task definitions. Native '
         'Agent/Prompter/History/SelfPrompter/NPC run with an injected CIEL model; '
         'CIEL owns authenticated transport and lifecycle.')


def git(cwd, *args, data=None, env=None):
    out = subprocess.run(['git', *args], cwd=cwd, input=data, env=env,
                         stdout=subprocess.PIPE, check=True)
    return out.stdout


def text(cwd, *args, **kw):
    return git(cwd, *args, **kw).decode('utf-8').strip()


def vendor_path(path):
    """Map an upstream path to its vendored path, or None when it is not shipped."""
    if path == 'package.json':
        return 'package.upstream.json'
    if path in ('settings.js', 'LICENSE', *TASK_FILES) or path.split('/')[0] in ('src', 'profiles', 'bots'):
        return path
    return None


def tree_files(cwd, rev):
    files = {}
    for line in git(cwd, 'ls-tree', '-r', '-z', rev).split(b'\0'):
        if not line:
            continue
        meta, path = line.split(b'\t', 1)
        mode, kind, sha = meta.decode().split()
        if kind == 'blob':
            files[path.decode('utf-8')] = (mode, sha)
    return files


def normalize(data):
    return data if b'\0' in data else data.replace(b'\r\n', b'\n')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def build(fork, ref, upstream_ref):
    ciel = text(fork, 'rev-parse', ref)
    base = text(fork, 'merge-base', ciel, upstream_ref)
    patched = set(text(fork, 'diff', '--name-only', base, ciel).splitlines())
    upstream = tree_files(fork, base)
    entries, manifest, normalized = [], {}, []
    for path, (mode, sha) in sorted(tree_files(fork, ciel).items()):
        target = vendor_path(path)
        if target is None:
            continue
        raw = git(fork, 'cat-file', 'blob', sha)
        data = normalize(raw)
        new_sha = text(fork, 'hash-object', '-w', '--stdin', data=data)
        entries.append(f'{mode} {new_sha}\t{target}')
        info = {'sha256': sha256(data)}
        if path in upstream:
            info['upstream_sha256'] = sha256(git(fork, 'cat-file', 'blob', upstream[path][1]))
        if data != raw and path not in patched:
            normalized.append(target)
        manifest[target] = info
    provenance = {
        'repository': UPSTREAM_URL,
        'commit': base,
        'fork': text(fork, 'remote', 'get-url', 'origin'),
        'fork_branch': ref,
        'fork_commit': ciel,
        'license': 'MIT',
        'scope': SCOPE,
        'patched_files': sorted(vendor_path(p) for p in patched if vendor_path(p)),
        'normalization_only_files': normalized,
        'files': manifest,
    }
    blob = (json.dumps(provenance, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    entries.append('100644 ' + text(fork, 'hash-object', '-w', '--stdin', data=blob)
                   + '\tprovenance.json')
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / 'index'))
        git(fork, 'update-index', '--add', '--index-info',
            data=('\n'.join(entries) + '\n').encode('utf-8'), env=env)
        tree = text(fork, 'write-tree', env=env)

    parent = None
    for candidate in (f'refs/remotes/origin/{VENDOR_BRANCH}', f'refs/heads/{VENDOR_BRANCH}'):
        if subprocess.run(['git', 'rev-parse', '-q', '--verify', candidate], cwd=fork,
                          stdout=subprocess.DEVNULL).returncode == 0:
            parent = text(fork, 'rev-parse', candidate)
            break
    if parent and text(fork, 'rev-parse', parent + '^{tree}') == tree:
        print(f'{VENDOR_BRANCH} already matches {ciel[:7]}')
        return parent
    message = (f'Vendor Mindcraft {ciel[:7]} (upstream {base[:7]})\n\n'
               f'fork-commit: {ciel}\nupstream-commit: {base}\n')
    args = ['commit-tree', tree, '-m', message] + (['-p', parent] if parent else [])
    commit = text(fork, *args)
    git(fork, 'update-ref', f'refs/heads/{VENDOR_BRANCH}', commit)
    print(f'{VENDOR_BRANCH} -> {commit[:7]} ({len(manifest)} files, '
          f'{len(provenance["patched_files"])} patched)')
    return commit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fork-dir', required=True, type=Path)
    parser.add_argument('--ref', default='ciel')
    parser.add_argument('--upstream-ref', default='upstream/develop')
    parser.add_argument('--no-push', action='store_true')
    parser.add_argument('--build-only', action='store_true')
    args = parser.parse_args()
    fork = args.fork_dir.resolve()

    git(fork, 'fetch', '-q', 'origin')
    if args.upstream_ref.startswith('upstream/'):
        git(fork, 'fetch', '-q', 'upstream')
    commit = build(fork, args.ref, args.upstream_ref)
    if args.build_only:
        return
    if args.no_push:
        source = str(fork)
    else:
        git(fork, 'push', 'origin', f'{commit}:refs/heads/{VENDOR_BRANCH}')
        source = text(fork, 'remote', 'get-url', 'origin')
    action = 'pull' if (ROOT / PREFIX).exists() else 'add'
    subprocess.run(['git', 'subtree', action, f'--prefix={PREFIX}', '--squash',
                    '-m', f'Update vendored Mindcraft to {commit[:7]}', source, VENDOR_BRANCH],
                   cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/server/check-mindcraft-vendor.py')],
                   cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
