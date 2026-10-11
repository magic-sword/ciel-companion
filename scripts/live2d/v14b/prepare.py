"""Snapshot prior inputs and prepare v14b without modifying prior versions."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT/'assets/ciel/generated/v14b'

def main():
    for name in ('inputs','candidates','selected','proofs','extraction','private'):
        (GEN/name).mkdir(parents=True,exist_ok=True)
    (ROOT/'assets/ciel/layers/v14b').mkdir(parents=True,exist_ok=True)
    (GEN/'.gitignore').write_text('/private/\n',encoding='utf-8')
    for name in ('v11-face-closed.png','v11-neutral.png','transform.json'):
        shutil.copyfile(ROOT/'assets/ciel/generated/v14/inputs'/name,GEN/'inputs'/name)
    folders=['assets/ciel/layers/'+v for v in ('v11','v12','v13','v14')]
    folders+=['assets/ciel/generated/v14','scripts/live2d/v14','.local/reference']
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in folders for p in (ROOT/folder).rglob('*') if p.is_file()}
    (GEN/'inputs/source-hashes.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(f'Copied exact closed input; snapshotted {len(hashes)} existing files.')

if __name__=='__main__': main()
