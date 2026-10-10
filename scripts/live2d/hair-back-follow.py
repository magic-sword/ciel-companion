# -*- coding: utf-8 -*-
"""後ろ髪（Hair_Back）を、頭の向き（角度X・角度Y）に合わせて動かす。

後ろ髪は ROOT の直下（画像座標）のメッシュで、頭が回っても動かなかった（上を向くと耳や頭が後ろ髪から離れて見える）。
メッシュを格子に分け、角度X×角度Y の 25 キーフォームを付ける。各キーの頂点の位置は、head3d-keys.py と同じ回転を、
頭の後ろ側（奥、深さ -BACK_Z）の面として計算し、動きの強さを高さで減らす（頭の高さで 1、FOLLOW_Y1 で 0。
毛先は肩・背中の側に残る）。
実行  python -I scripts/live2d/hair-back-follow.py 入力.cmo3 出力.cmo3   完了表示 HAIR_BACK_FOLLOW_ADDED
"""
import importlib.util
import math
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
import mesh_ops as m
from cmo3_tool import _fmt

spec = importlib.util.spec_from_file_location('h3d', os.path.join(HERE, 'head3d-keys.py'))
h3d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h3d)

MESH = 'Hair_Back'
CELL = 70.0
BACK_Z = 120.0                     # 後ろ髪の面の奥行き（頭の中心より奥）
FOLLOW_Y0, FOLLOW_Y1 = 950.0, 1900.0   # この高さの間で、頭に合わせて動く強さを 1 → 0 にする
KEYS = h3d.KEYS


def follow(y):
    return 1.0 - h3d.smoothstep((y - FOLLOW_Y0) / (FOLLOW_Y1 - FOLLOW_Y0))


def moved(points, yaw_deg, pitch_deg):
    p, q = math.radians(yaw_deg), math.radians(pitch_deg)
    out = []
    for x, y in points:
        X, Y, Z = x - h3d.CX, y - h3d.PIVOT_Y, -BACK_Z
        X1 = X * math.cos(p) + Z * math.sin(p)
        Z1 = -X * math.sin(p) + Z * math.cos(p)
        Y1 = Y * math.cos(q) - Z1 * math.sin(q) - h3d.head_lift(pitch_deg)   # 頭と一緒に持ち上げる
        # 回したときの位置と、回さないときの位置（= 元の位置）の差を、高さに応じた強さで足す
        w = follow(y)
        out.append((x + w * (X1 - X), y + w * (Y1 - Y)))
    return out


def param_ref(d, pid):
    return re.search(r'<CParameterGuid uuid="[^"]*" note="%s" xs\.id="(#\d+)"' % pid, d.xml).group(1)


def main(src, dst):
    d = t.Cmo3(src)
    a0, b0 = d.mesh_block(MESH)
    P = [float(v) for v in re.search(r'<float-array xs\.n="point" count="8">([^<]*)</float-array>', d.xml[a0:b0]).group(1).split()]
    bb = (min(P[0::2]), min(P[1::2]), max(P[0::2]), max(P[1::2]))
    m.remesh_quad(d, MESH, bb, max(2, int(round((bb[2] - bb[0]) / CELL))), max(2, int(round((bb[3] - bb[1]) / CELL))))

    a0, b0 = d.mesh_block(MESH)
    blk = d.xml[a0:b0]
    rest_vals = [float(v) for v in re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)</float-array>', blk).group(1).split()]
    rest = list(zip(rest_vals[0::2], rest_vals[1::2]))

    nl = chr(10)
    k = blk.index('<carray_list xs.n="keyforms"')
    k2 = blk.index('</carray_list>', k) + len('</carray_list>')
    form = re.search(r'<CArtMeshForm>.*?</CArtMeshForm>', blk[k:k2], flags=re.S).group(0)
    old_form_ref = re.search(r'<CFormGuid xs\.n="guid" xs\.ref="(#\d+)" />', form).group(1)
    nid, nidx = d._next_ids()
    n = len(KEYS) * len(KEYS)
    form_ids = [('#%d' % (nid + i), nidx + i) for i in range(n)]
    forms = []
    for yi, ky in enumerate(KEYS):
        for xi, kx in enumerate(KEYS):
            yaw = h3d.YAW[kx] + h3d.EXTRA_RATE * h3d.YAW_EXTRA.get(kx, {}).get(abs(ky), 0.0)
            pts = moved(rest, yaw, h3d.PITCH[ky])
            txt = ' '.join(_fmt(v) for q in pts for v in q)
            f = re.sub(r'<CFormGuid xs\.n="guid" xs\.ref="#\d+" />', '<CFormGuid xs.n="guid" xs.ref="%s" />' % form_ids[yi * len(KEYS) + xi][0], form)
            f = re.sub(r'(<float-array xs\.n="positions" count=")\d+(">)[^<]*(</float-array>)', lambda mm: mm.group(1) + str(2 * len(pts)) + mm.group(2) + txt + mm.group(3), f)
            forms.append(f)
    kf_new = '<carray_list xs.n="keyforms" count="%d">' % n + nl + (nl + nl).join(forms) + nl + '</carray_list>'

    grid_id, grid_idx = '#%d' % (nid + n), nidx + n
    bx, bxi = '#%d' % (nid + n + 1), nidx + n + 1
    by, byi = '#%d' % (nid + n + 2), nidx + n + 2
    items = []
    for yi in range(len(KEYS)):
        for xi in range(len(KEYS)):
            items.append('<KeyformOnGrid>' + nl + '<KeyformGridAccessKey xs.n="accessKey">' + nl + '<array_list xs.n="_keyOnParameterList" count="2">' + nl
                         + '<KeyOnParameter>' + nl + '<KeyformBindingSource xs.n="binding" xs.ref="%s" />' % bx + nl + '<i xs.n="keyIndex">%d</i>' % xi + nl + '</KeyOnParameter>' + nl
                         + '<KeyOnParameter>' + nl + '<KeyformBindingSource xs.n="binding" xs.ref="%s" />' % by + nl + '<i xs.n="keyIndex">%d</i>' % yi + nl + '</KeyOnParameter>' + nl
                         + '</array_list>' + nl + '</KeyformGridAccessKey>' + nl
                         + '<CFormGuid xs.n="keyformGuid" xs.ref="%s" />' % form_ids[yi * len(KEYS) + xi][0] + nl + '</KeyformOnGrid>')
    grid_xml = ('<KeyformGridSource xs.id="%s" xs.idx="%d">' % (grid_id, grid_idx) + nl
                + '<array_list xs.n="keyformsOnGrid" count="%d">' % n + nl + (nl + nl).join(items) + nl + '</array_list>' + nl
                + '<array_list xs.n="keyformBindings" count="2">' + nl + '<KeyformBindingSource xs.ref="%s" />' % bx + nl
                + '<KeyformBindingSource xs.ref="%s" />' % by + nl + '</array_list>' + nl + '</KeyformGridSource>')

    def binding(bid, bidx, pref):
        return ('<KeyformBindingSource xs.id="%s" xs.idx="%d">' % (bid, bidx) + nl
                + '<KeyformGridSource xs.n="_gridSource" xs.ref="%s" />' % grid_id + nl
                + '<CParameterGuid xs.n="parameterGuid" xs.ref="%s" />' % pref + nl
                + '<array_list xs.n="keys" count="%d">' % len(KEYS) + nl + nl.join('<f>%s</f>' % _fmt(kk) for kk in KEYS) + nl + '</array_list>' + nl
                + '<InterpolationType xs.n="interpolationType" v="LINEAR" />' + nl
                + '<ExtendedInterpolationType xs.n="extendedInterpolationType" v="LINEAR" />' + nl
                + '<i xs.n="insertPointCount">1</i>' + nl + '<f xs.n="extendedInterpolationScale">1.0</f>' + nl + '<s xs.n="description" />' + nl
                + '</KeyformBindingSource>')

    head = blk[:k]
    gm = re.search(r'<KeyformGridSource xs\.n="keyformGridSource"( xs\.ref="#\d+" />|>.*?</KeyformGridSource>)', head, flags=re.S)
    head = head[:gm.start()] + '<KeyformGridSource xs.n="keyformGridSource" xs.ref="%s" />' % grid_id + head[gm.end():]
    d.xml = d.xml[:a0] + head + kf_new + blk[k2:] + d.xml[b0:]
    anchor = re.search(r'<CFormGuid uuid="[^"]*"[^>]*xs\.id="%s"[^>]*/>' % re.escape(old_form_ref), d.xml)
    defs = nl.join('<CFormGuid uuid="%s" note="Key [  ]" xs.id="%s" xs.idx="%d" />' % (uuid.uuid4(), fid, fidx) for fid, fidx in form_ids)
    d.xml = (d.xml[:anchor.end()] + nl + defs + nl + grid_xml + nl + binding(bx, bxi, param_ref(d, 'ParamAngleX')) + nl
             + binding(by, byi, param_ref(d, 'ParamAngleY')) + d.xml[anchor.end():])
    d.save(dst)
    print('HAIR_BACK_FOLLOW_ADDED', dst, 'vertices', len(rest))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
