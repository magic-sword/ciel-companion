"""Place untouched generated art and make review sheets; never mask or retouch art."""
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / 'assets/ciel/generated/v16b'
LAY = ROOT / 'assets/ciel/layers/v16b'
PROOFS = GEN / 'proofs'
SOURCE = ROOT / 'assets/ciel/generated/v16/jacket.png'
CONFIG = ROOT / 'assets/ciel/layers/v16/placement.json'
SELECTED = GEN / 'jacket-front-03.png'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def panel(items, path, width=None):
    tiles = []
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 25)
    for label, art in items:
        # Review sheets only: neutral backdrop, labels and optional uniform resize.
        if width:
            art = art.resize((width, round(art.height * width / art.width)), Image.Resampling.LANCZOS)
        tile = Image.new('RGBA', (art.width, art.height + 48), '#424966')
        tile.alpha_composite(art, (0, 48))
        ImageDraw.Draw(tile).text((16, 10), label, font=font, fill='white')
        tiles.append(tile)
    sheet = Image.new('RGB', (sum(t.width for t in tiles), max(t.height for t in tiles)), '#424966')
    x = 0
    for tile in tiles:
        sheet.paste(tile, (x, 0))
        x += tile.width
    sheet.save(path)


def main():
    PROOFS.mkdir(exist_ok=True)
    before = {str(p.relative_to(ROOT)): sha(p) for p in (SOURCE, CONFIG)}
    assert before[str(SOURCE.relative_to(ROOT))] == '9bfeb9eabf54d1e6b5b3d23841cb99e997e2189129695541c6c414711ac6a40a'
    assert before[str(CONFIG.relative_to(ROOT))] == 'dd21a1e611684dd7aefa6f81ce395488e0218124af8e43cdc5934409d0aa40a4'
    shutil.copyfile(SELECTED, GEN / 'jacket-front.png')
    source = Image.open(SOURCE).convert('RGBA')
    front = Image.open(GEN / 'jacket-front.png').convert('RGBA')
    assert front.size == source.size == (1441, 1092)
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    transform = config['transforms']['Jacket']
    size = tuple(config['canvas'])
    scale = transform['uniform_scale']
    xy = tuple(transform['translate'])
    resized = front.resize(tuple(round(d * scale) for d in front.size), Image.Resampling.LANCZOS)
    placed = Image.new('RGBA', size)
    placed.alpha_composite(resized, xy)
    placed.save(LAY / 'Jacket_Front.png')
    panel([('v16 jacket.png', source), ('v16b jacket-front.png (candidate 03)', front)], PROOFS / 'comparison-side-by-side.png')
    overlay = Image.alpha_composite(source, front)
    overlay.save(PROOFS / 'overlay.png')
    # Opacity is changed ONLY on a temporary review copy, never on delivered art.
    half = front.copy()
    half.putalpha(half.getchannel('A').point(lambda a: round(a * 0.5)))
    overlay_half = Image.alpha_composite(source, half)
    panel([('Original + front at 50% opacity (alignment review)', overlay_half)], PROOFS / 'overlay-half.png')
    panel([('Jacket_Front on 2172 x 2896 canvas', placed)], PROOFS / 'placed-front.png', width=750)
    samples = [(250,250,430,450),(140,650,250,790),(320,600,450,820),
               (990,250,1170,450),(1190,650,1300,790),(970,600,1100,820)]
    src = np.asarray(source).astype(float)
    checks = []
    candidates = []
    for i in range(1, 5):
        path = GEN / f'jacket-front-{i:02}.png'
        art = Image.open(path).convert('RGBA')
        assert art.size == source.size
        a = np.asarray(art).astype(float)
        errors = [float(np.abs(a[y0:y1,x0:x1,:3]-src[y0:y1,x0:x1,:3]).mean()) for x0,y0,x1,y1 in samples]
        checks.append({'candidate': path.name, 'sha256': sha(path), 'sample_rgb_mae': errors, 'mean_sample_rgb_mae': float(np.mean(errors))})
        candidates.append((f'Candidate {i:02}' + (' - SELECTED' if i == 3 else ''), art))
    panel(candidates[:2], PROOFS / 'candidates-01-02.png', width=720)
    panel(candidates[2:], PROOFS / 'candidates-03-04.png', width=720)
    write(LAY / 'placement.json', {'canvas': list(size), 'source_size': list(front.size),
        'source': 'assets/ciel/generated/v16b/jacket-front.png', 'uniform_scale': scale,
        'translate': list(xy), 'resized_size': list(resized.size), 'resampling': 'Pillow LANCZOS',
        'coordinates': 'Top-left of the entire original frame; no crop, rotation, mask or local deformation.',
        'inherited_from': 'assets/ciel/layers/v16/placement.json: transforms.Jacket',
        'canvas_boundary_note': 'Inherited placement extends past left, right and bottom canvas edges. The complete garment remains in the source PNG.'})
    output = Image.open(LAY / 'Jacket_Front.png')
    assert output.mode == 'RGBA' and output.size == size
    assert output.getchannel('A').getextrema() == (0,255)
    assert np.array_equal(np.asarray(output), np.asarray(placed))
    assert sha(SELECTED) == sha(GEN / 'jacket-front.png')
    assert all(sha(ROOT / p) == h for p,h in before.items())
    log = json.loads((GEN / 'generation-log.json').read_text(encoding='utf-8'))
    calls = log['calls'][:1] + [json.loads((GEN / f'generation-{i:02}.json').read_text(encoding='utf-8')) for i in range(2,5)]
    write(GEN / 'generation-summary.json', {'count': len(calls), 'limit': 4, 'selected': SELECTED.name, 'calls': calls})
    write(LAY / 'validation.json', {'generation_count': len(calls), 'selected': SELECTED.name,
        'source_size': list(front.size), 'output_size': list(size), 'mode': output.mode,
        'alpha_extrema': list(output.getchannel('A').getextrema()),
        'selected_source_byte_identical': True, 'placement_pixel_verified': True,
        'reference_hashes_unchanged': before, 'delivered_source_sha256': sha(GEN / 'jacket-front.png'),
        'placed_sha256': sha(LAY / 'Jacket_Front.png'),
        'sample_boxes_xyxy': samples, 'candidate_comparison': checks,
        'metric_limitation': 'RGB MAE on six retained front patches, not a full-image registration guarantee.',
        'prohibited_art_operations_used': [],
        'remaining_issues': ['Small isolated alpha specks and edge residue from image generation remain.',
                             'Generated outlines and details are not pixel-identical to the original.']})
    print(json.dumps({'selected': SELECTED.name, 'size': list(size), 'scale': scale, 'translate': xy,
                      'mean_sample_errors': [c['mean_sample_rgb_mae'] for c in checks]}, indent=2))


if __name__ == '__main__':
    main()
