"""Prepare the exact v11 neutral input; writes only v14 directories."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / 'assets/ciel/generated/v14'
LAY = ROOT / 'assets/ciel/layers/v14'
CROP = (318, 236, 1854, 1772)

def main():
    for d in (GEN, LAY, GEN / 'private', GEN / 'inputs', GEN / 'candidates', GEN / 'proofs'):
        d.mkdir(parents=True, exist_ok=True)
    (GEN / '.gitignore').write_text('/private/\n', encoding='utf-8')
    state = json.loads((ROOT / 'assets/ciel/layers/v11/layer-state.json').read_text(encoding='utf-8'))
    im = Image.new('RGBA', tuple(state['canvas']))
    for row in state['layers']:
        if row['visible']:
            im = Image.alpha_composite(im, Image.open(ROOT / row['path']).convert('RGBA'))
    im.save(GEN / 'inputs/v11-neutral.png')
    face = im.crop(CROP).resize((1254, 1254), Image.Resampling.LANCZOS)
    bg = Image.new('RGBA', face.size, '#f4f5f7')
    bg.alpha_composite(face)
    bg.convert('RGB').save(GEN / 'inputs/v11-face-closed.png')
    transform = {'canvas': state['canvas'], 'crop_xyxy': CROP, 'input_size': [1254, 1254],
                 'inverse': 'canvas_x = 318 + input_x * 1536 / 1254; canvas_y = 236 + input_y * 1536 / 1254'}
    (GEN / 'inputs/transform.json').write_text(json.dumps(transform, indent=2), encoding='utf-8')
    paths = [p for folder in ('assets/ciel/layers/v11', 'assets/ciel/layers/v12', 'assets/ciel/layers/v13', '.local/reference') for p in (ROOT / folder).rglob('*') if p.is_file()]
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (GEN / 'inputs/source-hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print(f'Prepared v11 face from {sum(r["visible"] for r in state["layers"])} visible layers; {len(paths)} input hashes.')

if __name__ == '__main__':
    main()
