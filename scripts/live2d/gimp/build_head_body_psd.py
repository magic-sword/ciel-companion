"""Assemble the head and body layers into a PSD for Cubism.

GIMP 3 batch script (run with python-fu-eval; see the production spec, section 12.3).
Input:  assets/ciel/layers/head/{Hair_Under_Ear,Ear_R,Ear_L,Face_Skin,Hair_Front}.png
        (scripts/live2d/build-head-layers.py, build-ear-layers.py)
        assets/ciel/layers/body/{Body_Base,Outer_R,Outer_L,Waist_Belt,Chest_Gem,Neck_Gear}.png
        (scripts/live2d/build-body-layers.py)
Output: assets/ciel/psd/ciel-head-body.{psd,xcf}, head-body-report.json
Add this PSD to the existing model in Cubism ("add all layers as new art meshes"), not as a replacement of the
13-layer PSD (replacing shifts the layer ids). The layers are saved in the stacking order below (bottom first),
but Cubism puts newly added layers on top, so set the draw order values (see the spec).
"""
import os, json, hashlib
from pathlib import Path
from gi.repository import Gimp, Gio

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
SRC = ROOT / 'assets/ciel'
OUT = SRC / 'psd'
OUT.mkdir(parents=True, exist_ok=True)

def run_proc(name, **values):
    proc = Gimp.get_pdb().lookup_procedure(name)
    config = proc.create_config()
    config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
    for key, value in values.items(): config.set_property(key.replace('_', '-'), value)
    result = proc.run(config)
    if result.index(0) != Gimp.PDBStatusType.SUCCESS: raise RuntimeError(name)

# bottom -> top
names = [('body', 'Body_Base'), ('body', 'Outer_R'), ('body', 'Outer_L'), ('body', 'Waist_Belt'),
         ('body', 'Chest_Gem'), ('body', 'Neck_Gear'), ('head', 'Hair_Under_Ear'), ('head', 'Ear_R'),
         ('head', 'Ear_L'), ('head', 'Face_Skin'), ('head', 'Hair_Front')]
stack = [(n, SRC / 'layers' / d / f'{n}.png', True) for d, n in names]
for _, path, _ in stack: assert path.exists(), f'missing {path}; run the layer scripts first'

W, H = 2172, 2896
doc = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
for name, path, visible in stack:
    item = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, doc, Gio.File.new_for_path(str(path)))
    item.set_name(name)
    doc.insert_layer(item, None, 0)
    item.set_visible(visible)
assert [l.get_name() for l in doc.get_layers()] == [n for n, _, _ in reversed(stack)]

checks = {}
for suffix, proc in [('xcf', 'gimp-xcf-save'), ('psd', 'file-psd-export')]:
    target = OUT / f'ciel-head-body.{suffix}'
    run_proc(proc, image=doc, file=Gio.File.new_for_path(str(target)))
    loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(target)))
    got = [l.get_name() for l in loaded.get_layers()]
    assert got == [n for n, _, _ in reversed(stack)], got
    checks[suffix] = dict(layers=len(got), names_equal=True)
    loaded.delete()
doc.delete()

report = dict(generatedBy='scripts/live2d/gimp/build_head_body_psd.py', canvas=[W, H],
              order_bottom_to_top=[n for n, _, _ in stack], roundtrip=checks,
              inputs={n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p, _ in stack})
(OUT / 'head-body-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('HEAD_BODY_PSD_READY')
