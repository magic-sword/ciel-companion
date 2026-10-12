# -*- coding: utf-8 -*-
"""頷きのための上下の動きを強める（角度Y）と、体の前後の傾き（体の角度Y）の形を作る。

公式サンプル（ひより）の頷きのモーションは、角度Y を -20〜-30 へ素早く下げ、体の角度Y を少し遅れて ±5〜10 動かす。
ひよりでは体の角度Y -10 で上半身ごと頭が下がる（約 35 px）。シエルにはその体の動きが無かったので作る。

1. 頭の部位のワープ（head-xy-keys.py の PARTS）の、角度Y ±30 のキーの格子：
   - 同じほかのキーで角度Y 0 の格子からの縦の動きを、下向きは DOWN_GAIN 倍、上向きは UP_GAIN 倍にする
   - さらに、頭全体を下向き HEAD_DROP px 下げる（上向きは HEAD_LIFT px 上げる）
2. 上半身の曲面Y（体の角度Y -10/0/10）：上ほど下げて（-10、前へ倒れる）少し広げる。+10 は上ほど上げて少し狭める。

前提：上半身の曲面Y に体の角度Y の「キーの3点追加」をしてある。頭の部位のワープは角度X・Y のキーを持つ。
何度も実行しないこと（1 は今の形からの掛け算と足し算）。
実行  python -I scripts/live2d/nod-keys.py 入力.cmo3 出力.cmo3
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


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mk = _load('motion_keys', 'motion-keys.py')
hx = _load('head_xy', 'head-xy-keys.py')
sk = _load('sway_keys', 'sway-keys.py')

DOWN_GAIN = 1.6
UP_GAIN = 1.15
HEAD_DROP = 22.0      # px（下向き 30 で頭全体を下げる）
HEAD_LIFT = 6.0       # px（上向き 30 で頭全体を上げる）
BODY_FWD_DROP = 0.016  # 体の角度Y -10：上端を格子の高さのこの割合だけ下げる
BODY_FWD_WIDEN = 0.012  # 体の角度Y -10：上端の横幅を広げる割合（手前に来る）
BODY_BACK_LIFT = 0.010  # 体の角度Y +10：上端を上げる割合
BODY_BACK_NARROW = 0.006


def local_per_px(doc):
    """頭の部位のワープの親（顔の回転）の局所座標の 1 px あたりの量。顔の曲面と、その子の Face_Shadow_Hair（正面のまま）から。"""
    rest = np.array(doc.warp_keyform_positions('顔の曲面')[0])
    L0, L1 = rest.min(0), rest.max(0)
    a, b = doc.mesh_block('Face_Shadow_Hair')
    blk = doc.xml[a:b]
    pts = np.array(re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)<', blk).group(1).split(), float).reshape(-1, 2)
    k = blk.index('<carray_list xs.n="keyforms"')
    nrm = np.array(re.search(r'<float-array xs\.n="positions" count="\d+">([^<]*)<', blk[k:]).group(1).split(), float).reshape(-1, 2)
    px_per_norm = np.array([np.polyfit(nrm[:, i], pts[:, i], 1)[0] for i in range(2)])
    return (L1 - L0) / px_per_norm


def head(doc):
    lpp = local_per_px(doc)
    print('局所座標/px = %.4f, %.4f' % tuple(lpp))
    for name in hx.PARTS:
        x = doc.xml
        try:
            s, e = mk.block(x, 'CWarpDeformerSource', name)
        except ValueError:
            print('なし:', name)
            continue
        blk = x[s:e]
        keys = mk.form_keys(x, blk, 'CWarpDeformerForm')
        forms = mk.warp_forms(blk)
        out = blk
        n = 0
        for (a, b, g), k in sorted(zip(forms, keys), key=lambda z: -z[0][0]):
            v = k.get('ParamAngleY', 0.0)
            if abs(abs(v) - 30) > 1e-6:
                continue
            other = {p: q for p, q in k.items() if p != 'ParamAngleY'}
            zero = [g2 for (a2, b2, g2), k2 in zip(forms, keys)
                    if abs(k2.get('ParamAngleY', 0.0)) < 1e-6 and all(abs(k2.get(p, 0) - q) < 1e-6 for p, q in other.items())]
            if not zero:
                raise SystemExit('%s に角度Y 0 のキーがない' % name)
            g0 = zero[0]
            new = g.copy()
            if v < 0:   # 下向き（画面の下＝y 増加）
                new[:, 1] = g0[:, 1] + (g[:, 1] - g0[:, 1]) * DOWN_GAIN + HEAD_DROP * lpp[1]
            else:
                new[:, 1] = g0[:, 1] + (g[:, 1] - g0[:, 1]) * UP_GAIN - HEAD_LIFT * lpp[1]
            out = out[:a] + ' '.join(_fmt(q) for q in new.ravel()) + out[b:]
            n += 1
        doc.xml = x[:s] + out + x[e:]
        print('頭: %s %d キー' % (name, n))


def back_hair(doc):
    """後ろ髪の曲面の角度Y ±30 のキーにも、頭全体の上下を足す（顎より上は頭と同じ、y 2300 px より下は動かない。back-hair-keys.py と同じ重み）。"""
    fx, fy = sk.px_map(doc, '後ろ髪の曲面', 'Hair_Back')

    def fn(g, v):
        y = (g[:, 1] - fy[1]) / fy[0]
        u = np.clip((y - 1395.0) / (2300.0 - 1395.0), 0, 1)
        w = 1 - u * u * (3 - 2 * u)
        n = g.copy()
        n[:, 1] += (HEAD_DROP if v < 0 else -HEAD_LIFT) * w * fy[0]
        return n
    x = doc.xml
    s, e = mk.block(x, 'CWarpDeformerSource', '後ろ髪の曲面')
    blk = x[s:e]
    keys = mk.form_keys(x, blk, 'CWarpDeformerForm')
    out = blk
    for (a, b, g), k in sorted(zip(mk.warp_forms(blk), keys), key=lambda z: -z[0][0]):
        v = k.get('ParamAngleY', 0.0)
        if abs(abs(v) - 30) < 1e-6:
            out = out[:a] + ' '.join(_fmt(q) for q in fn(g, v).ravel()) + out[b:]
    doc.xml = x[:s] + out + x[e:]
    print('後ろ髪: 頭の上下を足した')


def body(doc):
    def fn(g, v):
        y0, y1 = g[:, 1].min(), g[:, 1].max()
        h = y1 - y0
        w = (y1 - g[:, 1]) / h          # 上端 1、下端 0
        cx = (g[:, 0].min() + g[:, 0].max()) / 2
        n = g.copy()
        if v < 0:
            n[:, 1] += BODY_FWD_DROP * h * w * (-v / 10)
            n[:, 0] = cx + (g[:, 0] - cx) * (1 + BODY_FWD_WIDEN * w * (-v / 10))
        else:
            n[:, 1] -= BODY_BACK_LIFT * h * w * (v / 10)
            n[:, 0] = cx + (g[:, 0] - cx) * (1 - BODY_BACK_NARROW * w * (v / 10))
        return n
    mk.edit_warp(doc, '上半身の曲面Y', 'ParamBodyAngleY', fn)


def main():
    src, dst = sys.argv[1:3]
    doc = t.Cmo3(src)
    mk.load_params(doc.xml)
    hx.load_params(doc.xml)
    head(doc)
    back_hair(doc)
    body(doc)
    doc.save(dst)
    print('NOD_KEYS_DONE')


if __name__ == '__main__':
    main()
