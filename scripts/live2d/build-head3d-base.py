"""立体回転の頭のための土台（.cmo3）を作る。

入力  1つ目の引数：Head_Warp（角度Xのキー付き）を持つ .cmo3
出力  2つ目の引数：
      - 頭のレイヤー（Face_Skin・Hair_Front・Ear_L・Ear_R・Hair_Under_Ear）を、絵の範囲に切り詰めて細かく分割する
      - 目・口のメッシュも細かく分割する（ワープデフォーマの曲面に沿って曲がるように）
      - Head_Warp の格子を、頭の範囲に絞った、細かい格子（10×10）に作り直す（子のメッシュは同じ位置のまま）
      キーフォームの形は、すべて基準の一様な格子になる（形は、あとで head3d-keys.py が作る）。
実行  python -I scripts/live2d/build-head3d-base.py 入力.cmo3 出力.cmo3
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmo3_tool as t
import mesh_ops as m

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'layers')
BIG = ['Face_Skin', 'Hair_Front', 'Ear_L', 'Ear_R', 'Hair_Under_Ear']
CELL = 70.0          # 分割するマスの大きさ（画素）
MARGIN = 8
RANGE = (420.0, 1780.0, -20.0, 1560.0)   # Head_Warp の格子の範囲（画像座標）。頭と耳をおおう
GRID = (10, 10)


def alpha_bbox(name):
    path = glob.glob(os.path.join(ROOT, '*', name + '.png'))[0]
    a = np.asarray(Image.open(path).convert('RGBA'))[..., 3]
    ys, xs = np.nonzero(a > 8)
    return xs.min() - MARGIN, ys.min() - MARGIN, xs.max() + 1 + MARGIN, ys.max() + 1 + MARGIN


def counts(bbox):
    return max(2, int(round((bbox[2] - bbox[0]) / CELL))), max(2, int(round((bbox[3] - bbox[1]) / CELL)))


def main(src, dst):
    d = t.Cmo3(src)
    names = m.meshes_in_warp(d, 'Head_Warp')
    print('meshes in Head_Warp:', len(names))
    for n in names:
        a, b = d.mesh_block(n)
        import re
        pt = re.search(r'<float-array xs\.n="point" count="8">([^<]*)</float-array>', d.xml[a:b])
        if not pt:
            print('  skip (not 4 vertices):', n)
            continue
        P = [float(v) for v in pt.group(1).split()]
        if n in BIG:
            bbox = alpha_bbox(n)
        else:
            bbox = (min(P[0::2]), min(P[1::2]), max(P[0::2]), max(P[1::2]))
        nx, ny = counts(bbox)
        if n not in BIG:
            nx, ny = max(2, min(nx, 6)), max(2, min(ny, 6))
        m.remesh_quad(d, n, bbox, nx, ny)
        print('  %-18s bbox %s -> %dx%d' % (n, tuple(int(v) for v in bbox), nx, ny))
    m.retarget_warp(d, 'Head_Warp', RANGE[0], RANGE[1], RANGE[2], RANGE[3], GRID[0], GRID[1])
    d.save(dst)
    print('HEAD3D_BASE_READY', dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
