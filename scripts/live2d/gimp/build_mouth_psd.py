"""Assemble the three mouth layers into a small PSD for Cubism.

GIMP 3 batch script (run with python-fu-eval; see the production spec, section 12.3).
Input:  assets/ciel/layers/head/{Mouth_Closed,Mouth_Small,Mouth_Large}.png  (scripts/live2d/build-mouth-and-hair-layers.py)
Output: assets/ciel/psd/ciel-mouth.{psd,xcf}, mouth-report.json
Open this PSD on the existing model in Cubism and add all layers as new art meshes: replacing ciel-head-body.psd
only updates the layers that already exist (new layer names are not added except one), so new layers go in by a separate PSD.
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
stack = [(n, SRC / 'layers/head' / f'{n}.png') for n in ('Mouth_Closed', 'Mouth_Small', 'Mouth_Large')]
for _, path in stack: assert path.exists(), f'missing {path}; run build-mouth-and-hair-layers.py first'

W, H = 2172, 2896
doc = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
for name, path in stack:
    item = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, doc, Gio.File.new_for_path(str(path)))
    item.set_name(name)
    doc.insert_layer(item, None, 0)
assert [l.get_name() for l in doc.get_layers()] == [n for n, _ in reversed(stack)]

checks = {}
for suffix, proc in [('xcf', 'gimp-xcf-save'), ('psd', 'file-psd-export')]:
    target = OUT / f'ciel-mouth.{suffix}'
    run_proc(proc, image=doc, file=Gio.File.new_for_path(str(target)))
    loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(target)))
    got = [l.get_name() for l in loaded.get_layers()]
    assert got == [n for n, _ in reversed(stack)], got
    checks[suffix] = dict(layers=len(got), names_equal=True)
    loaded.delete()
doc.delete()

report = dict(generatedBy='scripts/live2d/gimp/build_mouth_psd.py', canvas=[W, H],
              order_bottom_to_top=[n for n, _ in stack], roundtrip=checks,
              inputs={n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in stack})
(OUT / 'mouth-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('MOUTH_PSD_READY')
