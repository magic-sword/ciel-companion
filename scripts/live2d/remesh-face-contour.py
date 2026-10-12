# -*- coding: utf-8 -*-
"""顔の肌（Face_Skin）のメッシュを、輪郭に沿った同心の輪の形に作り直す（頬の輪郭をなめらかに曲げるため）。

四角い格子（61 px 間隔）のメッシュでは、輪郭が格子の線のところでしか曲がらず、横を向いたときの頬が折れ線になる。
顔の中心から放射状に N 本の線を引き、画像の不透明な範囲の端までの距離 R(θ) を測って、次の輪に頂点を置く。
  R+6（輪郭の線の外）、R-10・R-28（輪郭の線の内側）、R-55、0.75R、0.5R、0.25R、中心
隣り合う輪の間を三角形でつなぐ。全キーフォームの形は正面の形になる（横向きの形は cheek-keys.py で付ける）。

実行  python -I scripts/live2d/remesh-face-contour.py 入力.cmo3 出力.cmo3 [N=100]
"""
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
import mesh_ops

LAYERS = os.path.join(HERE, '..', '..', 'assets', 'ciel', 'current', 'layers')
CENTER = (1112.0, 1000.0)
RINGS = [('d', 6), ('d', -10), ('d', -28), ('d', -55), ('f', 0.75), ('f', 0.5), ('f', 0.25)]


def edge_radius(alpha, c, th):
    """中心 c から角度 th の向きに進み、不透明（> 8）の範囲の最後の位置までの距離。"""
    h, w = alpha.shape
    dx, dy = math.cos(th), math.sin(th)
    r_last = 0.0
    r = 0.0
    while True:
        x, y = c[0] + dx * r, c[1] + dy * r
        if not (0 <= x < w - 1 and 0 <= y < h - 1):
            break
        if alpha[int(round(y)), int(round(x))] > 8:
            r_last = r
        elif r - r_last > 40:
            break
        r += 0.5
    return r_last


def build(n):
    alpha = np.asarray(Image.open(os.path.join(LAYERS, 'Face_Skin.png')))[..., 3]
    th = np.array([2 * math.pi * i / n for i in range(n)])
    R = np.array([edge_radius(alpha, CENTER, a) for a in th])
    pts = []
    for kind, v in RINGS:
        rr = R + v if kind == 'd' else R * v
        for a, r in zip(th, rr):
            pts.append((CENTER[0] + math.cos(a) * r, CENTER[1] + math.sin(a) * r))
    pts.append(CENTER)
    tris, edges, outer = [], [], []
    nr = len(RINGS)
    for k in range(nr):
        for i in range(n):
            v, v2 = k * n + i, k * n + (i + 1) % n
            if k == 0:
                outer.append(len(edges))
            edges.append((v, v2))
            if k + 1 < nr:
                w, w2 = v + n, v2 + n
                edges.append((v, w))
                edges.append((v, w2))
                tris += [(v, v2, w2), (v, w2, w)]
    c = len(pts) - 1
    for i in range(n):
        v, v2 = (nr - 1) * n + i, (nr - 1) * n + (i + 1) % n
        edges.append((v, c))
        tris.append((v, v2, c))
    return pts, tris, edges, outer, R


def main():
    src, dst = sys.argv[1:3]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    doc = t.Cmo3(src)
    pts, tris, edges, outer, R = build(n)
    mesh_ops.remesh_points(doc, 'Face_Skin', pts, tris, edges, outer)
    doc.save(dst)
    print('REMESH_FACE_CONTOUR_DONE', len(pts), '頂点', len(tris), '三角形', '輪郭までの距離 %.0f〜%.0f' % (R.min(), R.max()))


if __name__ == '__main__':
    main()
