# -*- coding: utf-8 -*-
"""v5 のパーツ（PSD を「全てのレイヤーを新規アートメッシュとして追加」で取り込んだ直後の .cmo3）を、モデルに組み込む。

- 体のパーツ（動かさない）：4 頂点のメッシュを、絵の範囲に切り詰める。
- 頭のパーツ：Head_Warp の子にして、絵の範囲を約 70px のマス目に分ける（ワープの曲面に沿って曲がるように）。
- 描画順を、docs/ciel-codex-brief-v5-hair-parts-ja.md の最終の重なり順にする（目・口・犬耳は既存のメッシュ）。
入力・出力  1 つ目の引数（取り込み直後の .cmo3）、2 つ目の引数（出力）
実行  python -I scripts/live2d/integrate-v5.py 入力.cmo3 出力.cmo3   完了表示 V5_INTEGRATED
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmo3_tool as t
import mesh_ops as m

LAYERS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'layers')
CELL = 70.0
MARGIN = 8
BODY = ['Hair_Back', 'Body_Base', 'Outer_L', 'Outer_R', 'Body_Fur', 'Waist_Belt', 'Chest_Gem', 'Neck_Gear']
HEAD = ['Face_Skin', 'Face_Blush', 'Face_Nose', 'Hair_Crown', 'Hair_Side_L', 'Hair_Side_R', 'Hair_Front', 'Brow_L', 'Brow_R', 'Hair_Ahoge']
SMALL = ['Face_Nose', 'Brow_L', 'Brow_R', 'Face_Blush']   # 小さいパーツは分割を粗くする
# 描画順（大きいほど手前）。目（500）・口（250）・犬耳は既存
ORDER = {'Hair_Back': 5, 'Body_Base': 10, 'Outer_L': 50, 'Outer_R': 50, 'Body_Fur': 60, 'Waist_Belt': 70, 'Chest_Gem': 80,
         'Neck_Gear': 90, 'Face_Skin': 200, 'Face_Blush': 210, 'Face_Nose': 220, 'Hair_Crown': 600, 'Hair_Side_L': 650,
         'Hair_Side_R': 650, 'Hair_Front': 700, 'Brow_L': 750, 'Brow_R': 750, 'Hair_Ahoge': 760, 'Ear_L': 620, 'Ear_R': 620}
# 犬耳は、頭頂の髪より上、横髪・前髪より下（顔を横に向けたとき、耳が顔や横髪の上に重ならないように）
CELL_FINE = {'Face_Skin': 35.0}   # 顔の肌は、顎の輪郭が向きを変えてもなめらかに曲がるよう、細かく分ける


def alpha_bbox(name, margin=MARGIN):
    for sub in ('head', 'body'):
        p = os.path.join(LAYERS, sub, name + '.png')
        if os.path.exists(p):
            a = np.asarray(Image.open(p).convert('RGBA'))[..., 3]
            ys, xs = np.nonzero(a > 8)
            return (max(0, xs.min() - margin), max(0, ys.min() - margin), min(2171, xs.max() + margin), min(2895, ys.max() + margin))
    raise FileNotFoundError(name)


def main(src, dst):
    d = t.Cmo3(src)
    for n in BODY:
        bb = alpha_bbox(n)
        d.crop_quad_mesh(n, bb, margin=0)
        print('  body %-12s bbox %s' % (n, bb))
    for n in HEAD:
        bb = alpha_bbox(n)
        d.move_mesh_into_warp(n, 'Head_Warp')
        cell = CELL_FINE.get(n, CELL)
        nx = max(2, int(round((bb[2] - bb[0]) / cell)))
        ny = max(2, int(round((bb[3] - bb[1]) / cell)))
        if n in SMALL:
            nx, ny = min(nx, 4), min(ny, 4)
        m.remesh_quad(d, n, (bb[0], bb[1], bb[2] + 1, bb[3] + 1), nx, ny)
        print('  head %-12s bbox %s -> %dx%d' % (n, bb, nx, ny))
    for n, v in ORDER.items():
        d.set_draw_order(n, v)
    d.save(dst)
    print('V5_INTEGRATED', dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
