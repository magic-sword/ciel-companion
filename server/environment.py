"""Split Compose credentials and environment settings; never start services or print secrets."""
import argparse
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile

SHARED_KEYS = frozenset({'LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET',
                         'OPENAI_API_KEY', 'YOUTUBE_API_KEY', 'CIEL_DB_PASSWORD'})
COMPOSE_KEYS = frozenset({'CIEL_MODEL', 'CIEL_LLM_BACKEND', 'CIEL_INPUT',
                         'CIEL_STT_BACKEND', 'CIEL_VOSK_MODEL_PATH',
                         'CIEL_LOCAL_LLM_URL', 'CIEL_LOCAL_LLM_MODEL', 'CIEL_LOCAL_TIMEOUT'})

def read(path):
    if not path.exists():
        return {}
    values = {}
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:]
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)', line)
        if not match:
            raise ValueError(f'{path.name}:{number}: expected a single-line dotenv assignment')
        key, value = match.groups()
        if key in values:
            raise ValueError(f'{path.name}: duplicate key {key}')
        # Preserve quoting, escapes and interpolation for Compose, not the shell.
        values[key] = value
    return values

def serialize(values):
    return '# Managed settings; secrets must stay outside Git.\n' + ''.join(
        key + '=' + value + '\n' for key, value in values.items())

def plan(prod, dev=None):
    shared_path = prod / '.env.shared'
    shared = read(shared_path)
    unknown = set(shared) - SHARED_KEYS
    if unknown:
        raise ValueError('.env.shared contains non-shared keys: ' + ', '.join(sorted(unknown)))
    legacy = read(prod / 'agent/.env') if not shared_path.exists() else {}
    production = read(prod / '.env')
    # Existing shared values are authoritative; reject conflicting credentials.
    for source in ((legacy, production) if not shared_path.exists() else (production,)):
        for key in SHARED_KEYS & source.keys():
            if key in shared and shared[key] != source[key]:
                raise ValueError('Conflicting shared credential: ' + key)
            shared[key] = source[key]
    if not shared.get('CIEL_DB_PASSWORD', '').strip('\"\''):
        shared['CIEL_DB_PASSWORD'] = secrets.token_hex(24)
    if any(k.startswith('CIEL_DEV_') for k in production):
        raise ValueError('Development keys belong in .env.dev, not production .env')
    migrated = {k: v for k, v in legacy.items() if k not in SHARED_KEYS}
    # Match the old production Compose defaults, not the native agent defaults.
    for key in COMPOSE_KEYS:
        migrated.pop(key, None)
        if key in production:
            migrated[key] = production[key]
    migrated.update({k: v for k, v in production.items() if k not in SHARED_KEYS})
    if shared_path.exists():
        # Once migrated, never copy stale native settings into Compose again.
        migrated = {k: v for k, v in production.items() if k not in SHARED_KEYS}
    targets = {shared_path: shared, prod / '.env': migrated}
    if dev is not None:
        path = dev / '.env.dev'
        old = read(path)
        development = {k: v for k, v in old.items() if not k.startswith('CIEL_DEV_')}
        for key, value in old.items():
            if not key.startswith('CIEL_DEV_'):
                continue
            canonical = 'CIEL_MINUTES_DISCORD_WEBHOOK' if key == 'CIEL_DEV_DISCORD_WEBHOOK' else 'CIEL_' + key[len('CIEL_DEV_'):]
            if canonical in development and development[canonical] != value:
                raise ValueError('Conflicting development key: ' + canonical)
            development[canonical] = value
        if set(development) & SHARED_KEYS:
            raise ValueError('Shared credentials belong in .env.shared, not .env.dev')
        development.setdefault('CIEL_LLM_BACKEND', 'openai')
        development.setdefault('CIEL_MINUTES_DISCORD_WEBHOOK', '')
        development.setdefault('CIEL_LOCAL_ROLES', 'thought,brief,notes,relationship,growth')
        targets[path] = development
    return targets

def migrate(prod, dev=None, check=False):
    prod = Path(prod).resolve()
    dev = Path(dev).resolve() if dev is not None else None
    targets = plan(prod, dev)
    changes = {p: values for p, values in targets.items() if not p.exists() or read(p) != values}
    if check or not changes:
        return len(changes), None
    backup_root = prod / 'data/config-backups'
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix='environment-', dir=backup_root))
    for number, path in enumerate([*targets, prod / 'agent/.env']):
        if path.is_file():
            dest = backup / (str(number) + '-' + path.name)
            shutil.copy2(path, dest)
            dest.chmod(0o600)
    # The legacy native file remains untouched; Compose no longer reads it.
    originals = {p: p.read_bytes() if p.exists() else None for p in changes}
    try:
        for path, values in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=path.parent, prefix='.environment-')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                    stream.write(serialize(values))
                os.chmod(name, 0o600)
                os.replace(name, path)
            finally:
                if Path(name).exists():
                    Path(name).unlink()
    except BaseException:
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
                path.chmod(0o600)
        raise
    return len(changes), backup

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prod-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--dev-dir', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        count, backup = migrate(args.prod_dir, args.dev_dir, args.check)
    except ValueError as error:
        parser.exit(2, str(error) + '\n')
    print(f'Environment files needing migration: {count}' if args.check else f'Environment files updated: {count}')
    if backup:
        print('Private backup:', backup)
