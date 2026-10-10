# -*- coding: utf-8 -*-
"""上を向いたときの、顎の下端の波（凸凹）の大きさを測る。

head3d-keys.py と同じ式で、Head_Warp の格子の頂点を回し（角度Y）、格子の間は双線形で補間する（Cubism のワープと同じ）。
顎の輪郭（Face_JawLine.png の線）の点をこの変形に通し、変形後の輪郭の y を、なめらかな曲線（多項式）で近似したときの
ずれ（凸凹）を、最大値と RMS で出す。head3d-keys.py の定数を引数で上書きして比べられる。
実行  python -I scripts/live2d/measure-jaw-wave.py [名前=値 ...]   例: JAW_SOFT=3.0
"""
import importlib.util
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('h3d', os.path.join(HERE, 'head3d-keys.py'))
h3d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h3d)
LINE = os.path.join(HERE, '..', '..', 'assets', 'ciel', 'layers', 'head', 'Face_JawLine.png')
RANGE = (420.0, 1780.0, -20.0, 1560.0)   # Head_Warp の格子の範囲
GRID = 24


def jaw_points():
    a = np.asarray(Image.open(LINE).convert('RGBA'))[..., 3].astype(float)
    xs, ys = [], []
    for x in range(a.shape[1]):
        col = a[:, x]
        if col.max() < 40:
            continue
        w = col / col.sum()
        xs.append(float(x))
        ys.append(float((np.arange(len(col)) * w).sum()))
    return np.array(xs), np.array(ys)


def warp(points, pitch):
    x0, x1, y0, y1 = RANGE
    gx = np.linspace(x0, x1, GRID + 1)
    gy = np.linspace(y0, y1, GRID + 1)
    rest = [(x, y) for y in gy for x in gx]
    moved = np.array(h3d.rotated(rest, 0.0, pitch)).reshape(GRID + 1, GRID + 1, 2)
    out = []
    for x, y in points:
        u = (x - x0) / (x1 - x0) * GRID
        v = (y - y0) / (y1 - y0) * GRID
        i, j = min(int(u), GRID - 1), min(int(v), GRID - 1)
        fu, fv = u - i, v - j
        p = (moved[j, i] * (1 - fu) * (1 - fv) + moved[j, i + 1] * fu * (1 - fv)
             + moved[j + 1, i] * (1 - fu) * fv + moved[j + 1, i + 1] * fu * fv)
        out.append(p)
    return np.array(out)


def roughness(xs, ys):
    # 顎の先（V 字の頂点）の左右で、別々に 3 次式で近似して、ずれを測る
    tip = xs[np.argmax(ys)]
    res = []
    for m in (xs <= tip, xs >= tip):
        c = np.polyfit(xs[m], ys[m], 3)
        res.append(ys[m] - np.polyval(c, xs[m]))
    r = np.concatenate(res)
    return np.abs(r).max(), np.sqrt((r ** 2).mean())


def main(overrides):
    for o in overrides:
        k, v = o.split('=')
        setattr(h3d, k, float(v))
    xs, ys = jaw_points()
    print('jaw points', len(xs), 'x %d-%d' % (xs.min(), xs.max()))
    for key in (0.0, 15.0, 30.0):
        pitch = h3d.PITCH[key]
        p = warp(list(zip(xs, ys)), pitch)
        mx, rms = roughness(p[:, 0], p[:, 1])
        print('angleY %+5.1f  wave max %.2f px  rms %.2f px' % (key, mx, rms))


if __name__ == '__main__':
    main(sys.argv[1:])
