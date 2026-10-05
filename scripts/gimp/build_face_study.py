"""Run inside GIMP 3 Python batch. Builds an editable B1 study, not a finished rig."""
import json
import os
from pathlib import Path
from gi.repository import Gimp, Gio, Gegl

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
SOURCE = ROOT / 'docs/assets/ciel/production'
OUT = ROOT / 'assets/private/ciel/live2d/gimp/face-study-v1'
OUT.mkdir(parents=True, exist_ok=True)
image = Gimp.Image.new(1086, 1448, Gimp.ImageBaseType.RGB)
records = []


def run_proc(name, **values):
    proc = Gimp.get_pdb().lookup_procedure(name)
    config = proc.create_config()
    config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
    for key, value in values.items():
        config.set_property(key.replace('_', '-'), value)
    result = proc.run(config)
    if result.index(0) != Gimp.PDBStatusType.SUCCESS:
        raise RuntimeError(f'{name}: {result.index(0)}')


def part(name, source, crop, size, position, visible=True, cutoff=180):
    layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image,
                                 Gio.File.new_for_path(str(SOURCE / source)))
    image.insert_layer(layer, None, 0)
    layer.set_name(name)
    x, y, width, height = crop
    layer.resize(width, height, -x, -y)
    # Prototype mask: discard low-alpha haze. Preserve original files for refinement.
    # Hard thresholding may lose fine strokes; this is explicitly not a final mask.
    if cutoff is not None:
        rect = Gegl.Rectangle.new(0, 0, width, height)
        buffer = layer.get_buffer()
        rgba = bytearray(buffer.get(rect, 1.0, 'R\'G\'B\'A u8', Gegl.AbyssPolicy.NONE))
        for i in range(3, len(rgba), 4):
            rgba[i] = 255 if rgba[i] >= cutoff else 0
        buffer.set(rect, 'R\'G\'B\'A u8', bytes(rgba))
        buffer.flush()
        layer.update(0, 0, width, height)
    layer.scale(*size, False)
    layer.set_offsets(*position)
    layer.set_visible(visible)
    records.append(dict(name=name, source=source, crop=list(crop), size=list(size),
                        position=list(position), visible=visible, alpha_cutoff=cutoff))
    return layer


part('Reference_Neutral_v2', 'ciel-neutral-source-v2.png', (0, 0, 1086, 1448),
     (1086, 1448), (0, 0), False, None)
# Face base v1 was at the wrong coordinates. Reposition nose and chin approximately
# against neutral v2; exact contour matching remains a visual editing task.
part('Face_Base_Trial', 'face-base-study-v1.png', (330, 326, 426, 512),
     (256, 307), (415, 363))
for side, col, target_x in [('R', 0, 431), ('L', 1, 566)]:
    part(f'Eye_{side}_Sclera', 'eye-components-study-v1.png',
         ((115 if col == 0 else 625), 535, 345, 215), (85, 53), (target_x, 513))
    part(f'Eye_{side}_Iris', 'eye-components-study-v1.png',
         ((200 if col == 0 else 660), 828, 225, 236), (48, 51), (target_x + 20, 511))
    part(f'Eye_{side}_UpperLash', 'eye-components-study-v1.png',
         ((85 if col == 0 else 632), 1140, 370, 210), (100, 57), (target_x - 9, 497))

# Alternative mouth states are separate hidden study layers, not a mouth rig.
part('Mouth_Open_Study', 'mouth-components-study-v1.png', (1110, 140, 320, 235),
     (40, 29), (523, 600), False)
part('Mouth_Cavity', 'mouth-components-study-v1.png', (600, 630, 340, 235),
     (40, 28), (523, 600), False)
part('Mouth_Teeth', 'mouth-components-study-v1.png', (1120, 620, 295, 110),
     (37, 14), (525, 600), False)
part('Mouth_Tongue', 'mouth-components-study-v1.png', (1135, 748, 270, 130),
     (33, 16), (527, 613), False)
part('Mouth_Closed', 'mouth-components-study-v1.png', (105, 222, 350, 70),
     (39, 8), (524, 607))

xcf = OUT / 'ciel-face-study-v1.xcf'
psd = OUT / 'ciel-face-study-v1.psd'
preview = OUT / 'ciel-face-study-v1.png'
run_proc('gimp-xcf-save', image=image, file=Gio.File.new_for_path(str(xcf)))
run_proc('file-psd-export', image=image, file=Gio.File.new_for_path(str(psd)),
         cmyk=False, duotone=False)
run_proc('file-png-export', image=image, file=Gio.File.new_for_path(str(preview)))


def describe(doc):
    return [dict(name=l.get_name(), width=l.get_width(), height=l.get_height(),
                 offsets=list(l.get_offsets())[1:], visible=l.get_visible(),
                 alpha=l.has_alpha()) for l in doc.get_layers()]


expected = describe(image)
checks = {}
for path in [xcf, psd]:
    loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(path)))
    actual = describe(loaded)
    checks[path.suffix] = dict(layer_count=len(actual), metadata_match=actual == expected,
                              layers=actual)
    loaded.delete()
    if actual != expected:
        raise RuntimeError(f'Layer metadata changed in {path.name}')
report = dict(gimp=Gimp.version(), canvas=[1086, 1448], status='B1 study; not rig-ready',
              layers=records, roundtrip=checks,
              limitations=['Prototype hard alpha masks require edge review',
                           'Coordinates are approximate; silhouette not approved',
                           'Brows, lower lids, closed-eye forms and hair not included',
                           'Cubism import and animation not tested'])
(OUT / 'build-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('CIEL_BUILD_OK ' + str(OUT), flush=True)
image.delete()
