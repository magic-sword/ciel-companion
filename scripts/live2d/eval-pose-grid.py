# -*- coding: utf-8 -*-
"""Unity の描画（.local/render-check/pose_*.png）の両目の中心を測り、見本（assets/ciel/pose-grid-measure.json）との差を表にする。

実行  python -I scripts/live2d/eval-pose-grid.py
差は、描画 − 見本（px、基準画像の座標）。x は右が＋、y は下が＋。虹彩が 2 つ見つからない向きは「--」。
"""
import importlib.util
import json
import os

from PIL import Image
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('mht', os.path.join(HERE, 'measure-head-turn.py'))
mht = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mht)
ROOT = mht.ROOT
XS = ['L30', 'L15', '0', 'R15', 'R30']
YS = ['U30', 'U15', '0', 'D15', 'D30']
ref = json.load(open(os.path.join(ROOT, 'pose-grid-measure.json'), encoding='utf-8'))


def render_blobs(x, y):
    p = os.path.join(ROOT, '..', '..', '.local', 'render-check', 'pose_x%s_y%s.png' % (x, y))
    if x == '0' and y == '0':
        p = os.path.join(ROOT, '..', '..', '.local', 'render-check', 'neutral.png')
    im = Image.open(p).convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    crop = bg.convert('RGB').crop((143, 131, 625, 614)).resize((1536, 1536), Image.LANCZOS)
    return mht.iris_blobs(np.asarray(crop).astype(float))


def centre(b):
    return ((b[0]['x'] + b[1]['x']) / 2, (b[0]['y'] + b[1]['y']) / 2) if len(b) == 2 else None


def main():
    print('両目の中心の差（描画 − 見本）  x/y')
    print('      ' + ' '.join('%11s' % ('x' + x) for x in XS))
    for y in YS:
        row = []
        for x in XS:
            k = 'x%s_y%s' % (x, y)
            a, b = centre(render_blobs(x, y)), centre(ref[k])
            row.append('    --     ' if not a or not b else '%+4.0f/%+4.0f  ' % (a[0] - b[0], a[1] - b[1]))
        print('%-6s' % ('y' + y) + ' '.join(row))


if __name__ == '__main__':
    main()
