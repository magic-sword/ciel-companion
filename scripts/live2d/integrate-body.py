# -*- coding: utf-8 -*-
"""PSD から新規アートメッシュとして取り込んだ体まわりの層を、仮リグへ組み込む（v19）。

1. 4 頂点のメッシュを、層の PNG の不透明な範囲の格子に作り直す（remesh-from-layers.py と同じ）。
2. 親のワープへ入れる。ワープの正規化座標と画像座標の換算は、参照モデル（同じワープに以前入っていたメッシュを持つ .cmo3）
   のメッシュの point（画像座標）と positions（正規化座標）から、一次式で求める。
3. 描画順を設定する。

実行  python -I scripts/live2d/integrate-body.py 入力.cmo3 参照.cmo3 層のフォルダ 出力.cmo3
"""
import glob
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
import mesh_ops
from cmo3_tool import _fmt

# 名前: (親のワープ, 参照モデルで同じワープに入っていたメッシュ, 描画順)
PLAN = {
    'Hair_Back': ('呼吸', 'Body', 100),        # 後に上半身の曲面Y の直下へ移した（呼吸で波打たないように）
    'Jacket_Back': ('呼吸', 'Body', 105),
    'Body': ('呼吸', 'Body', 110),
    'Choker_Back': ('首の曲面', 'Neck', 120),
    'Neck': ('首の曲面', 'Neck', 140),
    'Neck_Shadow_Chin': ('首の曲面', 'Neck', 150),
    'Jacket_Front': ('呼吸', 'Body', 170),
    'Choker_Front': ('首の曲面', 'Neck', 190),
}


def mesh_point_and_rest(doc, name):
    a, b = doc.mesh_block(name)
    blk = doc.xml[a:b]
    pt = np.array(re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)<', blk).group(1).split(), float).reshape(-1, 2)
    k = blk.index('<carray_list xs.n="keyforms"')
    pos = np.array(re.search(r'<float-array xs\.n="positions" count="\d+">([^<]*)<', blk[k:]).group(1).split(), float).reshape(-1, 2)
    return pt, pos


def main():
    src, ref_p, layer_dir, dst = sys.argv[1:5]
    doc = t.Cmo3(src)
    ref = t.Cmo3(ref_p)
    # 1. メッシュを作り直す
    for name in PLAN:
        p = os.path.join(layer_dir, name + '.png')
        al = np.asarray(Image.open(p).convert('RGBA'))[..., 3] > 4
        ys, xs = np.nonzero(al)
        H, W = al.shape
        bbox = (max(0, xs.min() - 6), max(0, ys.min() - 6), min(W, xs.max() + 7), min(H, ys.max() + 7))
        nx = int(min(14, max(1, round((bbox[2] - bbox[0]) / 60))))
        ny = int(min(14, max(1, round((bbox[3] - bbox[1]) / 60))))
        mesh_ops.remesh_quad(doc, name, bbox, nx, ny)
    # 2. 親のワープへ
    for name, (warp, ref_mesh, order) in PLAN.items():
        rp, rn = mesh_point_and_rest(ref, ref_mesh)
        fx = np.polyfit(rp[:, 0], rn[:, 0], 1)
        fy = np.polyfit(rp[:, 1], rn[:, 1], 1)
        w = doc.warp_info(warp)
        a, b = doc.mesh_block(name)
        blk = doc.xml[a:b]
        blk = re.sub(r'<CDeformerGuid xs\.n="targetDeformerGuid" uuid="[^"]*" note="ROOT" />',
                     '<CDeformerGuid xs.n="targetDeformerGuid" xs.ref="%s" />' % w['guid'], blk)
        blk = re.sub(r'(<CDeformerGuid xs\.n="targetDeformerGuid" xs\.ref=")#\d+(")', lambda m: m.group(1) + w['guid'] + m.group(2), blk)
        pt = np.array(re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)<', blk).group(1).split(), float).reshape(-1, 2)
        nrm = np.stack([np.polyval(fx, pt[:, 0]), np.polyval(fy, pt[:, 1])], 1)
        text = ' '.join(_fmt(v) for v in nrm.ravel())
        k = blk.index('<carray_list xs.n="keyforms"')
        k2 = blk.index('</carray_list>', k)
        kf = re.sub(r'(<float-array xs\.n="positions" count="\d+">)[^<]*(<)', lambda m: m.group(1) + text + m.group(2), blk[k:k2])
        kf = re.sub(r'(<CoordType xs\.n="coordType" xs\.ref=")#\d+(")', lambda m: m.group(1) + w['coord'] + m.group(2), kf)
        kf = re.sub(r'<CoordType xs\.n="coordType">\s*<s xs\.n="coordName">Canvas</s>\s*</CoordType>',
                    '<CoordType xs.n="coordType" xs.ref="%s" />' % w['coord'], kf)
        blk = blk[:k] + kf + blk[k2:]
        doc.xml = doc.xml[:a] + blk + doc.xml[b:]
        doc.set_draw_order(name, order)
        print('%-18s -> %s  order %d' % (name, warp, order))
    doc.save(dst)
    print('INTEGRATE_BODY_DONE')


if __name__ == '__main__':
    main()
