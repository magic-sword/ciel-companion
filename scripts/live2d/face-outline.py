# -*- coding: utf-8 -*-
"""書き出したモデルで、顔の輪郭（Face_Skin の外形）と口・顎先の位置を、指定のパラメーターで測る（頬の膨らみの調整用）。

Face_Skin の画像の外形の点を、Core が計算した Face_Skin の三角形の中の位置（重心座標）で、変形後へ写す。
出力：左右の輪郭の x（y ごと）、口の中心、顎先（キャンバス px）。
実行  python -I scripts/live2d/face-outline.py モデル.model3.json [ID=値 ...]
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cubism_core as cc

LAYERS = os.path.join(HERE, '..', '..', 'assets', 'ciel', 'current', 'layers')


def boundary(name):
    a = np.asarray(Image.open(os.path.join(LAYERS, name + '.png')))[..., 3] > 128
    pts = []
    for y in range(0, a.shape[0], 5):
        xs = np.nonzero(a[y])[0]
        if len(xs):
            pts += [(xs[0], y), (xs[-1], y)]
    return np.array(pts, float)


def warp_points(p, rest, now, tri):
    out = np.full_like(p, np.nan)
    for t in tri:
        a, b, c = rest[t]
        m = np.array([b - a, c - a]).T
        if abs(np.linalg.det(m)) < 1e-9:
            continue
        uv = np.linalg.solve(m, (p - a).T).T
        ok = (uv[:, 0] >= -1e-6) & (uv[:, 1] >= -1e-6) & (uv.sum(1) <= 1 + 1e-6) & np.isnan(out[:, 0])
        A, B, C = now[t]
        out[ok] = A + uv[ok, 0:1] * (B - A) + uv[ok, 1:2] * (C - A)
    return out


def measure(model, params):
    model.reset()
    d0 = {d['id']: d for d in model.drawables()}
    model.update()
    d0 = {d['id']: d for d in model.drawables()}
    model.reset()
    model.set(params)
    model.update()
    d1 = {d['id']: d for d in model.drawables()}
    p = boundary('Face_Skin')
    q = warp_points(p, d0['Face_Skin']['pos'], d1['Face_Skin']['pos'], d0['Face_Skin']['tri'])
    mouth = d1['Mouth_Line_Upper']['pos'].mean(0)
    return q, mouth


def main():
    model = cc.Model(sys.argv[1])
    params = {}
    for kv in sys.argv[2:]:
        k, v = kv.split('=')
        params[k] = float(v)
    q, mouth = measure(model, params)
    q = q[~np.isnan(q[:, 0])]
    chin = q[q[:, 1].argmax()]
    print('口 %.0f,%.0f  顎先 %.0f,%.0f' % (mouth[0], mouth[1], chin[0], chin[1]))
    for y in range(1150, 1400, 25):
        s = q[np.abs(q[:, 1] - y) < 4]
        if len(s):
            print('y=%d  左 %.0f  右 %.0f' % (y, s[:, 0].min(), s[:, 0].max()))


if __name__ == '__main__':
    main()
