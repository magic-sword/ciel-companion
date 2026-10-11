# -*- coding: utf-8 -*-
"""PSD から取り込んだ直後の 4 頂点の四角形メッシュを、層の PNG の不透明な範囲に切り詰め、格子に分ける。

取り込んだ直後のメッシュは、キャンバス全体（層の PNG と同じ大きさ）を覆う四角形で、デフォーマの範囲も変形の細かさも
正しく決まらない。層の PNG（キャンバスと同じ大きさ）の不透明な範囲を求め、mesh_ops.remesh_quad で CELL px ほどのマス目にする。

実行  python -I scripts/live2d/remesh-from-layers.py 入力.cmo3 出力.cmo3 層のフォルダ [CELL=60] [最大分割=14]
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
import mesh_ops


def main():
    src, dst, layer_dir = sys.argv[1:4]
    cell = float(sys.argv[4]) if len(sys.argv) > 4 else 60
    cap = int(sys.argv[5]) if len(sys.argv) > 5 else 14
    doc = t.Cmo3(src)
    done = []
    for p in sorted(glob.glob(os.path.join(layer_dir, '*.png'))):
        name = os.path.splitext(os.path.basename(p))[0]
        try:
            a, b = doc.mesh_block(name)
        except KeyError:
            continue
        al = np.asarray(Image.open(p).convert('RGBA'))[..., 3] > 4
        ys, xs = np.nonzero(al)
        if len(xs) == 0:
            continue
        pad = 6
        H, W = al.shape
        bbox = (max(0, xs.min() - pad), max(0, ys.min() - pad), min(W, xs.max() + 1 + pad), min(H, ys.max() + 1 + pad))
        nx = int(min(cap, max(1, round((bbox[2] - bbox[0]) / cell))))
        ny = int(min(cap, max(1, round((bbox[3] - bbox[1]) / cell))))
        mesh_ops.remesh_quad(doc, name, bbox, nx, ny)
        done.append((name, bbox, nx, ny))
    doc.save(dst)
    for d in done:
        print('%-24s bbox=%s grid=%dx%d' % d)
    print('REMESH_FROM_LAYERS_DONE', len(done))


if __name__ == '__main__':
    main()
