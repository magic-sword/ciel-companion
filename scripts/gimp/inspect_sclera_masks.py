"""Inspect the two actual PSD mask layers without changing production material."""
import hashlib
import json
import os
from pathlib import Path
from gi.repository import Gimp, Gio, Gegl

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
OUT = ROOT / 'assets/private/ciel/live2d/gimp/sclera-mask-inspection'
OUT.mkdir(parents=True, exist_ok=True)
W, H = 280, 195
CW, CH = 90, 70
FMT = "R'G'B'A u8"
board = Gimp.Image.new(CW * 3, CH * 4, Gimp.ImageBaseType.RGB)
records = []
for version in (5, 6):
    path = ROOT / f'assets/private/ciel/live2d/gimp/cubism-eye-material-v{version}/semantic-hair-parts.psd'
    doc = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(path)))
    layers = {layer.get_name(): layer for layer in doc.get_layers()}
    for side_index, (side, crop_x) in enumerate((('L', 160), ('R', 30))):
        row = (version - 5) * 2 + side_index
        masks = []
        for name in ('Sclera', 'Sclera_Hidden'):
            buf = bytes(layers[f'{side}_{name}'].get_buffer().get(
                Gegl.Rectangle.new(0, 0, W, H), 1.0, FMT, Gegl.AbyssPolicy.NONE))
            masks.append(buf[3::4])
        # Source-space alpha union; this is not a simulation of Cubism filtering.
        union = bytes(round(255 * (1 - (1-a/255)*(1-b/255))) for a,b in zip(*masks))
        record = dict(version=version, side=side, psd_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), masks={})
        for col, (name, alpha) in enumerate(zip(('Sclera', 'Sclera_Hidden', 'union'), (*masks, union))):
            opaque = sum(a == 255 for a in alpha)
            partial = sum(0 < a < 255 for a in alpha)
            record['masks'][name] = dict(opaque_pixels=opaque, partial_alpha_pixels=partial)
            rgba = bytes(c for y in range(40, 40+CH) for x in range(crop_x, crop_x+CW)
                         for c in (alpha[y*W+x],)*3+(255,))
            layer = Gimp.Layer.new(board, f'v{version}_{side}_{name}', CW, CH,
                                  Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
            board.insert_layer(layer, None, 0)
            layer.get_buffer().set(Gegl.Rectangle.new(0,0,CW,CH), FMT, rgba)
            layer.set_offsets(col*CW, row*CH)
        records.append(record)
    doc.delete()
Gimp.context_set_interpolation(Gimp.InterpolationType.NONE)
board.scale(CW*3*4, CH*4*4)
proc = Gimp.get_pdb().lookup_procedure('file-png-export')
cfg = proc.create_config()
cfg.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
cfg.set_property('image', board)
cfg.set_property('file', Gio.File.new_for_path(str(OUT/'sclera-mask-alpha.png')))
assert proc.run(cfg).index(0) == Gimp.PDBStatusType.SUCCESS
board.delete()
(OUT/'report.json').write_text(json.dumps(dict(
    status='diagnostic_only', rows=['v5 L','v5 R','v6 L','v6 R'],
    columns=['visible sclera alpha','hidden sclera alpha','source-space alpha union'],
    enlargement='4x nearest-neighbor to expose source pixels, not app appearance',
    records=records,
    limits=['Does not simulate Cubism mesh deformation or texture filtering',
            'Does not prove the cause of the observed Cubism edge defect']), indent=2)+'\n', encoding='utf-8')
print('SCLERA_MASK_INSPECTION_READY', flush=True)
