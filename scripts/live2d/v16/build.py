"""v16: uniform placement and review images only; never modify artwork pixels."""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / 'assets/ciel/generated/v16'
LAY = ROOT / 'assets/ciel/layers/v16'
SIZE = (2172, 2896)
FONT = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 25)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def place(source, scale, xy):
    im = Image.open(source).convert('RGBA')
    # Exactly one common scale for both dimensions; only integer raster rounding.
    resized = im.resize(tuple(round(v * scale) for v in im.size), Image.Resampling.LANCZOS)
    out = Image.new('RGBA', SIZE)
    out.alpha_composite(resized, tuple(xy))
    return out


def panel(items, path, crop=None, width=650):
    images = []
    for label, im in items:
        im = im.crop(crop) if crop else im.copy()
        im = im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS)
        tile = Image.new('RGBA', (width, im.height + 48), '#424966')
        tile.alpha_composite(im, (0, 48))
        ImageDraw.Draw(tile).text((16, 10), label, font=FONT, fill='white')
        images.append(tile)
    result = Image.new('RGB', (sum(i.width for i in images), max(i.height for i in images)), '#424966')
    x = 0
    for im in images:
        result.paste(im, (x, 0))
        x += im.width
    result.save(path)


def main():
    config = read(LAY / 'placement.json')
    layers = {}
    checks = {}
    for name, transform in config['transforms'].items():
        source = ROOT / transform['source']
        im = place(source, transform['uniform_scale'], transform['translate'])
        target = LAY / 'garments' / (name + '.png')
        im.save(target)
        layers[name] = im
        a = im.getchannel('A')
        checks[name] = {'source_sha256': sha(source), 'output_sha256': sha(target),
                        'size': list(im.size), 'mode': im.mode, 'alpha_extrema': a.getextrema(),
                        'bbox': a.getbbox(), 'only_uniform_scale_and_translation': True}
        assert im.size == SIZE and im.mode == 'RGBA' and a.getextrema() == (0, 255)

    # Face/head/neck are existing v14c layers, unchanged and in their existing order.
    excluded = {'Hair_Back', 'Body', 'Outer_L', 'Outer_R', 'Choker_Back', 'Choker_Inside',
                'Choker_Pendant', 'Choker_Front', 'Choker_Buckle'}
    composite = Image.open(ROOT / 'assets/ciel/layers/v15b/Hair_Back.png').convert('RGBA')
    composite.alpha_composite(layers['Body'])
    references = ['assets/ciel/layers/v15b/Hair_Back.png']
    for layer in read(ROOT / 'assets/ciel/layers/v14c/layer-state.json')['layers']:
        if layer['visible'] and layer['name'] not in excluded:
            composite.alpha_composite(Image.open(ROOT / layer['path']).convert('RGBA'))
            references.append(layer['path'])
    # Explicitly unsplit garments on top, as authorized for this handoff preview.
    composite.alpha_composite(layers['Jacket'])
    composite.alpha_composite(layers['Choker'])
    composite.save(GEN / 'proofs/v16-composite.png')
    original = Image.open(ROOT / 'assets/ciel/master/ciel-upper-body-2x.png').convert('RGBA')
    previous = Image.open(ROOT / 'assets/ciel/generated/v15b/proofs/v15b-composite.png').convert('RGBA')
    items = [('Original', original), ('v15b', previous), ('v16 - unsplit garments', composite)]
    panel(items, GEN / 'proofs/comparison-full.png')
    panel(items, GEN / 'proofs/comparison-neck-shoulders.png', crop=(280, 1190, 1890, 2140), width=805)
    panel([(n, layers[n]) for n in ['Body', 'Jacket', 'Choker']], GEN / 'proofs/placed-garments.png', width=550)
    checks['proof_context'] = {p: sha(ROOT / p) for p in references}
    checks['body_source_matches_v15'] = checks['Body']['source_sha256'] == '7f1576a48a13813fbd24c56feefd016d9c10c81688a0dbfe68f634818a54a126'
    assert checks['body_source_matches_v15']
    write(LAY / 'validation.json', checks)
    print(json.dumps({k: v for k, v in checks.items() if k != 'proof_context'}, indent=2))


if __name__ == '__main__':
    main()
