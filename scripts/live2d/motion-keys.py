# -*- coding: utf-8 -*-
"""首の傾き・体の傾き・呼吸・髪と耳の揺れの形を、キーフォームに設定する（段階 4）。

前提：Cubism で各デフォーマに次のキーを「キーの 3 点追加」してある（呼吸は 2 点）。
  顔の回転（回転）      ParamAngleZ      -30/0/30 → 角度 -ANGLE_Z/0/+ANGLE_Z
  上半身の曲面Z（ワープ）ParamBodyAngleZ  -10/0/10 → 格子を下端を軸に回す（±BODY_Z 度）
  呼吸（ワープ）         ParamBreath      0/1      → 上半分を少し持ち上げ、肩を広げる
  前髪・アホ毛の曲面     ParamHairFront   -1/0/1   ┐ 毛先ほど大きく横へずらす（付け根は動かさない）
  横髪 L/R・耳の曲面     ParamHairSide    -1/0/1   ┘
キーは、ほかのパラメーター（角度 X×Y）と組み合わさった格子になっている。揺れ・呼吸のキーは、同じ X・Y の
中央のキーの形からの差として作る（X・Y の形は保つ）。
実行  python -I scripts/live2d/motion-keys.py 入力.cmo3 出力.cmo3
"""
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
from cmo3_tool import _fmt

ANGLE_Z = 10.0
BODY_Z = 3.0
SWAY = {'前髪の曲面': ('ParamHairFront', 0.05), 'アホ毛の曲面': ('ParamHairFront', 0.12),
        '右横髪の曲面': ('ParamHairSide', 0.06), '左横髪の曲面': ('ParamHairSide', 0.06),
        '右耳の曲面': ('ParamHairSide', 0.04), '左耳の曲面': ('ParamHairSide', 0.04)}

PARAMS = {}


def load_params(x):
    for m in re.finditer(r'<CParameterSource>(.*?)</CParameterSource>', x, re.S):
        g = re.search(r'<CParameterGuid xs\.n="guid" xs\.(?:ref|id)="(#\d+)"', m.group(1))
        r = re.search(r'<CParameterId xs\.n="id" xs\.ref="(#\d+)"', m.group(1))
        i = re.search(r'idstr="([^"]*)"', m.group(1))
        if not i and r:
            i = re.search(r'<CParameterId [^>]*idstr="([^"]*)"[^>]*xs\.id="%s"|<CParameterId [^>]*xs\.id="%s"[^>]*idstr="([^"]*)"' % (r.group(1), r.group(1)), x)
        if g and i:
            PARAMS[g.group(1)] = i.group(1) or i.group(2)


def block(x, tag, name):
    i = x.index('<s xs.n="localName">%s</s>' % name)
    s = x.rfind('<%s' % tag, 0, i)
    return s, x.index('</%s>' % tag, i)


def form_keys(x, blk, form_tag):
    """keyforms の並びに対応する {パラメーターID: キーの値}。"""
    gref = re.search(r'<KeyformGridSource xs\.n="keyformGridSource" xs\.ref="(#\d+)"', blk).group(1)
    ga = x.index('<KeyformGridSource xs.id="%s"' % gref)
    g = x[ga:x.index('</KeyformGridSource>', ga)]
    binds = {}
    for b in set(re.findall(r'<KeyformBindingSource xs\.n="binding" xs\.ref="(#\d+)"', g)):
        ba = x.index('<KeyformBindingSource xs.id="%s"' % b)
        bb = x[ba:x.index('</KeyformBindingSource>', ba)]
        pid = PARAMS[re.search(r'parameterGuid" xs\.ref="(#\d+)"', bb).group(1)]
        keys = [float(v) for v in re.findall(r'<f>([^<]*)</f>', bb.split('xs.n="keys"')[1].split('</array_list>')[0])]
        binds[b] = (pid, keys)
    by_form = {}
    for it in re.findall(r'<KeyformOnGrid>(.*?)</KeyformOnGrid>', g, re.S):
        form = re.search(r'<CFormGuid xs\.n="keyformGuid" xs\.ref="(#\d+)"', it).group(1)
        d = {}
        for b, k in re.findall(r'binding" xs\.ref="(#\d+)" />\s*<i xs\.n="keyIndex">(\d+)</i>', it):
            pid, keys = binds[b]
            d[pid] = keys[int(k)]
        by_form[form] = d
    order = re.findall(r'<%s[^>]*>.*?<CFormGuid xs\.n="guid" xs\.ref="(#\d+)"' % form_tag, blk, re.S)
    return [by_form[f] for f in order]


def warp_forms(blk):
    return [(m.start(1), m.end(1), np.array(m.group(1).split(), float).reshape(-1, 2))
            for m in re.finditer(r'<float-array xs\.n="positions" count="\d+">([^<]*)<', blk)]


def edit_warp(doc, name, param, fn):
    """fn(基準の格子, パラメーターの値) → 新しい格子。基準は、同じほかのキーで param=0（呼吸は 0）の形。"""
    x = doc.xml
    s, e = block(x, 'CWarpDeformerSource', name)
    blk = x[s:e]
    keys = form_keys(x, blk, 'CWarpDeformerForm')
    forms = warp_forms(blk)
    if len(keys) != len(forms):
        raise SystemExit('数が合わない: %s' % name)
    base_val = 0.0
    out = blk
    for (a, b, g), k in sorted(zip(forms, keys), key=lambda z: -z[0][0]):
        v = k.get(param)
        if v is None:
            raise SystemExit('%s に %s のキーがない' % (name, param))
        if abs(v - base_val) < 1e-6:
            continue
        other = {p: q for p, q in k.items() if p != param}
        same = [g2 for (a2, b2, g2), k2 in zip(forms, keys) if all(abs(k2.get(p, 0) - q) < 1e-6 for p, q in other.items())]
        zero = [g2 for (a2, b2, g2), k2 in zip(forms, keys)
                if abs(k2.get(param) - base_val) < 1e-6 and all(abs(k2.get(p, 0) - q) < 1e-6 for p, q in other.items())]
        # 0 のキーがない（-1 と 1 だけ）ときは、同じほかのキーの形の平均（キーを足した直後はどれも同じ形）
        base = zero[0] if zero else np.mean(same, 0)
        new = fn(base, v)
        out = out[:a] + ' '.join(_fmt(q) for q in new.ravel()) + out[b:]
    doc.xml = x[:s] + out + x[e:]
    print('設定:', name, param, len(forms), 'キー')


def main():
    src, dst = sys.argv[1:3]
    doc = t.Cmo3(src)
    load_params(doc.xml)

    # 顔の回転：角度Z
    x = doc.xml
    s, e = block(x, 'CRotationDeformerSource', '顔の回転')
    blk = x[s:e]
    keys = form_keys(x, blk, 'CRotationDeformerForm')
    i = 0

    def ang(m):
        nonlocal i
        v = keys[i]['ParamAngleZ']
        i += 1
        return '<CRotationDeformerForm angle="%s"' % _fmt(-v / 30.0 * ANGLE_Z)
    blk = re.sub(r'<CRotationDeformerForm angle="[^"]*"', ang, blk)
    doc.xml = x[:s] + blk + x[e:]
    print('設定: 顔の回転 ParamAngleZ')

    # 上半身の曲面Z：下端の中央を軸に回す
    def body_z(g, v):
        th = math.radians(-v / 10.0 * BODY_Z)
        c = np.array([(g[:, 0].min() + g[:, 0].max()) / 2, g[:, 1].max()])
        d = g - c
        return c + np.stack([d[:, 0] * math.cos(th) - d[:, 1] * math.sin(th), d[:, 0] * math.sin(th) + d[:, 1] * math.cos(th)], 1)
    edit_warp(doc, '上半身の曲面Z', 'ParamBodyAngleZ', body_z)

    # 呼吸：上ほど持ち上げ、肩（上の方）を少し広げる
    def breath(g, v):
        y0, y1 = g[:, 1].min(), g[:, 1].max()
        h = y1 - y0
        w = (y1 - g[:, 1]) / h           # 上端 1、下端 0
        cx = (g[:, 0].min() + g[:, 0].max()) / 2
        n = g.copy()
        n[:, 1] -= v * 0.012 * h * w
        n[:, 0] = cx + (g[:, 0] - cx) * (1 + v * 0.006 * w)
        return n
    edit_warp(doc, '呼吸', 'ParamBreath', breath)

    # 髪・耳の揺れ：付け根（上端）は固定、下ほど横へ
    for name, (param, amt) in SWAY.items():
        def sway(g, v, amt=amt):
            y0, y1 = g[:, 1].min(), g[:, 1].max()
            w = ((g[:, 1] - y0) / (y1 - y0)) ** 1.5
            wid = g[:, 0].max() - g[:, 0].min()
            n = g.copy()
            n[:, 0] += v * amt * wid * w
            return n
        edit_warp(doc, name, param, sway)
    doc.save(dst)
    print('MOTION_KEYS_DONE')


if __name__ == '__main__':
    main()
