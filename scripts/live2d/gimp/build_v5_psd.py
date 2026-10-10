"""v5 のパーツ（髪・顔・体を作り直したもの）を、Cubism に取り込む PSD にまとめる。

GIMP 3 batch script（python-fu-eval。実行方法は仕様書 12.3）。
入力  assets/ciel/layers/{head,body}/*.png（v5 のパーツ。scripts/live2d/install-v5-parts.ps1 が置く）
出力  assets/ciel/psd/ciel-v5.{psd,xcf}、v5-report.json
Cubism では、古いメッシュを削除してから、「全てのレイヤーを新規アートメッシュとして追加」で取り込む。
目・口・犬耳は、既存のメッシュをそのまま使う（この PSD には入れない）。
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

# bottom -> top（docs/ciel-codex-brief-v5-hair-parts-ja.md の最終の重なり順。目・口・犬耳は既存）
names = [('head', 'Hair_Back'), ('body', 'Body_Base'), ('body', 'Outer_L'), ('body', 'Outer_R'), ('body', 'Body_Fur'),
         ('body', 'Waist_Belt'), ('body', 'Chest_Gem'), ('body', 'Neck_Gear'), ('head', 'Face_Skin'),
         ('head', 'Face_Blush'), ('head', 'Face_Nose'), ('head', 'Hair_Crown'), ('head', 'Hair_Side_L'),
         ('head', 'Hair_Side_R'), ('head', 'Hair_Front'), ('head', 'Brow_L'), ('head', 'Brow_R'), ('head', 'Hair_Ahoge')]
stack = [(n, SRC / 'layers' / d / f'{n}.png') for d, n in names]
for _, path in stack: assert path.exists(), f'missing {path}; run install-v5-parts.ps1 first'

W, H = 2172, 2896
doc = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
for name, path in stack:
    item = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, doc, Gio.File.new_for_path(str(path)))
    item.set_name(name)
    doc.insert_layer(item, None, 0)
assert [l.get_name() for l in doc.get_layers()] == [n for n, _ in reversed(stack)]

checks = {}
for suffix, proc in [('xcf', 'gimp-xcf-save'), ('psd', 'file-psd-export')]:
    target = OUT / f'ciel-v5.{suffix}'
    run_proc(proc, image=doc, file=Gio.File.new_for_path(str(target)))
    loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(target)))
    got = [l.get_name() for l in loaded.get_layers()]
    assert got == [n for n, _ in reversed(stack)], got
    checks[suffix] = dict(layers=len(got), names_equal=True)
    loaded.delete()
doc.delete()

report = dict(generatedBy='scripts/live2d/gimp/build_v5_psd.py', canvas=[W, H],
              order_bottom_to_top=[n for n, _ in stack], roundtrip=checks,
              inputs={n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in stack})
(OUT / 'v5-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('V5_PSD_READY')
