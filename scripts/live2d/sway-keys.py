# -*- coding: utf-8 -*-
"""物理演算で動かす、後ろ髪の揺れと胸の揺れの形を、キーフォームに設定する。

前提：Cubism で次のキーを「キーの3点追加」してある（±1 の 2 キー。ほかのキーとの組み合わせはそのまま）。
  後ろ髪の曲面（角度X・Y・Z の格子）  ParamHairBack  -1/1 → 顎より下ほど横へずらす（根元は頭に付いたまま）
  胸の曲面（Body を包むワープ）        ParamBustY     -1/1 → 左右の胸のふくらみのまわりだけ上下へ（+ が上）
揺れのキーは、同じほかのキーの形（角度X・Y・Z の形）からの差として作る（back-hair-keys.py の後に実行する）。
キャンバス px と、ワープの親の座標の換算は、ワープの中のメッシュの point（px）と位置から一次式で求める。

実行  python -I scripts/live2d/sway-keys.py 入力.cmo3 出力.cmo3
"""
import importlib.util
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t

_spec = importlib.util.spec_from_file_location('motion_keys', os.path.join(HERE, 'motion-keys.py'))
mk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mk)

CHIN_Y = 1395.0                 # 顎の高さ（キャンバス px。back-hair-keys.py の計算値）
HAIR_SWAY = 60.0                # 後ろ髪の毛先の横の動き（px）
BUST_C = ((910.0, 2060.0), (1310.0, 2060.0))    # 左右のふくらみの中心（px。胸は横 710〜1510、縦 1850〜2200）
BUST_S = (170.0, 120.0)         # 広がり（px、ガウスの σ）
BUST_LIFT = 18.0                # 胸の上下の動き（px）


def px_map(doc, warp, mesh):
    """キャンバス px → ワープの親の座標 の一次式（x と y それぞれ）。"""
    ma, mb = doc.mesh_block(mesh)
    blk = doc.xml[ma:mb]
    pts = np.array(re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)<', blk).group(1).split(), float).reshape(-1, 2)
    k = blk.index('<carray_list xs.n="keyforms"')
    nrm = np.array(re.search(r'<float-array xs\.n="positions" count="\d+">([^<]*)<', blk[k:]).group(1).split(), float).reshape(-1, 2)
    rest = np.array(doc.warp_keyform_positions(warp)[0])
    lo, hi = rest.min(0), rest.max(0)
    q = lo + nrm * (hi - lo)
    return np.polyfit(pts[:, 0], q[:, 0], 1), np.polyfit(pts[:, 1], q[:, 1], 1)


def main():
    src, dst = sys.argv[1:3]
    doc = t.Cmo3(src)
    mk.load_params(doc.xml)

    fx, fy = px_map(doc, '後ろ髪の曲面', 'Hair_Back')

    def hair(g, v):
        y = (g[:, 1] - fy[1]) / fy[0]
        u = np.clip((y - CHIN_Y) / (2894.0 - CHIN_Y), 0, 1)
        n = g.copy()
        n[:, 0] += v * HAIR_SWAY * fx[0] * u ** 1.5
        return n
    mk.edit_warp(doc, '後ろ髪の曲面', 'ParamHairBack', hair)

    bx, by = px_map(doc, '胸の曲面', 'Body')

    def bust(g, v):
        x = (g[:, 0] - bx[1]) / bx[0]
        y = (g[:, 1] - by[1]) / by[0]
        w = sum(np.exp(-0.5 * (((x - cx) / BUST_S[0]) ** 2 + ((y - cy) / BUST_S[1]) ** 2)) for cx, cy in BUST_C)
        w = np.minimum(w, 1.0)
        n = g.copy()
        n[:, 1] -= v * BUST_LIFT * by[0] * w
        return n
    mk.edit_warp(doc, '胸の曲面', 'ParamBustY', bust)
    doc.save(dst)
    print('SWAY_KEYS_DONE')


if __name__ == '__main__':
    main()
