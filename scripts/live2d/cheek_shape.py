# -*- coding: utf-8 -*-
"""横を向いたときの顔の輪郭の形（cheek-keys.py と preview-cheek.py が共有する）。

Face_Skin は remesh-face-contour.py の輪郭に沿ったメッシュ（N 点 × 7 輪 + 中心）であること。
角度X ±30 で、顎より下の輪郭を「目標の曲線」へ寄せる。目標の曲線は、お手本（pose_xR15・xL15）の輪郭の線を自動で読み取り、
目の位置（横）と顎先の高さ（縦）で重ねたものに、上の方（横髪に隠れる所）を今の輪郭からなめらかにつないだもの。
曲線は角を丸め（Chaikin）、輪郭の点はその曲線の最も近い点へ動かす。内側の輪は、動きを少しずつ弱めて付いてこさせる。
"""
import os

import numpy as np
from PIL import Image

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'reference', 'pose')
# お手本の絵とキャンバスの重ね方（横は目の位置、縦は顎先の高さで合わせた、お手本の座標に足す量）
REF_POSE = {+1: ('pose_xR15_y0_porcelain.png', 280, 235), -1: ('pose_xL15_y0_porcelain.png', 346, 250)}

N = 100
RING_WEIGHT = [1.0, 1.0, 1.0, 0.85, 0.5, 0.25, 0.08]
Y_START = 1000.0          # これより上（横髪・前髪に隠れる）は動かさない。Y_START〜+150 でなめらかに効かせる

def outline_points(pos):
    """輪郭の線（不透明な範囲の端から約 2 px 内側）の位置：輪 0（R+6）と輪 1（R-10）の間。"""
    return pos[0:N] + (pos[N:2 * N] - pos[0:N]) * 0.5


def chaikin(p, it=3):
    for _ in range(it):
        q = [p[0]]
        for a, b in zip(p[:-1], p[1:]):
            q += [0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b]
        q.append(p[-1])
        p = np.array(q)
    return p


def ref_outline(s):
    """お手本の顔の下半分の輪郭（茶色い線）を、顔の中心からの放射状の線で読み取り、キャンバスの座標で返す。
    髪の線（青）は除く。半径が前後と大きく違う点（髪の影など）は捨てる。並びは画面の右 → 顎 → 左。"""
    name, ox, oy = REF_POSE[s]
    im = np.asarray(Image.open(os.path.join(REF, name)).convert('RGB')).astype(int)
    line = (im[..., 0] - im[..., 2] > 8) & (im.mean(-1) < 200)
    cx, cy = 1105 - ox, 1000 - oy
    pts = []
    for a in np.linspace(0.15 * np.pi, 0.85 * np.pi, 140):
        best = None
        for rr in np.arange(150, 520, 0.5):
            x, y = int(cx + np.cos(a) * rr), int(cy + np.sin(a) * rr)
            if 0 <= x < im.shape[1] and 0 <= y < im.shape[0] and line[y, x]:
                best = (x + ox, y + oy, rr)
        if best:
            pts.append(best)
    p = np.array(pts, float)
    med = np.array([np.median(p[max(0, i - 4):i + 5, 2]) for i in range(len(p))])
    return p[np.abs(p[:, 2] - med) < 12, :2]


def target_curve(o, s):
    """目標の曲線：お手本の輪郭を、上の端（横髪に隠れる所）で今の輪郭へなめらかにつなぐ。"""
    ref = ref_outline(s)
    right = o[o[:, 0] >= np.median(o[:, 0])]
    left = o[o[:, 0] < np.median(o[:, 0])]

    def cur(side, y):
        return side[np.argmin(np.abs(side[:, 1] - y))]
    top_r, top_l = ref[0], ref[-1]
    link_r = [cur(right, y) for y in np.arange(Y_START, top_r[1] - 40, 40)]
    link_l = [cur(left, y) for y in np.arange(Y_START, top_l[1] - 40, 40)][::-1]
    pts = np.array(link_r + list(ref) + link_l, float)
    return chaikin(pts)


def nearest_on(curve, p):
    a, b = curve[:-1], curve[1:]
    d = b - a
    t = np.clip(((p[:, None, :] - a[None]) * d[None]).sum(-1) / np.maximum((d * d).sum(-1), 1e-9)[None], 0, 1)
    q = a[None] + t[..., None] * d[None]
    k = np.argmin(((q - p[:, None, :]) ** 2).sum(-1), 1)
    return q[np.arange(len(p)), k]


def shape(cur, s):
    """cur：横向き（±30）での Face_Skin の頂点の位置（キャンバス px、頬の形を付ける前）。新しい位置を返す。"""
    o = outline_points(cur)
    curve = target_curve(o, s)
    d = nearest_on(curve, o) - o
    u = np.clip((o[:, 1] - Y_START) / 150.0, 0, 1)
    d *= (u * u * (3 - 2 * u))[:, None]
    k = np.ones(5) / 5
    d = np.stack([np.convolve(np.r_[d[-2:, j], d[:, j], d[:2, j]], k, 'valid') for j in range(2)], 1)
    out = cur.copy()
    for r, w in enumerate(RING_WEIGHT):
        out[r * N:(r + 1) * N] += d * w
    return out, curve
