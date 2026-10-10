# -*- coding: utf-8 -*-
"""顎の輪郭線のメッシュ（Face_JawLine。PSD から新規アートメッシュとして取り込んだ直後）を組み込む。

- Head_Warp の子にして、絵の範囲を細かく分ける（顔の肌と同じように曲がる）。
- 角度Y（ParamAngleY）に 5 キーを付け、上を向くほど不透明度を下げる（お手本の上向きでは、顎の線がほぼ消える）。
- 描画順は、顔の肌（200）の直上。
実行  python -I scripts/live2d/add-jaw-line-keys.py 入力.cmo3 出力.cmo3   完了表示 JAW_LINE_KEYS_ADDED
"""
import os
import re
import sys
import uuid

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmo3_tool as t
import mesh_ops as m
from cmo3_tool import _fmt

MESH = 'Face_JawLine'
LAYER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'layers', 'head', MESH + '.png')
KEYS = [-30.0, -15.0, 0.0, 15.0, 30.0]
OPACITY = {-30.0: 1.0, -15.0: 1.0, 0.0: 1.0, 15.0: 0.35, 30.0: 0.0}
DRAW_ORDER = 205
CELL = 35.0
MARGIN = 8


def main(src, dst):
    d = t.Cmo3(src)
    a = np.asarray(Image.open(LAYER).convert('RGBA'))[..., 3]
    ys, xs = np.nonzero(a > 4)
    bb = (xs.min() - MARGIN, ys.min() - MARGIN, xs.max() + 1 + MARGIN, ys.max() + 1 + MARGIN)
    d.move_mesh_into_warp(MESH, 'Head_Warp')
    m.remesh_quad(d, MESH, bb, max(2, int(round((bb[2] - bb[0]) / CELL))), max(2, int(round((bb[3] - bb[1]) / CELL))))

    nl = chr(10)
    a0, b0 = d.mesh_block(MESH)
    blk = d.xml[a0:b0]
    k = blk.index('<carray_list xs.n="keyforms"')
    k2 = blk.index('</carray_list>', k) + len('</carray_list>')
    form = re.search(r'<CArtMeshForm>.*?</CArtMeshForm>', blk[k:k2], flags=re.S).group(0)
    old_form_ref = re.search(r'<CFormGuid xs\.n="guid" xs\.ref="(#\d+)" />', form).group(1)
    nid, nidx = d._next_ids()
    form_ids = [('#%d' % (nid + i), nidx + i) for i in range(len(KEYS))]
    forms = []
    for ki, key in enumerate(KEYS):
        f = re.sub(r'<CFormGuid xs\.n="guid" xs\.ref="#\d+" />', '<CFormGuid xs.n="guid" xs.ref="%s" />' % form_ids[ki][0], form)
        f = re.sub(r'<f xs\.n="opacity">[^<]*</f>', '<f xs.n="opacity">%s</f>' % _fmt(OPACITY[key]), f)
        f = re.sub(r'<i xs\.n="drawOrder">-?\d+</i>', '<i xs.n="drawOrder">%d</i>' % DRAW_ORDER, f)
        forms.append(f)
    kf_new = '<carray_list xs.n="keyforms" count="%d">' % len(KEYS) + nl + (nl + nl).join(forms) + nl + '</carray_list>'

    grid_id, grid_idx = '#%d' % (nid + len(KEYS)), nidx + len(KEYS)
    bind_id, bind_idx = '#%d' % (nid + len(KEYS) + 1), nidx + len(KEYS) + 1
    items = []
    for ki in range(len(KEYS)):
        items.append('<KeyformOnGrid>' + nl + '<KeyformGridAccessKey xs.n="accessKey">' + nl + '<array_list xs.n="_keyOnParameterList" count="1">' + nl
                     + '<KeyOnParameter>' + nl + '<KeyformBindingSource xs.n="binding" xs.ref="%s" />' % bind_id + nl + '<i xs.n="keyIndex">%d</i>' % ki + nl
                     + '</KeyOnParameter>' + nl + '</array_list>' + nl + '</KeyformGridAccessKey>' + nl
                     + '<CFormGuid xs.n="keyformGuid" xs.ref="%s" />' % form_ids[ki][0] + nl + '</KeyformOnGrid>')
    grid_xml = ('<KeyformGridSource xs.id="%s" xs.idx="%d">' % (grid_id, grid_idx) + nl
                + '<array_list xs.n="keyformsOnGrid" count="%d">' % len(KEYS) + nl + (nl + nl).join(items) + nl + '</array_list>' + nl
                + '<array_list xs.n="keyformBindings" count="1">' + nl + '<KeyformBindingSource xs.ref="%s" />' % bind_id + nl + '</array_list>' + nl
                + '</KeyformGridSource>')
    head = blk[:k]
    gm = re.search(r'<KeyformGridSource xs\.n="keyformGridSource"( xs\.ref="#\d+" />|>.*?</KeyformGridSource>)', head, flags=re.S)
    head = head[:gm.start()] + '<KeyformGridSource xs.n="keyformGridSource" xs.ref="%s" />' % grid_id + head[gm.end():]
    d.xml = d.xml[:a0] + head + kf_new + blk[k2:] + d.xml[b0:]

    py = re.search(r'<CParameterGuid uuid="[^"]*" note="ParamAngleY" xs\.id="(#\d+)"', d.xml).group(1)
    anchor = re.search(r'<CFormGuid uuid="[^"]*"[^>]*xs\.id="%s"[^>]*/>' % re.escape(old_form_ref), d.xml)
    defs = nl.join('<CFormGuid uuid="%s" note="Key [  ]" xs.id="%s" xs.idx="%d" />' % (uuid.uuid4(), fid, fidx) for fid, fidx in form_ids)
    bind_xml = ('<KeyformBindingSource xs.id="%s" xs.idx="%d">' % (bind_id, bind_idx) + nl
                + '<KeyformGridSource xs.n="_gridSource" xs.ref="%s" />' % grid_id + nl
                + '<CParameterGuid xs.n="parameterGuid" xs.ref="%s" />' % py + nl
                + '<array_list xs.n="keys" count="%d">' % len(KEYS) + nl + nl.join('<f>%s</f>' % _fmt(kk) for kk in KEYS) + nl + '</array_list>' + nl
                + '<InterpolationType xs.n="interpolationType" v="LINEAR" />' + nl
                + '<ExtendedInterpolationType xs.n="extendedInterpolationType" v="LINEAR" />' + nl
                + '<i xs.n="insertPointCount">1</i>' + nl + '<f xs.n="extendedInterpolationScale">1.0</f>' + nl + '<s xs.n="description" />' + nl
                + '</KeyformBindingSource>')
    d.xml = d.xml[:anchor.end()] + nl + defs + nl + grid_xml + nl + bind_xml + d.xml[anchor.end():]
    d.save(dst)
    print('JAW_LINE_KEYS_ADDED', dst, 'bbox', bb)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
