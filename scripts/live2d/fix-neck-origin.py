# -*- coding: utf-8 -*-
"""首の位置（回転デフォーマ）の軸を、親の呼吸のワープの中（首の付け根）へ移す。

首の位置の軸が呼吸のワープの格子の下の外（正規化座標 y=1.086、キャンバス y≒3186）にあったため、
呼吸・体の角度Y の変形（上ほど動き、下端は動かない）が、頭と首・首輪にほとんど伝わらなかった（逆向きに少し動いていた）。
軸を首の付け根（NEW_Y px）へ移し、子（顔の回転の軸、首の曲面の格子）の位置を、同じ見た目になるように反対へずらす。
回転デフォーマの子の座標は、軸からのキャンバス px（角度 0・倍率 1 のとき）。
あわせて、頭が呼吸に付いてくるようになった分、呼吸の動きを BREATH_GAIN 倍に弱める。

実行  python -I scripts/live2d/fix-neck-origin.py 入力.cmo3 出力.cmo3
"""
import importlib.util
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
from cmo3_tool import _fmt

_spec = importlib.util.spec_from_file_location('motion_keys', os.path.join(HERE, 'motion-keys.py'))
mk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mk)

NEW_Y = 1480.0
# 呼吸の格子の外へはみ出した軸の位置は、ワープの外挿で一次式とずれる。書き出して確かめた正面の頭のずれ（px、下が +）を打ち消す
REST_FIX = 7.47
# 呼吸で首から上が上がりすぎないように、呼吸のキーの形（上を持ち上げる量・肩を広げる量）をこの倍率にする
BREATH_GAIN = 0.6


def main():
    src, dst = sys.argv[1:3]
    doc = t.Cmo3(src)
    # キャンバス px → 呼吸の正規化座標（呼吸の直下の Jacket_Front から）
    a, b = doc.mesh_block('Jacket_Front')
    blk = doc.xml[a:b]
    pts = np.array(re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)<', blk).group(1).split(), float).reshape(-1, 2)
    k = blk.index('<carray_list xs.n="keyforms"')
    nrm = np.array(re.search(r'<float-array xs\.n="positions" count="\d+">([^<]*)<', blk[k:]).group(1).split(), float).reshape(-1, 2)
    fy = np.polyfit(pts[:, 1], nrm[:, 1], 1)

    x = doc.xml
    s, e = mk.block(x, 'CRotationDeformerSource', '首の位置')
    seg = x[s:e]
    old_n = float(re.search(r'<CRotationDeformerForm [^>]*originY="([^"]*)"', seg).group(1))
    old_px = (old_n - fy[1]) / fy[0]
    new_n = np.polyval(fy, NEW_Y)
    delta = old_px - NEW_Y - REST_FIX
    print('軸: 正規化 %.4f（%.0f px）→ %.4f（%.0f px）、子を %.1f px ずらす' % (old_n, old_px, new_n, NEW_Y, delta))
    seg = re.sub(r'(<CRotationDeformerForm [^>]*originY=")[^"]*(")', lambda m: m.group(1) + _fmt(new_n) + m.group(2), seg)
    doc.xml = x[:s] + seg + x[e:]

    # 顔の回転の軸
    x = doc.xml
    s, e = mk.block(x, 'CRotationDeformerSource', '顔の回転')
    seg = re.sub(r'(<CRotationDeformerForm [^>]*originY=")([^"]*)(")',
                 lambda m: m.group(1) + _fmt(float(m.group(2)) + delta) + m.group(3), x[s:e])
    doc.xml = x[:s] + seg + x[e:]

    # 首の曲面の格子（全キー）
    x = doc.xml
    s, e = mk.block(x, 'CWarpDeformerSource', '首の曲面')
    seg = x[s:e]
    out = seg
    for a2, b2, g in sorted(mk.warp_forms(seg), key=lambda z: -z[0]):
        g = g.copy()
        g[:, 1] += delta
        out = out[:a2] + ' '.join(_fmt(q) for q in g.ravel()) + out[b2:]
    doc.xml = x[:s] + out + x[e:]
    # 呼吸のキー（呼吸 1）の形を、呼吸 0 の形からの差の BREATH_GAIN 倍に
    mk.load_params(doc.xml)
    x = doc.xml
    s, e = mk.block(x, 'CWarpDeformerSource', '呼吸')
    seg = x[s:e]
    keys = mk.form_keys(x, seg, 'CWarpDeformerForm')
    forms = mk.warp_forms(seg)
    g0 = [g for (a2, b2, g), k2 in zip(forms, keys) if abs(k2['ParamBreath']) < 1e-6][0]
    out = seg
    for (a2, b2, g), k2 in sorted(zip(forms, keys), key=lambda z: -z[0][0]):
        if abs(k2['ParamBreath']) > 1e-6:
            out = out[:a2] + ' '.join(_fmt(q) for q in (g0 + (g - g0) * BREATH_GAIN).ravel()) + out[b2:]
    doc.xml = x[:s] + out + x[e:]
    doc.save(dst)
    print('FIX_NECK_ORIGIN_DONE')


if __name__ == '__main__':
    main()
