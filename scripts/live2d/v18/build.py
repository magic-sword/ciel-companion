"""v18: whole-image uniform placement and review composition only.

No artwork painting, masking, alpha cleanup, recoloring, or local deformation.
"""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / 'assets/ciel/generated/v18'
LAY = ROOT / 'assets/ciel/layers/v18'
SIZE = (2172, 2896)
STATE = json.loads((ROOT / 'assets/ciel/layers/v15b/layer-state.json').read_text(encoding='utf-8'))
FONT = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 24)
BODY_SCALE = 1.48
BODY_XY = (306, 1038)
JACKET_SCALE = 1.61
JACKET_XY = (-35, 1280)

def read(path):
    return Image.open(path).convert('RGBA')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def place(art, scale, xy):
    scaled = art.resize(tuple(round(d * scale) for d in art.size), Image.Resampling.LANCZOS)
    out = Image.new('RGBA', SIZE)
    out.alpha_composite(scaled, xy)
    return out

def compose(body_path, front_path, hair=True, jacket=True):
    paths = []
    if hair:
        paths.append('assets/ciel/layers/v15b/Hair_Back.png')
    if jacket:
        paths.append('assets/ciel/layers/v16c/dressed/Jacket_Back.png')
    paths += ['assets/ciel/layers/v16c/dressed/Choker_Back.png', body_path]
    if jacket:
        paths.append(front_path)
    paths.append('assets/ciel/layers/v16c/dressed/Choker_Front.png')
    excluded = {'Hair_Back', 'Body', 'Neck', 'Neck_Shadow_Chin', 'Fur_Back', 'Outer_L', 'Outer_R'}
    for layer in STATE['layers']:
        name = layer['name']
        if not layer['visible'] or name in excluded or name.startswith('Choker_'):
            continue
        if not hair and (name.startswith(('Hair_', 'Ear_')) or name == 'Face_Shadow_Hair'):
            continue
        paths.append(layer['path'])
    out = Image.new('RGBA', SIZE)
    for path in paths:
        out.alpha_composite(read(ROOT / path))
    return out, paths

def panel(items, path, viewport=None, width=724):
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
    b = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    j = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    body_source = GEN / f'body-candidate-{b:02}.png'
    jacket_source = GEN / f'jacket-front-candidate-{j:02}.png'
    body_art, jacket_art = read(body_source), read(jacket_source)
    assert jacket_art.size == (1441, 1092)
    body = place(body_art, BODY_SCALE, BODY_XY)
    front = place(jacket_art, JACKET_SCALE, JACKET_XY)
    body.save(LAY / 'Body.png')
    front.save(LAY / 'Jacket_Front.png')
    v18, order = compose('assets/ciel/layers/v18/Body.png', 'assets/ciel/layers/v18/Jacket_Front.png')
    v17, order17 = compose('assets/ciel/layers/v17/Body.png', 'assets/ciel/layers/v16c/dressed/Jacket_Front.png')
    original = read(ROOT / 'assets/ciel/master/ciel-upper-body-2x.png')
    items = [('Approved original', original), ('v17 / same layer order', v17), ('v18', v18)]
    panel(items, LAY / 'compare-upper-body.png')
    panel(items, LAY / 'compare-neck-shoulders.png', viewport=(450, 1210, 1780, 2110), width=900)
    v18.save(LAY / 'dressed-transparent.png')
    v17.save(GEN / 'v17-same-order-transparent.png')
    panel([('v18', v18)], LAY / 'dressed.png', width=1086)
    panel([('Body only / no jacket, hair or choker', body)], LAY / 'body-only.png', viewport=(0, 1220, 2172, 2896), width=1086)
    panel([('Body original generated frame', body_art)], LAY / 'body-source-review.png', width=760)
    bare, bare_order = compose('assets/ciel/layers/v18/Body.png', 'assets/ciel/layers/v18/Jacket_Front.png', hair=False, jacket=False)
    clothed, no_hair_order = compose('assets/ciel/layers/v18/Body.png', 'assets/ciel/layers/v18/Jacket_Front.png', hair=False)
    bare.save(LAY / 'no-jacket-no-hair-transparent.png')
    clothed.save(LAY / 'dressed-no-hair-transparent.png')
    panel([('No jacket / no hair', bare), ('Dressed / no hair', clothed)], LAY / 'compare-no-hair.png', viewport=(100, 1250, 2072, 2896), width=850)
    old_front = read(ROOT / 'assets/ciel/layers/v16c/Jacket_Front.png')
    panel([('v16c front', old_front), ('v18 front', front)], LAY / 'compare-jacket-front.png', viewport=(0, 1250, 2172, 2896), width=900)
    body_items = [(f'Body attempt {n:02}' + (' / selected' if n == b else ''), read(GEN / f'body-candidate-{n:02}.png')) for n in (1, 3, 4)]
    panel(body_items, GEN / 'body-candidates.png', width=540)
    jacket_items = [(f'Front attempt {n:02}' + (' / selected' if n == j else ''), read(p)) for n in range(1, 5) if (p := GEN / f'jacket-front-candidate-{n:02}.png').exists()]
    panel(jacket_items, GEN / 'jacket-candidates.png', width=650)
    log = json.loads((GEN / 'generation-log.json').read_text(encoding='utf-8'))
    for record in log:
        if record['status'] != 'success':
            continue
        saved, tool = GEN / record['file'], Path(record['tool_original'])
        assert sha(saved) == sha(tool)
    refs = set(order + order17 + bare_order + no_hair_order)
    refs.update(['assets/ciel/master/ciel-upper-body-2x.png', 'assets/ciel/generated/v16/jacket.png', 'assets/ciel/layers/v16c/placement.json', 'assets/ciel/layers/v15b/layer-state.json', 'assets/ciel/generated/v18/inputs/user-note-shoulder-fur.png'])
    refs = sorted(p for p in refs if '/v18/' not in p or '/inputs/' in p)
    hashes = {p: sha(ROOT / p) for p in refs}
    baseline = GEN / 'reference-hashes.json'
    if baseline.exists():
        assert hashes == json.loads(baseline.read_text(encoding='utf-8'))
    else:
        write(baseline, hashes)
    placements = {}
    for name, source, art, scale, xy in [('Body', body_source, body_art, BODY_SCALE, BODY_XY), ('Jacket_Front', jacket_source, jacket_art, JACKET_SCALE, JACKET_XY)]:
        placements[name] = {'source': source.relative_to(ROOT).as_posix(), 'source_size': list(art.size), 'uniform_scale': scale, 'translate': list(xy), 'resized_size': [round(d * scale) for d in art.size], 'rotation': 0, 'resampling': 'Pillow LANCZOS', 'operations': ['whole-frame uniform scale', 'translation onto transparent canvas']}
        assert np.array_equal(np.asarray(read(LAY / f'{name}.png')), np.asarray(place(art, scale, xy)))
    write(LAY / 'placement.json', {'canvas': SIZE, 'transforms': placements, 'jacket_inherits': 'assets/ciel/layers/v16c/placement.json', 'orders': {'v18': order, 'v17_comparison': order17, 'no_jacket_no_hair': bare_order, 'dressed_no_hair': no_hair_order}, 'neck_note': 'New Body includes its own neck; old Neck and Neck_Shadow_Chin excluded from face layers.'})
    counts = {kind: sum(r['kind'] == kind for r in log) for kind in ('Body', 'Jacket_Front')}
    assert all(n <= 4 for n in counts.values())
    assert all(r['referenced_image_paths'] == ['assets/ciel/master/ciel-upper-body-2x.png'] for r in log if r['kind'] == 'Body')
    inherited = json.loads((ROOT / 'assets/ciel/layers/v16c/placement.json').read_text(encoding='utf-8'))
    assert inherited['uniform_scale'] == JACKET_SCALE and inherited['translate'] == list(JACKET_XY)
    write(GEN / 'generation-summary.json', {'attempt_counts_including_failure': counts, 'successful_image_counts': {kind: sum(r['kind'] == kind and r['status'] == 'success' for r in log) for kind in counts}, 'limit_per_layer': 4, 'selected': {'Body': b, 'Jacket_Front': j}, 'all_body_references_original_only': True, 'all_saved_images_match_tool_originals': True, 'full_log': 'generation-log.json'})
    samples = {}
    a = np.asarray(front)
    for name, box in {'neck_left_rear': (730, 1390, 840, 1520), 'neck_right_rear': (1410, 1390, 1515, 1520), 'central_chest': (930, 1620, 1290, 2150), 'central_abdomen': (900, 2470, 1330, 2680)}.items():
        x0, y0, x1, y1 = box
        alpha = a[y0:y1, x0:x1, 3]
        old_alpha = np.asarray(old_front)[y0:y1, x0:x1, 3]
        samples[name] = {'xyxy': box, 'v18_pixels_alpha_over_127': int((alpha > 127).sum()), 'v16c_pixels_alpha_over_127': int((old_alpha > 127).sum()), 'v18_max_alpha': int(alpha.max())}
    write(LAY / 'validation.json', {'canvas': SIZE, 'mode': 'RGBA', 'selected_body_attempt': b, 'selected_jacket_attempt': j, 'generation_attempt_counts_including_failure': counts, 'tool_copies_byte_identical': True, 'placement_pixel_verified': True, 'reference_hashes_unchanged_since_first_build': True, 'reference_hashes': hashes, 'source_hashes': {'body': sha(body_source), 'jacket': sha(jacket_source)}, 'output_hashes': {'Body': sha(LAY / 'Body.png'), 'Jacket_Front': sha(LAY / 'Jacket_Front.png')}, 'alpha_extrema': {'Body': body.getchannel('A').getextrema(), 'Jacket_Front': front.getchannel('A').getextrema()}, 'prohibited_art_operations_used': [], 'read_only_front_samples': samples, 'samples_note': 'Rectangles check representative regions, not the entire overlap silhouette.'})
    write(LAY / 'visual-review.json', {'body': {'selected': b, 'observations': ['Shoulder and arm contours are smoother and broader than v17.', 'Cool porcelain skin and shaded volume retained.', 'The torso still has stronger bust/waist shaping than the requested young natural proportions.', 'Black neckline design was redrawn and differs from the original.', 'Forearms intersect the source side borders near the lower part of the proof.']}, 'jacket_front': {'selected': j, 'observations': ['Medial upper shoulder fur lobes removed; rear collar remains only in unchanged Jacket_Back.', 'Large front panels, folded lapels and cyan lining webs removed.', 'Retained fur and sleeves are not pixel-identical to v16/v16c.', 'Some downward fur tips still overlap the outer edges of the top.']}, 'composite': {'observations': ['Upper-arm skin remains visible inside the existing sleeves.', 'Fine generated alpha residue remains; no programmatic cleanup was applied.'], 'live2d_motion_tested': False}, 'strict_zero_top_overlap_achieved': False})
    print(json.dumps({'selected': {'body': b, 'jacket': j}, 'placements': placements, 'samples': samples}, indent=2))

if __name__ == '__main__':
    main()
