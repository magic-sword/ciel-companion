"""顎の輪郭線のレイヤー（Face_JawLine）だけの PSD を作る。既存のモデルへ「全てのレイヤーを新規アートメッシュとして追加」で取り込む。

GIMP 3 batch script（python-fu-eval。実行方法は仕様書 12.3）。
入力  assets/ciel/layers/head/Face_JawLine.png（scripts/live2d/split-jaw-line.py）
出力  assets/ciel/psd/ciel-jawline.psd
"""
import os
from pathlib import Path
from gi.repository import Gimp, Gio

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
src = ROOT / 'assets/ciel/layers/head/Face_JawLine.png'
out = ROOT / 'assets/ciel/psd/ciel-jawline.psd'
doc = Gimp.Image.new(2172, 2896, Gimp.ImageBaseType.RGB)
item = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, doc, Gio.File.new_for_path(str(src)))
item.set_name('Face_JawLine')
doc.insert_layer(item, None, 0)
proc = Gimp.get_pdb().lookup_procedure('file-psd-export')
config = proc.create_config()
config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
config.set_property('image', doc)
config.set_property('file', Gio.File.new_for_path(str(out)))
if proc.run(config).index(0) != Gimp.PDBStatusType.SUCCESS: raise RuntimeError('psd export')
doc.delete()
print('JAWLINE_PSD_READY')
