"""Assemble/crop existing artwork for image edits; no drawn pixels or warping."""
from pathlib import Path
import json,hashlib
from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'assets/ciel/generated/v25'
CROP=(550,650,1600,1700)
for directory in ('inputs','edits','keyed','layers','proofs','qa'):(OUT/directory).mkdir(parents=True,exist_ok=True)
manifest=json.loads((ROOT/'assets/ciel/current/layers.json').read_text(encoding='utf-8'))
base=Image.new('RGBA',tuple(manifest['canvas']))
for entry in manifest['layers']:
    if entry.get('visible',True):base.alpha_composite(Image.open(ROOT/entry['path']).convert('RGBA'))
base.save(OUT/'inputs/assembled-current.png')
bg=Image.new('RGBA',base.size,(64,72,104,255));bg.alpha_composite(base)
bg.crop(CROP).convert('RGB').save(OUT/'inputs/face-current.png')
reference=Image.open(ROOT/'assets/ciel/generated/v22/expressions/happy.png').convert('RGBA')
reference.crop((350,690,1320,1660)).save(OUT/'inputs/happy-reference-face.png')
(OUT/'current-before.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted((ROOT/'assets/ciel/current').rglob('*')) if p.is_file()},indent=2),encoding='utf-8')
print('V25_INPUTS_READY')
