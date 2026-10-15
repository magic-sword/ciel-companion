"""層の一覧（JSON）から、Cubism に取り込む PSD（と XCF）を作る（計画書 8.3 の段階 3 の受け渡し）。

GIMP 3 batch script（python-fu-eval。実行方法は仕様書 12.3。環境変数 CIEL_PROJECT_ROOT と CIEL_PSD_MANIFEST が要る）。
一覧の形（パスはリポジトリのルートから）：
  {"canvas": [2172, 2896], "out": "assets/ciel/psd/ciel-v9",
   "layers": [{"name": "Hair_Back", "path": "assets/ciel/layers/v9/Hair_Back.png"}, ...]}   ← 下から上の順
各 PNG はキャンバスと同じ大きさの透明画像。レイヤー名は Cubism のアートメッシュ名になる（英数字と _）。
出力  <out>.psd、<out>.xcf、<out>-report.json。出力後に読み直して、レイヤーの名前と順が一致することを確かめる。
"""
import os, json, hashlib, re
from pathlib import Path
from gi.repository import Gimp, Gio

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
manifest = json.loads((ROOT / os.environ['CIEL_PSD_MANIFEST']).read_text(encoding='utf-8-sig'))  # BOM 付きも読む
W, H = manifest['canvas']
out = ROOT / manifest['out']
out.parent.mkdir(parents=True, exist_ok=True)
stack = [(l['name'], ROOT / l['path']) for l in manifest['layers']]
visible = {l['name']: l.get('visible', True) for l in manifest['layers']}   # 差分（閉じ目など）は非表示で書く
for name, path in stack:
    assert re.fullmatch(r'[A-Za-z0-9_]+', name), f'bad layer name {name}'
    assert path.exists(), f'missing {path}'
assert len({n for n, _ in stack}) == len(stack), 'duplicate layer names'


def run_proc(name, **values):
    proc = Gimp.get_pdb().lookup_procedure(name)
    config = proc.create_config()
    config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
    for key, value in values.items(): config.set_property(key.replace('_', '-'), value)
    result = proc.run(config)
    if result.index(0) != Gimp.PDBStatusType.SUCCESS: raise RuntimeError(name)


doc = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
for name, path in stack:
    item = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, doc, Gio.File.new_for_path(str(path)))
    entry = next(l for l in manifest['layers'] if l['name'] == name)
    assert (item.get_width(), item.get_height()) == tuple(entry.get('canvas', [W, H])), f'{name}: size {item.get_width()}x{item.get_height()}'
    item.set_name(name)
    item.set_visible(visible[name])
    doc.insert_layer(item, None, 0)
    item.set_offsets(*entry.get('offset', [0, 0]))
expect = [n for n, _ in reversed(stack)]
assert [l.get_name() for l in doc.get_layers()] == expect

checks = {}
for suffix, proc in [('xcf', 'gimp-xcf-save'), ('psd', 'file-psd-export')]:
    target = out.with_suffix('.' + suffix)
    run_proc(proc, image=doc, file=Gio.File.new_for_path(str(target)))
    loaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(target)))
    got = [l.get_name() for l in loaded.get_layers()]
    assert got == expect, got
    for layer in loaded.get_layers():
        entry = next(l for l in manifest['layers'] if l['name'] == layer.get_name())
        assert tuple(layer.get_offsets())[-2:] == tuple(entry.get('offset', [0, 0])), layer.get_name()
    checks[suffix] = dict(layers=len(got), names_equal=True, offsets_equal=True)
    loaded.delete()
doc.delete()

report = dict(generatedBy='scripts/live2d/gimp/build_layers_psd.py', manifest=os.environ['CIEL_PSD_MANIFEST'],
              canvas=[W, H], order_bottom_to_top=[n for n, _ in stack], roundtrip=checks,
              inputs={n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in stack})
Path(str(out) + '-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print('LAYERS_PSD_READY', out)
