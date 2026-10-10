# -*- coding: utf-8 -*-
"""顎の裏（Chin_Under。PSD から新規アートメッシュとして取り込んだ直後）を組み込む。

顎の裏は、顔の下（首より上・顔より下）にある面で、上を向いて顔が上へずれたとき、空いた所から見える。
- 動かない体と同じく ROOT の直下のまま、約 50px の格子に分け、角度X×角度Y の 25 キーを付ける。
- 位置（グルーと同じ考え方）：上の縁（GLUE_TOP より上）は顔の顎と同じに動き、下の縁（GLUE_BOTTOM より下）は首に
  残る。間は、なだらかに伸び縮みする。上を向くと顎が上がり、顎の裏が広がって見える。
- 不透明度：角度Y が 0 以下で 0、上向き 15・30 で 1（正面・横向き・下向きで、顔の脇から見えないように）。
- 描画順 DRAW_ORDER（首 10 より上、首輪 90 より下、顔 200 より下）。
顎の裏の線（Chin_Under_Line）と首の線（Neck_Line）にも、同じ動きで使う（線が顎の裏と離れない）。
実行  python -I scripts/live2d/chin-under-keys.py 入力.cmo3 出力.cmo3 [メッシュ名 ...]   完了表示 CHIN_UNDER_KEYS_ADDED（既定は Chin_Under）
"""
import importlib.util
import math
import os
import re
import sys
import uuid

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
import mesh_ops as m
from cmo3_tool import _fmt

spec = importlib.util.spec_from_file_location('h3d', os.path.join(HERE, 'head3d-keys.py'))
h3d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h3d)

LAYERS = os.path.join(HERE, '..', '..', 'assets', 'ciel', 'layers', 'head')
CELL = 50.0
MARGIN = 8
GLUE_TOP = 1340.0    # これより上の点は、顔の顎と同じに動く（顎の輪郭の高さ）
GLUE_BOTTOM = 1530.0 # これより下の点は、首と同じ（動かない）
OPACITY_Y = {-30.0: 0.0, -15.0: 0.0, 0.0: 0.0, 15.0: 1.0, 30.0: 1.0}
DRAW_ORDER = {'Chin_Under': 85, 'Chin_Under_Line': 86, 'Neck_Line': 86}
KEYS = h3d.KEYS


def moved(points, yaw_deg, pitch_deg):
    """上の縁は顔の顎（head3d-keys.py の顔の表面と同じ動き）に、下の縁は首（動かない）に付けて、間を伸び縮みさせる。"""
    face = h3d.rotated(points, yaw_deg, pitch_deg)
    out = []
    for (x, y), (fx, fy) in zip(points, face):
        w = 1.0 - h3d.smoothstep((y - GLUE_TOP) / (GLUE_BOTTOM - GLUE_TOP))   # 上の縁で 1（顔）、下の縁で 0（首）
        out.append((x + w * (fx - x), y + w * (fy - y)))
    return out


def param_ref(d, pid):
    return re.search(r'<CParameterGuid uuid="[^"]*" note="%s" xs\.id="(#\d+)"' % pid, d.xml).group(1)


def add_keys(d, MESH):
    a = np.asarray(Image.open(os.path.join(LAYERS, MESH + '.png')).convert('RGBA'))[..., 3]
    ys, xs = np.nonzero(a > 4)
    bb = (xs.min() - MARGIN, ys.min() - MARGIN, xs.max() + 1 + MARGIN, ys.max() + 1 + MARGIN)
    m.remesh_quad(d, MESH, bb, max(2, int(round((bb[2] - bb[0]) / CELL))), max(2, int(round((bb[3] - bb[1]) / CELL))))

    a0, b0 = d.mesh_block(MESH)
    blk = d.xml[a0:b0]
    rv = [float(v) for v in re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)</float-array>', blk).group(1).split()]
    rest = list(zip(rv[0::2], rv[1::2]))
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
            f = re.sub(r'<f xs\.n="opacity">[^<]*</f>', '<f xs.n="opacity">%s</f>' % _fmt(OPACITY_Y[ky]), f)
            f = re.sub(r'<i xs\.n="drawOrder">-?\d+</i>', '<i xs.n="drawOrder">%d</i>' % DRAW_ORDER[MESH], f)
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
    print(MESH, 'bbox', bb, 'vertices', len(rest))


def main(src, dst, meshes):
    d = t.Cmo3(src)
    for mesh in meshes or ['Chin_Under']:
        add_keys(d, mesh)
    d.save(dst)
    print('CHIN_UNDER_KEYS_ADDED', dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
