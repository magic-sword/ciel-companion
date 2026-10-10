"""v5 の目（assets/ciel/layers/eyes、install-v5-parts.ps1 が置く）を、Cubism の目の PSD と同じレイヤー名で 2 つの PSD にする。

GIMP 3 batch script（python-fu-eval。実行方法は仕様書 12.3）。
出力  assets/ciel/psd/ciel-v5-eyes-blink.psd（開き・閉じ：Cubism の「ciel-v2-blink-test.psd」を差し替える）
      assets/ciel/psd/ciel-v5-eyes-half.psd（半目：Cubism の「ciel-v2-half-eyes.psd」を差し替える）
レイヤー名で対応するので、まばたきのキー（不透明度）や Head_Warp への組み込みは、そのまま残る。
"""
import os
from pathlib import Path
from gi.repository import Gimp, Gio

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
EYES = ROOT / 'assets/ciel/layers/eyes'
OUT = ROOT / 'assets/ciel/psd'


def export(stack, target):
    doc = Gimp.Image.new(2172, 2896, Gimp.ImageBaseType.RGB)
    for name, path in stack:
        assert path.exists(), f'missing {path}'
        item = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, doc, Gio.File.new_for_path(str(path)))
        item.set_name(name)
        doc.insert_layer(item, None, 0)
    proc = Gimp.get_pdb().lookup_procedure('file-psd-export')
    config = proc.create_config()
    config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
    config.set_property('image', doc)
    config.set_property('file', Gio.File.new_for_path(str(target)))
    if proc.run(config).index(0) != Gimp.PDBStatusType.SUCCESS:
        raise RuntimeError('psd export ' + str(target))
    doc.delete()


blink, half = [], []
for side in ('R', 'L'):
    for part in ('sclera', 'iris', 'lash', 'crease'):
        blink.append((f'{side}_{part.capitalize()}', EYES / f'{side}_{part}.png'))
        half.append((f'{side}_{part.capitalize()}_Half', EYES / f'{side}_{part}_half.png'))
    for part in ('lash', 'crease'):
        blink.append((f'{side}_{part.capitalize()}_Closed', EYES / f'{side}_{part}_closed.png'))
export(blink, OUT / 'ciel-v5-eyes-blink.psd')
export(half, OUT / 'ciel-v5-eyes-half.psd')
print('V5_EYES_PSD_READY')
