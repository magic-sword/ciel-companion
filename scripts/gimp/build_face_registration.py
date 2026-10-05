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
OUT = ROOT / 'assets/private/ciel/live2d/gimp/face-registration-v1'
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


buffers = {name: bytearray(W * H * 4) for name in ['Face_Context_Remainder', *regions]}
counts = {name: 0 for name in buffers}
for y in range(H):
    for x in range(W):
        matches = [name for name, poly in regions.items() if inside(x + .5, y + .5, poly)]
        if len(matches) > 1:
            raise RuntimeError('Overlapping ownership regions')
        owner = matches[0] if matches else 'Face_Context_Remainder'
        i = 4 * (y * W + x)
        buffers[owner][i:i + 4] = reference[i:i + 4]
        counts[owner] += 1

image = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
for name, rgba in buffers.items():
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
    path = OUT / ('ciel-face-registration-v1.' + suffix)
    run_proc(proc, image=image, file=Gio.File.new_for_path(str(path)))
    loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(path)))
    checks[suffix] = compare(composite(loaded))
    checks[suffix]['layer_names'] = [layer.get_name() for layer in loaded.get_layers()]
    checks[suffix]['partition_match'] = all(pixels(layer) == bytes(buffers[layer.get_name()]) for layer in loaded.get_layers())
    assert len(loaded.get_layers()) == 5
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
    if layer.get_name() not in regions:
        continue
    layer.set_visible(False)
    ablation[layer.get_name()] = compare(composite(image))['changed_pixels']
    layer.set_visible(True)
    assert ablation[layer.get_name()] > 0
report = dict(source='docs/assets/ciel/ciel-approved-appearance-v1.png',
              source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              crop=list(CROP), canvas=[W, H], scale=1, gimp=Gimp.version(),
              stage='Visible-region registration baseline, not rig-ready parts',
              regions=regions, assigned_pixel_counts=counts, checks=checks,
              feature_removal_changed_pixels=ablation,
              limitations=['Original skin/hair overlap retained within visible regions',
                           'Background retained; no clean character silhouette yet',
                           'No occluded-area painting or blink/open-mouth shapes',
                           'Original resolution retained; not final production resolution'])
(OUT / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('CIEL_REGISTRATION_OK ' + json.dumps(checks), flush=True)
image.delete()
original.delete()
