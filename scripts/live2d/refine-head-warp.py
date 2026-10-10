# -*- coding: utf-8 -*-
"""Head_Warp の格子を細かくする（16×16 → GRID）。子のメッシュは画像上の同じ位置のまま。

格子のマス目が粗いと、顎のように奥行きが急に変わる所で、マス目ごとに折れて、上を向いたとき顎の下端が波打つ。
格子を作り直すとキーフォームの形は一様な格子に戻るので、続けて head3d-keys.py で 25 キーを作り直す。
実行  python -I scripts/live2d/refine-head-warp.py 入力.cmo3 出力.cmo3   完了表示 HEAD_WARP_REFINED
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmo3_tool as t
import mesh_ops as m

GRID = (24, 24)


def main(src, dst):
    d = t.Cmo3(src)
    w = d.warp_info('Head_Warp')
    m.retarget_warp(d, 'Head_Warp', w['x0'], w['x1'], w['y0'], w['y1'], GRID[0], GRID[1])
    d.save(dst)
    print('HEAD_WARP_REFINED', dst, (w['x0'], w['x1'], w['y0'], w['y1']), GRID)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
