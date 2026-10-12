# -*- coding: utf-8 -*-
"""まばたきの途中（目の開き 0.5）と閉じたとき（0）の、開いた目の層の形を作る（段階 4）。

前提：目の各メッシュに「左目 開閉」「右目 開閉」の 3 キー（0・0.5・1）がある。虹彩・ハイライトは白目でクリッピング。
上まぶた側（白目・上まぶたの肌・上まつげ・二重）の頂点を、閉じ目の線（Eye_*_Closed の画像の弧）へ向けて縮める：
0.5 のキーで RATIO 倍、0 のキーでほぼ線まで（白目は下側も線へ）。下まつげ・下まぶたは動かさない（0 で不透明度 0）。

頂点の画像上の位置は、書き出したモデル（.model3.json）を Cubism Core で計算して得る（.cmo3 の point の並びは
キーフォームの頂点の並びと一致しないことがあるため）。キーの値と並びは、メッシュの KeyformGrid から読む。
各キーフォームは、元の（開いた目の）形 BASE から作り直す（何度実行しても同じ結果）。

実行  python -I scripts/live2d/half-blink-keys.py 入力.cmo3 書き出したモデル.model3.json 元の形の.cmo3 出力.cmo3 [RATIO=0.45]
      元の形の .cmo3：目のキーフォームが 3 つとも開いた目のもの（例：まばたきを作る前のモデル）
"""
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
import cubism_core as cc
from cmo3_tool import _fmt

LAYERS = os.path.join(HERE, '..', '..', 'assets', 'ciel', 'current', 'layers')
UPPER = ['Sclera', 'LidSkin_Upper', 'LashUpper', 'Crease']


def keyform_blocks(doc, name):
    """メッシュの keyforms の中の positions の (開始, 終了)（文書全体の位置）と値。"""
    a, b = doc.mesh_block(name)
    blk = doc.xml[a:b]
    k = blk.index('<carray_list xs.n="keyforms"')
    k2 = blk.index('</carray_list>', k)
    out = []
    for m in re.finditer(r'<float-array xs\.n="positions" count="\d+">([^<]*)<', blk[k:k2]):
        out.append((a + k + m.start(1), a + k + m.end(1), np.array(m.group(1).split(), float).reshape(-1, 2)))
    return out


def key_values(doc, name):
    """keyforms の並びに対応する、パラメーターの値。"""
    a, b = doc.mesh_block(name)
    blk = doc.xml[a:b]
    x = doc.xml
    gref = re.search(r'<KeyformGridSource xs\.n="keyformGridSource" xs\.ref="(#\d+)"', blk).group(1)
    ga = x.index('<KeyformGridSource xs.id="%s"' % gref)
    g = x[ga:x.index('</KeyformGridSource>', ga)]
    bind = re.search(r'<KeyformBindingSource xs\.n="binding" xs\.ref="(#\d+)"', g).group(1)
    ba = x.index('<KeyformBindingSource xs.id="%s"' % bind)
    bb = x[ba:x.index('</KeyformBindingSource>', ba)]
    keys = [float(v) for v in re.findall(r'<f>([^<]*)</f>', bb.split('xs.n="keys"')[1].split('</array_list>')[0])]
    by_form = {}
    for it in re.findall(r'<KeyformOnGrid>(.*?)</KeyformOnGrid>', g, re.S):
        form = re.search(r'<CFormGuid xs\.n="keyformGuid" xs\.ref="(#\d+)"', it).group(1)
        ki = int(re.search(r'<i xs\.n="keyIndex">(\d+)</i>', it).group(1))
        by_form[form] = keys[ki]
    k = blk.index('<carray_list xs.n="keyforms"')
    forms = re.findall(r'<CFormGuid xs\.n="guid" xs\.ref="(#\d+)"', blk[k:blk.index('</carray_list>', k)])
    return [by_form[f] for f in forms]


def closing_curve(side):
    a = np.asarray(Image.open(os.path.join(LAYERS, 'Eye_%s_Closed.png' % side)))[..., 3].astype(float)
    cols = np.nonzero(a.sum(0) > 0)[0]
    ys = np.arange(a.shape[0])
    cy = np.array([np.average(ys, weights=a[:, c]) for c in cols])
    k = max(1, len(cols) // 40)
    cy = np.convolve(np.pad(cy, k, mode='edge'), np.ones(k) / k, mode='same')[k:-k]
    return lambda xs: np.interp(xs, cols.astype(float), cy)


def main():
    src, model3, base_src, dst = sys.argv[1:5]
    ratio = float(sys.argv[5]) if len(sys.argv) > 5 else 0.45
    doc = t.Cmo3(src)
    base = t.Cmo3(base_src)
    core = cc.Model(model3)
    core.reset()
    core.set({'ParamEyeLOpen': 1, 'ParamEyeROpen': 1})
    core.update()
    px = {d['id']: d['pos'] for d in core.drawables()}
    for side in 'LR':
        yc_of = closing_curve(side)
        for part in UPPER:
            name = 'Eye_%s_%s' % (side, part)
            rest = keyform_blocks(base, name)[0][2]           # 開いた目の形（元のモデル）
            vals = key_values(doc, name)
            p = px[name]
            if len(p) != len(rest):
                print('頂点の数が違う:', name, len(p), len(rest))
                continue
            ay = np.polyfit(p[:, 1], rest[:, 1], 1)[0]         # 画像 y → 親の座標 y
            y = p[:, 1]
            ycx = yc_of(p[:, 0])
            blocks = keyform_blocks(doc, name)
            for (s, e, _), v in sorted(zip(blocks, vals), key=lambda z: -z[0][0]):
                if v >= 0.99:
                    ny = y
                elif v >= 0.49:
                    ny = np.where(y < ycx, ycx + (y - ycx) * ratio, y)
                else:
                    ny = np.where(y < ycx, ycx + (y - ycx) * 0.03, y)
                    if part == 'Sclera':
                        ny = ycx + (y - ycx) * 0.03
                f = rest.copy()
                f[:, 1] = rest[:, 1] + (ny - y) * ay
                doc.xml = doc.xml[:s] + ' '.join(_fmt(q) for q in f.ravel()) + doc.xml[e:]
        print('目 %s: 完了' % side)
    doc.save(dst)
    print('HALF_BLINK_KEYS_DONE')


if __name__ == '__main__':
    main()
