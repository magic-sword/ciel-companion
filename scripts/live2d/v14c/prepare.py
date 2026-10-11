"""Prepare v14c and fingerprint prior assets; never write into prior versions."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
GEN=ROOT/'assets/ciel/generated/v14c'

def main():
    for name in ('inputs','extraction','selected','proofs','private'):
        (GEN/name).mkdir(parents=True,exist_ok=True)
    (ROOT/'assets/ciel/layers/v14c').mkdir(parents=True,exist_ok=True)
    (GEN/'.gitignore').write_text('/private/\n',encoding='utf-8')
    folders=[f'assets/ciel/{kind}/{version}' for kind in ('layers','generated') for version in ('v14','v14b')]
    folders+=['scripts/live2d/v14','scripts/live2d/v14b','.local/reference']
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in folders for p in (ROOT/folder).rglob('*') if p.is_file()}
    (GEN/'inputs/source-hashes.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    for v in ('v14','v14b'):
        im=Image.open(ROOT/f'assets/ciel/layers/{v}/Mouth_Large.png')
        im.crop((1020,1205,1190,1325)).resize((1020,720),Image.Resampling.NEAREST).save(GEN/f'inputs/{v}-mouth-native-zoom.png')
    print(f'Snapshotted {len(hashes)} prior files.')

if __name__=='__main__':main()
