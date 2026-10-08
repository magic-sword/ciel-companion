"""Assemble the blink test PSD for Cubism from the layer PNGs.

GIMP 3 batch script (run with python-fu-eval; see the production spec, section 14).
Input:  assets/ciel/master/ciel-upper-body-2x-eyeless.png
        assets/ciel/layers/eyes/{R,L}_*.png   (scripts/live2d/build-eye-layers.ps1)
Output: assets/ciel/psd/ciel-blink-test.{psd,xcf}, report.json
Layer names use the character's own left/right (R = viewer's left). Closed-eye layers are saved hidden,
so the visible composite is the neutral face.
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
stack = [('Face_Base', SRC / 'master/ciel-upper-body-2x-eyeless.png', True)]
for side in ('R', 'L'):
    eyes = SRC / 'layers/eyes'
    stack += [
        (f'{side}_Sclera', eyes / f'{side}_sclera.png', True),
        (f'{side}_Iris', eyes / f'{side}_iris.png', True),
        (f'{side}_Lash', eyes / f'{side}_lash.png', True),
        (f'{side}_Crease', eyes / f'{side}_crease.png', True),
        (f'{side}_Lash_Closed', eyes / f'{side}_lash_closed.png', False),
        (f'{side}_Crease_Closed', eyes / f'{side}_crease_closed.png', False),
    ]
for _, path, _ in stack: assert path.exists(), f'missing {path}; run the source/eye-layer scripts first'

W, H = 2172, 2896
doc = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
for name, path, visible in stack:
    item = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, doc, Gio.File.new_for_path(str(path)))
    item.set_name(name)
    doc.insert_layer(item, None, 0)   # position 0 = top, so the last inserted ends on top
    item.set_visible(visible)
assert [l.get_name() for l in doc.get_layers()] == [n for n, _, _ in reversed(stack)]

checks = {}
for suffix, proc in [('xcf', 'gimp-xcf-save'), ('psd', 'file-psd-export')]:
    target = OUT / f'ciel-blink-test.{suffix}'
    run_proc(proc, image=doc, file=Gio.File.new_for_path(str(target)))
    loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(target)))
    names = [l.get_name() for l in loaded.get_layers()]
    vis = {l.get_name(): l.get_visible() for l in loaded.get_layers()}
    assert names == [n for n, _, _ in reversed(stack)], names
    assert all(vis[n] == v for n, _, v in stack), vis
    checks[suffix] = dict(layers=len(names), names_and_visibility_equal=True)
    loaded.delete()

# flattened neutral composite for an external pixel comparison against the master
flat = doc.duplicate()
merged = flat.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
run_proc('file-png-export', image=flat, file=Gio.File.new_for_path(str(OUT / 'neutral-composite.png')))
flat.delete()
doc.delete()

report = dict(
    generatedBy='scripts/live2d/gimp/build_blink_psd.py',
    canvas=[W, H], order_bottom_to_top=[n for n, _, _ in stack],
    hidden=[n for n, _, v in stack if not v], roundtrip=checks,
    inputs={n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p, _ in stack},
    note='Blink test only: the body, hair and mouth are still part of Face_Base.')
(OUT / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('SOURCE_V2_BLINK_PSD_READY')
