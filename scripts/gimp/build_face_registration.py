"""Preserve the approved normal face exactly while partitioning visible regions.

This is a registration baseline, NOT rig-ready cutouts: exposed skin, hair overlap
and the original background stay intact. No hidden reference supplies the preview.
"""
import hashlib
import json
import os
from pathlib import Path
from gi.repository import Gimp, Gio, Gegl

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
SOURCE = ROOT / 'docs/assets/ciel/ciel-approved-appearance-v1.png'
OUT = ROOT / 'assets/private/ciel/live2d/gimp/face-registration-v4'
OUT.mkdir(parents=True, exist_ok=True)
FMT = "R'G'B'A u8"
# Coordinates in the approved sheet's large left-hand portrait. No resizing.
CROP = (330, 235, 280, 195)
W, H = CROP[2:]
RECT = Gegl.Rectangle.new(0, 0, W, H)


def run_proc(name, **values):
    config = Gimp.get_pdb().lookup_procedure(name).create_config()
    config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
    for key, value in values.items():
        config.set_property(key.replace('_', '-'), value)
    result = Gimp.get_pdb().lookup_procedure(name).run(config)
    if result.index(0) != Gimp.PDBStatusType.SUCCESS:
        raise RuntimeError(f'{name}: {result.index(0)}')


def pixels(layer):
    return bytes(layer.get_buffer().get(RECT, 1.0, FMT, Gegl.AbyssPolicy.NONE))


def new_layer(doc, name, rgba, x=0):
    layer = Gimp.Layer.new(doc, name, W, H, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
    doc.insert_layer(layer, None, 0)
    buf = layer.get_buffer()
    buf.set(RECT, FMT, bytes(rgba))
    buf.flush()
    layer.update(0, 0, W, H)
    layer.set_offsets(x, 0)
    return layer


original = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(SOURCE)))
original.crop(W, H, CROP[0], CROP[1])
reference = pixels(original.get_layers()[0])
run_proc('file-png-export', image=original, file=Gio.File.new_for_path(str(OUT / 'approved-face-crop.png')))
# Polygon coordinates relative to the crop. Boundaries are ownership boundaries,
# not finished alpha silhouettes. The rest layer has real holes under each region.
regions = {
    'Eye_R_VisibleRegion': [(36, 67), (52, 49), (84, 47), (107, 61), (113, 82), (101, 104), (62, 110), (44, 94)],
    'Eye_L_VisibleRegion': [(167, 62), (188, 48), (221, 47), (240, 66), (239, 91), (217, 110), (181, 105), (168, 84)],
    'Nose_VisibleRegion': [(128, 103), (152, 103), (152, 127), (128, 127)],
    'Mouth_Closed_VisibleRegion': [(116, 133), (165, 133), (165, 149), (116, 149)],
}


def inside(x, y, poly):
    result = False
    j = len(poly) - 1
    for i, (xi, yi) in enumerate(poly):
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            result = not result
        j = i
    return result


eye_geometry = {
    'R': {'iris': [(72, 59), (89, 58), (104, 65), (108, 80), (106, 96), (99, 104), (77, 105), (67, 94), (65, 76)],
          'opening': [(53, 77), (60, 68), (73, 63), (95, 62), (107, 73), (106, 91), (100, 101), (79, 103), (60, 99), (53, 91)],
          'pupil': [87, 79, 4.5, 7.5], 'lower_y': 98},
    'L': {'iris': [(180, 58), (194, 56), (209, 60), (216, 73), (216, 88), (209, 102), (188, 103), (176, 98), (173, 82), (175, 67)],
          'opening': [(171, 73), (181, 62), (200, 58), (217, 64), (226, 72), (226, 88), (214, 98), (192, 101), (178, 97), (173, 86)],
          'pupil': [193, 77, 4.0, 7.5], 'lower_y': 98},
}
components = ['Sclera_Visible', 'Iris_Visible', 'Pupil_Visible', 'Highlight_Visible',
              'UpperLash_Visible', 'LowerLid_Visible', 'EdgeContext']
names = ['Face_Context_Remainder', 'Nose_VisibleRegion', 'Mouth_UpperLine_Visible', 'Mouth_LowerEdge_Context']
names += [f'Eye_{side}_{component}' for side in ['R', 'L'] for component in components]
buffers = {name: bytearray(W * H * 4) for name in names}
counts = {name: 0 for name in buffers}
for y in range(H):
    for x in range(W):
        matches = [name for name, poly in regions.items() if inside(x + .5, y + .5, poly)]
        if len(matches) > 1:
            raise RuntimeError('Overlapping ownership regions')
        owner = matches[0] if matches else 'Face_Context_Remainder'
        i = 4 * (y * W + x)
        if owner.startswith('Eye_'):
            side = owner.split('_')[1]
            g = eye_geometry[side]
            rgb = reference[i:i + 3]
            component = 'EdgeContext'
            if inside(x + .5, y + .5, g['iris']):
                px, py, rx, ry = g['pupil']
                if y < 75 and rgb[0] > 210 and rgb[1] > 225 and rgb[2] > 230:
                    component = 'Highlight_Visible'
                elif ((x + .5 - px) / rx) ** 2 + ((y + .5 - py) / ry) ** 2 <= 1:
                    component = 'Pupil_Visible'
                else:
                    component = 'Iris_Visible'
            elif max(rgb) < 180 and y < 95:
                component = 'UpperLash_Visible'
            elif g['lower_y'] <= y <= 105 and min(rgb) < 215:
                component = 'LowerLid_Visible'
            elif inside(x + .5, y + .5, g['opening']):
                component = 'Sclera_Visible'
            owner = f'Eye_{side}_{component}'
        elif owner == 'Mouth_Closed_VisibleRegion':
            owner = 'Mouth_UpperLine_Visible' if y <= 142 else 'Mouth_LowerEdge_Context'
        buffers[owner][i:i + 4] = reference[i:i + 4]
        counts[owner] += 1

# Conservative opaque upper-edge holdout, not a physically separated shadow.
# Restrict to the top of the iris so the pupil and lower rim never become fixed.
shadow_rule = dict(max_y_exclusive=72, max_green_exclusive=110)
for side in ['R', 'L']:
    name = f'Eye_{side}_UpperOcclusion_Visible'
    rgba = bytearray(W * H * 4)
    source = buffers[f'Eye_{side}_Iris_Visible']
    count = 0
    for i in range(0, len(reference), 4):
        if source[i + 3] and (i // 4) // W < 72 and source[i + 1] < 110:
            rgba[i:i + 4] = source[i:i + 4]
            source[i:i + 4] = bytes(4)
            count += 1
    assert count > 0
    buffers[name] = rgba
    counts[name] = count
    counts[f'Eye_{side}_Iris_Visible'] -= count

fills = {}
fill_records = {}


def interpolate(samples, x, y):
    """Conservative local color continuation; does not modify visible source pixels."""
    nearest = sorted(samples, key=lambda s: (s[0] - x) ** 2 + 4 * (s[1] - y) ** 2)[:8]
    weights = [1 / (1 + (sx - x) ** 2 + 4 * (sy - y) ** 2) for sx, sy, _ in nearest]
    return bytes(round(sum(s[2][c] * w for s, w in zip(nearest, weights)) / sum(weights))
                 for c in range(3)) + bytes([255])


for side in ['R', 'L']:
    iris_names = [f'Eye_{side}_{n}_Visible' for n in ['Iris', 'Pupil', 'Highlight']]
    iris_mask = [i for i in range(0, len(reference), 4) if any(buffers[n][i + 3] for n in iris_names)]
    occluded = [i for i in range(0, len(reference), 4)
                if buffers[f'Eye_{side}_UpperOcclusion_Visible'][i + 3]]
    holes = occluded + [i for i in iris_mask if buffers[f'Eye_{side}_Pupil_Visible'][i + 3]
             or buffers[f'Eye_{side}_Highlight_Visible'][i + 3]]
    for kind, source_name, targets in [('Sclera', f'Eye_{side}_Sclera_Visible', iris_mask),
                                       ('Iris', f'Eye_{side}_Iris_Visible', holes)]:
        samples = []
        for i in range(0, len(reference), 4):
            if not buffers[source_name][i + 3]:
                continue
            rgb = reference[i:i + 3]
            if kind == 'Sclera' and (min(rgb) < 150 or max(rgb) - min(rgb) > 50):
                continue
            if kind == 'Iris' and (rgb[1] < 85 or rgb[2] - rgb[0] < 35):
                continue
            samples.append(((i // 4) % W, (i // 4) // W, rgb))
        assert samples, f'No usable color samples for {source_name}'
        name = f'Eye_{side}_{kind}_HiddenFill'
        rgba = bytearray(W * H * 4)
        for i in targets:
            rgba[i:i + 4] = interpolate(samples, (i // 4) % W, (i // 4) // W)
        fills[name] = rgba
        fill_records[name] = dict(filled_pixels=len(targets), source=source_name,
                                 sample_count=len(samples), method='8-neighbor inverse-distance RGB interpolation; y distance weighted 4x')

all_buffers = {**fills, **buffers}
image = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
for name, rgba in all_buffers.items():
    new_layer(image, name, rgba)


def composite(doc):
    layer = Gimp.Layer.new_from_visible(doc, doc, 'Verification_Only')
    doc.insert_layer(layer, None, 0)
    result = pixels(layer)
    doc.remove_layer(layer)
    return result


def compare(actual):
    differences = [abs(a - b) for a, b in zip(reference, actual)]
    return dict(equal=actual == reference,
                changed_pixels=sum(any(differences[i:i + 4]) for i in range(0, len(differences), 4)),
                max_channel_difference=max(differences), sha256=hashlib.sha256(actual).hexdigest())


checks = {'in_memory': compare(composite(image))}
if not checks['in_memory']['equal']:
    raise RuntimeError(f'Reconstruction mismatch: {checks}')
for suffix, proc in [('xcf', 'gimp-xcf-save'), ('psd', 'file-psd-export')]:
    path = OUT / ('ciel-face-registration-v4.' + suffix)
    run_proc(proc, image=image, file=Gio.File.new_for_path(str(path)))
    loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(path)))
    checks[suffix] = compare(composite(loaded))
    checks[suffix]['layer_names'] = [layer.get_name() for layer in loaded.get_layers()]
    checks[suffix]['partition_match'] = all(pixels(layer) == bytes(all_buffers[layer.get_name()]) for layer in loaded.get_layers())
    assert len(loaded.get_layers()) == len(all_buffers)
    assert checks[suffix]['equal'] and checks[suffix]['partition_match'], checks[suffix]
    loaded.delete()

run_proc('file-png-export', image=image, file=Gio.File.new_for_path(str(OUT / 'reconstructed-face.png')))
sheet = Gimp.Image.new(W * 2, H, Gimp.ImageBaseType.RGB)
new_layer(sheet, 'Left_ApprovedCrop', reference)
new_layer(sheet, 'Right_Reconstructed', composite(image), W)
run_proc('file-png-export', image=sheet, file=Gio.File.new_for_path(str(OUT / 'comparison.png')))
sheet.delete()
# Removing each feature must change the result. This rules out a hidden full-face
# backing layer falsely making the exact-reconstruction test pass.
ablation = {}
for layer in image.get_layers():
    if layer.get_name() == 'Face_Context_Remainder' or layer.get_name() in fills:
        continue
    layer.set_visible(False)
    ablation[layer.get_name()] = compare(composite(image))['changed_pixels']
    layer.set_visible(True)
    assert ablation[layer.get_name()] > 0
    # Export each real partition independently at its original canvas position.
    single = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
    new_layer(single, layer.get_name(), buffers[layer.get_name()])
    run_proc('file-png-export', image=single,
             file=Gio.File.new_for_path(str(OUT / (layer.get_name() + '.png'))))
    single.delete()

# Expose the painted areas separately so exact normal-state reconstruction cannot
# conceal holes or poor fill quality. These are inspection views, not expressions.
diagnostics = Gimp.Image.new(W * 3, H, Gimp.ImageBaseType.RGB)
new_layer(diagnostics, 'Normal', reference)
coverage = {}
for column, hidden in [(1, ['Pupil', 'Highlight']), (2, ['Iris', 'Pupil', 'Highlight'])]:
    for layer in image.get_layers():
        if any(layer.get_name() == f'Eye_{side}_{name}_Visible' for side in ['R', 'L'] for name in hidden):
            layer.set_visible(False)
        if column == 2 and layer.get_name().endswith('_Iris_HiddenFill'):
            layer.set_visible(False)
    exposed = composite(image)
    for side in ['R', 'L']:
        targets = [i for i in range(0, len(reference), 4)
                   if any(buffers[f'Eye_{side}_{name}_Visible'][i + 3] for name in hidden)]
        holes = sum(exposed[i + 3] != 255 for i in targets)
        coverage[f'{side}_stage_{column}'] = dict(exposed_pixels=len(targets), nonopaque_pixels=holes)
        assert holes == 0, coverage
    new_layer(diagnostics, f'Inspection_{column}', exposed, W * column)
run_proc('file-png-export', image=diagnostics, file=Gio.File.new_for_path(str(OUT / 'fill-inspection.png')))
diagnostics.delete()
for layer in image.get_layers():
    layer.set_visible(True)
assert compare(composite(image))['equal']

# Translate the iris as a unit, clipped to the existing visible eye opening.
# This is a diagnostic only: keep the saved normal XCF/PSD untouched.
moving_names = [f'Eye_{side}_{part}_Visible' for side in ['R', 'L']
                for part in ['Iris', 'Pupil', 'Highlight']]
for layer in image.get_layers():
    if layer.get_name() in moving_names or layer.get_name().endswith('_Iris_HiddenFill'):
        layer.set_visible(False)
gaze_base = composite(image)
for layer in image.get_layers():
    layer.set_visible(True)
gaze_records = {}
gaze_sheet = Gimp.Image.new(W * 5, H, Gimp.ImageBaseType.RGB)
for column, dx in enumerate([-4, -2, 0, 2, 4]):
    gaze = bytearray(gaze_base)
    clipped = 0
    moved = 0
    allowed = set()
    for side in ['R', 'L']:
        parts = [buffers[f'Eye_{side}_{part}_Visible'] for part in ['Iris', 'Pupil', 'Highlight']]
        sclera = buffers[f'Eye_{side}_Sclera_Visible']
        opening = {i for i in range(0, len(reference), 4)
                   if sclera[i + 3] or any(part[i + 3] for part in parts)}
        allowed.update(opening)
        moving = bytearray(fills[f'Eye_{side}_Iris_HiddenFill'])
        for part in parts:
            for i in range(0, len(reference), 4):
                if part[i + 3]:
                    moving[i:i + 4] = part[i:i + 4]
        for i in range(0, len(reference), 4):
            if not moving[i + 3]:
                continue
            x = (i // 4) % W
            target = i + dx * 4
            if not 0 <= x + dx < W or target not in opening:
                clipped += 1
                continue
            gaze[target:target + 4] = moving[i:i + 4]
            moved += 1
    outside_changes = sum(gaze[i:i + 4] != reference[i:i + 4]
                          for i in range(0, len(reference), 4) if i not in allowed)
    holes = sum(gaze[i + 3] != 255 for i in allowed)
    fixed_changes = sum(gaze[i:i + 4] != reference[i:i + 4]
                        for side in ['R', 'L'] for i in range(0, len(reference), 4)
                        if buffers[f'Eye_{side}_UpperOcclusion_Visible'][i + 3])
    assert fixed_changes == 0
    assert holes == 0 and outside_changes == 0
    if dx == 0:
        assert bytes(gaze) == reference
    gaze_records[str(dx)] = dict(offset_pixels=dx, moved_pixels=moved,
                                  clipped_pixels=clipped, nonopaque_eye_pixels=holes,
                                  changed_pixels_outside_eyes=outside_changes,
                                  changed_upper_occlusion_pixels=fixed_changes,
                                  comparison=compare(gaze))
    new_layer(gaze_sheet, f'Gaze_dx_{dx}', gaze, column * W)
run_proc('file-png-export', image=gaze_sheet,
         file=Gio.File.new_for_path(str(OUT / 'gaze-inspection.png')))
gaze_sheet.delete()
assert compare(composite(image))['equal']

# Ownership preview highlights provisional edges without changing production pixels.
palette = [(244, 246, 250), (160, 100, 200), (230, 80, 110), (240, 170, 120),
           (180, 205, 240), (0, 175, 205), (35, 40, 90), (255, 220, 30),
           (180, 55, 65), (240, 130, 45), (210, 210, 210)]
ownership = bytearray(W * H * 4)
legend = {}
for n, (name, rgba) in enumerate(buffers.items()):
    color = (150, 75, 210) if name.endswith('_UpperOcclusion_Visible') else (palette[n] if n < 11 else palette[n - 7])
    legend[name] = list(color)
    for i in range(0, len(rgba), 4):
        if rgba[i + 3]:
            ownership[i:i + 4] = bytes((*color, 255))
map_doc = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
new_layer(map_doc, 'Region_Ownership', ownership)
run_proc('file-png-export', image=map_doc, file=Gio.File.new_for_path(str(OUT / 'ownership-map.png')))
map_doc.delete()
report = dict(source='docs/assets/ciel/ciel-approved-appearance-v1.png',
              source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              crop=list(CROP), canvas=[W, H], scale=1, gimp=Gimp.version(),
              stage='Visible-region registration baseline, not rig-ready parts',
              regions=regions, eye_geometry=eye_geometry, ownership_colors=legend,
              assigned_pixel_counts=counts, hidden_fills=fill_records, fill_coverage=coverage, checks=checks,
              gaze_translation_checks=gaze_records, upper_occlusion_rule=shadow_rule,
              feature_removal_changed_pixels=ablation,
              limitations=['Semantic boundaries are provisional manual polygons and color rules',
                           'EdgeContext retains original skin/hair and antialias pixels',
                           'Hidden fills are interpolated prototypes, not approved hand-painted textures',
                           'Iris outside its currently visible outline is not reconstructed',
                           'Background retained; no clean character silhouette yet',
                           'Horizontal integer translation preview only; no Cubism or mesh deformation tests',
                           'Upper occlusion is a provisional opaque holdout, not a translucent shadow',
                           'No blink/open-mouth shapes; some mixed boundary pixels remain',
                           'Original resolution retained; not final production resolution'])
(OUT / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('CIEL_REGISTRATION_OK ' + json.dumps(checks), flush=True)
image.delete()
original.delete()
