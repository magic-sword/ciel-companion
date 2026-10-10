"""1 枚のレイヤーだけの PSD を作る（既存のモデルへ「全てのレイヤーを新規アートメッシュとして追加」で取り込む用）。

GIMP 3 batch script（python-fu-eval。実行方法は仕様書 12.3）。環境変数で指定する：
  CIEL_LAYER  レイヤー名（assets/ciel/layers/{head,body}/<名前>.png を探す）
出力  assets/ciel/psd/ciel-<名前の小文字>.psd
"""
import os
from pathlib import Path
from gi.repository import Gimp, Gio

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
names = os.environ['CIEL_LAYER'].split(',')     # カンマ区切りで複数（先頭が一番下。PSD の名前は先頭から）
out = ROOT / 'assets/ciel/psd' / f'ciel-{names[0].lower()}.psd'
doc = Gimp.Image.new(2172, 2896, Gimp.ImageBaseType.RGB)
for name in names:
    src = next(p for p in (ROOT / 'assets/ciel/layers' / d / f'{name}.png' for d in ('head', 'body')) if p.exists())
    item = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, doc, Gio.File.new_for_path(str(src)))
    item.set_name(name)
    doc.insert_layer(item, None, 0)
proc = Gimp.get_pdb().lookup_procedure('file-psd-export')
config = proc.create_config()
config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
config.set_property('image', doc)
config.set_property('file', Gio.File.new_for_path(str(out)))
if proc.run(config).index(0) != Gimp.PDBStatusType.SUCCESS: raise RuntimeError('psd export')
doc.delete()
print('SINGLE_PSD_READY', out)
