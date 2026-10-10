# -*- coding: utf-8 -*-
"""目のメッシュ（20 枚）を、新しい目の画像の範囲を覆う格子に作り直す。

v5 の目は、古い目より範囲が広い（下まつ毛など）。古いメッシュのままだと、はみ出した所が切れる。
各メッシュを、古いメッシュの範囲と新しい画像の不透明な範囲を合わせた矩形（余白 MARGIN）の、約 CELL px の格子にする。
まばたきのキー（不透明度）はそのまま。目は Head_Warp の子（正規化座標）のまま。
実行  python -I scripts/live2d/expand-eye-meshes.py 入力.cmo3 出力.cmo3   完了表示 EYE_MESHES_EXPANDED
"""
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
import mesh_ops as m

EYES = os.path.join(HERE, '..', '..', 'assets', 'ciel', 'layers', 'eyes')
CELL = 25.0
MARGIN = 10


def main(src, dst):
    d = t.Cmo3(src)
    for side in ('R', 'L'):
        for part in ('Sclera', 'Iris', 'Lash', 'Crease', 'Sclera_Half', 'Iris_Half', 'Lash_Half', 'Crease_Half', 'Lash_Closed', 'Crease_Closed'):
            name = '%s_%s' % (side, part)
            a = np.asarray(Image.open(os.path.join(EYES, name.lower() + '.png')).convert('RGBA'))[..., 3]
            ys, xs = np.nonzero(a > 4)
            ma, mb = d.mesh_block(name)
            P = np.array([float(v) for v in re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)', d.xml[ma:mb]).group(1).split()]).reshape(-1, 2)
            bb = (min(xs.min(), P[:, 0].min()) - MARGIN, min(ys.min(), P[:, 1].min()) - MARGIN,
                  max(xs.max() + 1, P[:, 0].max()) + MARGIN, max(ys.max() + 1, P[:, 1].max()) + MARGIN)
            nx = max(2, int(round((bb[2] - bb[0]) / CELL)))
            ny = max(2, int(round((bb[3] - bb[1]) / CELL)))
            m.remesh_rect(d, name, bb, nx, ny)
            print('  %-16s bbox %s -> %dx%d' % (name, tuple(int(v) for v in bb), nx, ny))
    d.save(dst)
    print('EYE_MESHES_EXPANDED', dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
