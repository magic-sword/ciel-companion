"""v17 placement/proofs only. No artwork masks, cleanup, painting or deformation."""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / 'assets/ciel/generated/v17'
LAY = ROOT / 'assets/ciel/layers/v17'
CONFIG_PATH = ROOT / 'assets/ciel/layers/v16/placement.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
SIZE = tuple(CONFIG['canvas'])
TRANSFORM = CONFIG['transforms']['Body']
SOURCE = ROOT / TRANSFORM['source']
DRESSED = ROOT / 'assets/ciel/layers/v16c/dressed'
STATE_PATH = ROOT / 'assets/ciel/layers/v15b/layer-state.json'
STATE = json.loads(STATE_PATH.read_text(encoding='utf-8'))
FONT = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 24)
VIEWPORT = (240, 1200, 1950, 2896)


def read_image(path):
    return Image.open(path).convert('RGBA')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def place(art):
    scaled = art.resize(tuple(round(d * TRANSFORM['uniform_scale']) for d in art.size), Image.Resampling.LANCZOS)
    out = Image.new('RGBA', SIZE)
    out.alpha_composite(scaled, tuple(TRANSFORM['translate']))
    return out


def compose(body, jacket=False, hair=False):
    out = Image.new('RGBA', SIZE)
    used = []
    foreground_hair = []

    def add(path):
        out.alpha_composite(read_image(path))
        used.append(str(path.relative_to(ROOT)).replace('\\', '/'))

    if hair:
        add(ROOT / 'assets/ciel/layers/v15b/Hair_Back.png')
    if jacket:
        add(DRESSED / 'Jacket_Back.png')
    add(DRESSED / 'Choker_Back.png')
    out.alpha_composite(body)
    used.append('BODY_ARGUMENT')
    excluded = {'Hair_Back', 'Body', 'Fur_Back', 'Outer_L', 'Outer_R'}
    for layer in STATE['layers']:
        name = layer['name']
        if not layer['visible'] or name in excluded or name.startswith('Choker_'):
            continue
        if not hair and (name.startswith(('Hair_', 'Ear_')) or name == 'Face_Shadow_Hair'):
            continue
        if hair and name.startswith('Hair_'):
            foreground_hair.append(ROOT / layer['path'])
            continue
        add(ROOT / layer['path'])
    if jacket:
        add(DRESSED / 'Jacket_Front.png')
    add(DRESSED / 'Choker_Front.png')
    for path in foreground_hair:
        add(path)
    return out, used


def panel(items, path, viewport=None, width=760):
    # Viewport cropping, labels and background exist only in review images.
    tiles = []
    for label, art in items:
        if viewport:
            art = art.crop(viewport)
        if width:
            art = art.resize((width, round(art.height * width / art.width)), Image.Resampling.LANCZOS)
        tile = Image.new('RGBA', (art.width, art.height + 48), '#424966')
        tile.alpha_composite(art, (0, 48))
        ImageDraw.Draw(tile).text((14, 10), label, font=FONT, fill='white')
        tiles.append(tile)
    out = Image.new('RGB', (sum(t.width for t in tiles), max(t.height for t in tiles)), '#424966')
    x = 0
    for tile in tiles:
        out.paste(tile, (x, 0))
        x += tile.width
    out.save(path)


def main():
    number = int(sys.argv[1])
    final = '--final' in sys.argv[2:]
    candidate = GEN / f'body-candidate-{number:02}.png'
    old_art, new_art = read_image(SOURCE), read_image(candidate)
    assert old_art.size == new_art.size == (1025, 1534)
    old_body, new_body = place(old_art), place(new_art)
    without, no_order = compose(new_body)
    with_jacket, dressed_order = compose(new_body, jacket=True)
    prefix = LAY if final else GEN
    suffix = '' if final else f'-candidate-{number:02}'
    panel([('body-01 / v15', old_art), (f'body-02 / candidate {number:02}', new_art)], prefix / f'compare-body{suffix}.png', width=None)
    panel([('No jacket / no hair', without), ('Jacket + choker / no hair', with_jacket)], prefix / f'compare-upper-body{suffix}.png', viewport=VIEWPORT)
    panel([('Shoulder / sleeve fit', with_jacket)], prefix / f'shoulder-detail{suffix}.png', viewport=(400, 1400, 1840, 2350), width=None)
    if not final:
        return
    shutil.copyfile(candidate, GEN / 'body-02.png')
    new_body.save(LAY / 'Body.png')
    without.save(LAY / 'no-jacket-transparent.png')
    with_jacket.save(LAY / 'dressed-no-hair-transparent.png')
    panel([('No jacket / no hair', without)], LAY / 'no-jacket.png', viewport=VIEWPORT, width=1026)
    panel([('Jacket + choker / no hair', with_jacket)], LAY / 'dressed-no-hair.png', viewport=VIEWPORT, width=1026)
    full, full_order = compose(new_body, jacket=True, hair=True)
    full.save(LAY / 'dressed-transparent.png')
    panel([('v17 / jacket + choker + hair', full)], LAY / 'dressed.png', width=1086)
    candidates = [(f'Candidate {n:02}' + (' / SELECTED' if n == number else ''), read_image(GEN / f'body-candidate-{n:02}.png')) for n in range(1, 5) if (GEN / f'body-candidate-{n:02}.png').exists()]
    panel(candidates, GEN / 'candidates.png', width=420)
    refs = {SOURCE, CONFIG_PATH, STATE_PATH, ROOT / 'assets/ciel/master/ciel-upper-body-2x.png', ROOT / 'assets/ciel/layers/v16c/no-jacket.png'}
    refs.update(ROOT / p for p in no_order + dressed_order + full_order if p != 'BODY_ARGUMENT')
    baseline = GEN / 'reference-hashes.json'
    hashes = {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in sorted(refs)}
    if baseline.exists():
        assert json.loads(baseline.read_text(encoding='utf-8')) == hashes
    else:
        write_json(baseline, hashes)
    placement = {'canvas': list(SIZE), 'source': 'assets/ciel/generated/v17/body-02.png',
                 'source_size': list(new_art.size), 'uniform_scale': TRANSFORM['uniform_scale'],
                 'translate': TRANSFORM['translate'], 'resized_size': [round(d * TRANSFORM['uniform_scale']) for d in new_art.size],
                 'inherited_from': 'assets/ciel/layers/v16/placement.json: transforms.Body',
                 'resampling': 'Pillow LANCZOS', 'rotation': 0,
                 'artwork_operations': ['whole-frame uniform scale', 'translation onto transparent work canvas'],
                 'canvas_note': 'Inherited frame extends 77 pixels below work canvas; complete skirt retained in source PNG.',
                 'proof_viewport': list(VIEWPORT), 'proof_orders': {'no_jacket': no_order, 'dressed_no_hair': dressed_order, 'dressed_hair': full_order}}
    write_json(LAY / 'placement.json', placement)
    a, b = np.asarray(old_art), np.asarray(new_art)
    samples = {}
    for name, box in {'neckline': (395, 0, 620, 300), 'top_center': (270, 300, 750, 1000), 'abdomen_center': (280, 1080, 740, 1340)}.items():
        x0, y0, x1, y1 = box
        first, second = a[y0:y1, x0:x1], b[y0:y1, x0:x1]
        samples[name] = {'xyxy': list(box), 'equal_rgba_fraction': float(np.mean(np.all(first == second, axis=2))),
                         'mean_absolute_rgb_difference_0_255': float(np.abs(first[:, :, :3].astype(float) - second[:, :, :3]).mean())}
    assert sha(candidate) == sha(GEN / 'body-02.png')
    assert np.array_equal(np.asarray(read_image(LAY / 'Body.png')), np.asarray(place(new_art)))
    calls = []
    for path in sorted(GEN.glob('generation-[0-9][0-9].json')):
        record = json.loads(path.read_text(encoding='utf-8'))
        saved = ROOT / record['saved_copy']
        original = Path(record['tool_original'])
        assert sha(saved) == sha(original)
        record['sha256'] = sha(saved)
        calls.append(record)
    assert len(calls) <= 4
    write_json(GEN / 'generation-summary.json', {'generation_count': len(calls), 'limit': 4, 'selected': number, 'calls': calls})
    write_json(LAY / 'validation.json', {'source_size': list(new_art.size), 'layer_size': list(new_body.size), 'mode': new_body.mode,
               'alpha_extrema': list(new_body.getchannel('A').getextrema()), 'selected_candidate': number, 'generation_count': len(calls),
               'tool_copies_byte_identical': True, 'placement_pixel_verified': True, 'prohibited_art_operations_used': [],
               'source_sha256': sha(GEN / 'body-02.png'), 'layer_sha256': sha(LAY / 'Body.png'),
               'reference_hashes': hashes, 'read_only_interior_samples': samples,
               'sample_note': 'Samples measure generation drift only; they do not prove unchanged torso outline.',
               'visual_review': {'horizontal_underarm_mask_cut': False, 'long_skin_triangles_below_fur': False,
                   'torso_pixel_identical': False, 'arm_ends_at_source_side_borders': True,
                   'remaining_issues': ['Minor generated line/shading changes also affect the torso and neckline.',
                       'Small alpha specks and edge residue remain in the raw image.',
                       'Unclothed arms extend more outward than a slight relaxed opening; only the in-frame upper-arm portions are present.',
                       'Existing jacket fur overlap and left/right asymmetry are retained.']}})
    print(json.dumps({'selected': number, 'generation_count': len(calls), 'size': list(new_body.size), 'samples': samples}, indent=2))


if __name__ == '__main__':
    main()
