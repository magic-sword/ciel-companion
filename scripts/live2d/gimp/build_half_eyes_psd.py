"""Assemble the half-open eye layers into a small PSD for Cubism.

GIMP 3 batch script (run with python-fu-eval; see the production spec, section 14).
Input:  assets/ciel/layers/eyes/{R,L}_{sclera,iris,lash,crease}_half.png
        (scripts/live2d/build-eye-layers.ps1, then scripts/live2d/trim-half-eye-layers.py)
Output: assets/ciel/psd/ciel-half-eyes.{psd,xcf}, half-eyes-report.json
This PSD is NOT a replacement for ciel-blink-test.psd: open it on the same model in Cubism and add all layers
as new art meshes (replacing the 13-layer PSD shifts the layer ids and mixes up the textures; see spec section 16).
Layer names use the character's own left/right (R = viewer's left). All layers are saved visible.
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

# bottom -> top (same order as the open eyes: sclera < iris < lash < crease)
eyes = SRC / 'layers/eyes'
stack = []
for side in ('R', 'L'):
    for part in ('sclera', 'iris', 'lash', 'crease'):
        stack.append((f'{side}_{part.capitalize()}_Half', eyes / f'{side}_{part}_half.png', True))
for _, path, _ in stack: assert path.exists(), f'missing {path}; run scripts/live2d/build-eye-layers.ps1 first'

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
    target = OUT / f'ciel-half-eyes.{suffix}'
    run_proc(proc, image=doc, file=Gio.File.new_for_path(str(target)))
    loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(target)))
    names = [l.get_name() for l in loaded.get_layers()]
    vis = {l.get_name(): l.get_visible() for l in loaded.get_layers()}
    assert names == [n for n, _, _ in reversed(stack)], names
    assert all(vis[n] == v for n, _, v in stack), vis
    checks[suffix] = dict(layers=len(names), names_and_visibility_equal=True)
    loaded.delete()
doc.delete()

report = dict(
    generatedBy='scripts/live2d/gimp/build_half_eyes_psd.py',
    canvas=[W, H], order_bottom_to_top=[n for n, _, _ in stack], roundtrip=checks,
    inputs={n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p, _ in stack})
(OUT / 'half-eyes-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('SOURCE_V2_HALF_EYES_PSD_READY')
