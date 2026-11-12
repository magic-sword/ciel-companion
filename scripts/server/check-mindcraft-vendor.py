"""Verify the pinned Mindcraft source tree and its explicit CIEL patch set."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / 'server/minecraft/src/vendor/mindcraft'


def main():
    manifest = json.loads((VENDOR / 'provenance.json').read_text(encoding='utf-8'))
    expected = manifest['files']
    actual = {p.relative_to(VENDOR).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in VENDOR.rglob('*') if p.is_file() and p.name != 'provenance.json'}
    errors = [name for name in sorted(set(expected) | set(actual))
              if actual.get(name) != expected.get(name, {}).get('sha256')]
    if errors:
        raise SystemExit('Mindcraft vendor drift: ' + ', '.join(errors))
    print(f"Mindcraft {manifest['commit']}: {len(actual)} files verified; "
          f"{len(manifest['patched_files'])} explicit upstream patches")


if __name__ == '__main__':
    main()
