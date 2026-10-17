# -*- coding: utf-8 -*-
"""ほっぺの「ぷにっと押す」「つまんで引っ張る」の変形の形（v64）。

顔の回転の下に、左右のほっぺのワープ（Cheek_Squish_L・Cheek_Squish_R）を挟み、顔の曲面・口の曲面・鼻の曲面を
その子にする。ワープの格子の点を、ここで決める変形の量だけ動かしたものが、パラメーターのキーフォームになる。
同じ計算を、書き出さずに試し描きする preview.py でも使う。

座標はキャンバスの画素（2172×2896）。L はモデルの左（画面の右）、R はモデルの右（画面の左）。
- poke（−1〜1）：押す。くぼみ（DIMPLE）のまわりの肌を、少し外へ押しのける（輪郭は動かさない）。
  くぼみの影は別の層（Cheek_Dimple_*）で出す。負は、離したあとの揺れ戻りのふくらみ（物理演算の揺れ）。
- pull（x, y それぞれ −1〜1）：つまんで引っ張る。x は顔の外向きが＋、y は下向きが＋。
  つまむ点（GRAB）のまわりのかたまりが、丸く伸びる。口の端もつられる。
変形は範囲の外では 0。格子のふちでも 0 なので、ワープの外の部品とずれない。
"""
import numpy as np

FACE_W = 723.0                     # Face_Skin の横幅
OUTWARD = {'L': np.array([1.0, 0.0]), 'R': np.array([-1.0, 0.0])}   # 顔の外向き
DOWN = np.array([0.0, 1.0])

# くぼみの中心（Codex が描いたくぼみの影の中心。assets/ciel/generated/v64/report.md）と、押しのける範囲・量
DIMPLE = {'L': np.array([1304.0, 1236.0]), 'R': np.array([912.0, 1236.0])}
DIMPLE_R = 0.085
DIMPLE_PUSH = 0.012

# つまむ点（輪郭の上）と、伸ばすかたまりの範囲（横・上・下）・量（顔の横幅に対する比）
GRAB = {'L': np.array([1380.0, 1245.0]), 'R': np.array([842.0, 1258.0])}
GRAB_MASS = (0.34, 0.16, 0.24)
GRAB_REACH = {'L': 0.12, 'R': 0.12}
# 口の端（画面の右が L）と、つられて動く範囲・割合
MOUTH_CORNER = {'L': np.array([1160.0, 1247.0]), 'R': np.array([1056.0, 1247.0])}
MOUTH_R = (0.10, 0.06, 0.08)
MOUTH_FOLLOW = 0.45

# ワープの格子の範囲と分割（キャンバスの画素）。子のワープがはみ出さないよう顔全体を覆い、ふちでは変形を 0 にする
GRID_BOX = (640.0, 430.0, 1580.0, 1520.0)   # 子にする顔の曲面・口・鼻の格子をすべて含む
GRID_COLS, GRID_ROWS = 36, 42   # 1 マス約 26×26 px（つまんだ所のとがりを出すため）


def _falloff(p, c, radius):
    """中心 c から楕円の範囲で 1 → 0 になる重み（(1−d²)²、なめらか）。上と下で範囲が違う"""
    rx, ry_up, ry_down = (r * FACE_W for r in radius)
    dx = (p[:, 0] - c[0]) / rx
    ry = np.where(p[:, 1] < c[1], ry_up, ry_down)
    dy = (p[:, 1] - c[1]) / ry
    d2 = dx * dx + dy * dy
    w = np.clip(1.0 - d2, 0.0, 1.0) ** 2
    return w, np.sqrt(d2)


def displacement(p, side, poke=0.0, pull_x=0.0, pull_y=0.0):
    """点 p（N×2、画素）を動かす量（N×2、画素）"""
    p = np.asarray(p, dtype=float)
    out = np.zeros_like(p)
    if poke:
        # 押した所（くぼみの中心）は浅くへこみ、まわりの肌が押しのけられて少し盛り上がる。輪郭は動かさない。
        # poke が負のとき（離したあとの揺れ戻り）は、逆に中心が少しふくらむ（ぷるん）
        dc = DIMPLE[side]
        r = p - dc
        dist = np.linalg.norm(r, axis=1)
        unit = r / (dist[:, None] + 1e-6)
        rad = DIMPLE_R * FACE_W
        t = dist / rad
        # 中心から外へ押しのける量：中心で 0、半径の 0.45 あたりで最大、半径の外で 0
        tc = np.clip(t, 0, 1)
        push = np.sin(np.pi * tc) * np.sqrt(1 - tc)
        out += (poke * DIMPLE_PUSH * FACE_W) * push[:, None] * unit
    if pull_x or pull_y:
        # ほっぺのかたまり全体が、おもちのように丸く伸びる。つまんだ点のまわりを広く、なめらかな山の形で引くので、
        # 伸びた先は丸く、根元は広い（一点をとがらせると、皮だけを引っ張って破けそうに見えた。2026-10-17）。
        # 口の端も、引かれる方へつられて伸びる
        g = GRAB[side]
        direction = pull_x * OUTWARD[side] + pull_y * DOWN
        w_mass, _ = _falloff(p, g, GRAB_MASS)
        out += (GRAB_REACH[side] * FACE_W) * np.sqrt(w_mass)[:, None] * direction
        w_mouth, _ = _falloff(p, MOUTH_CORNER[side], MOUTH_R)
        out += (MOUTH_FOLLOW * GRAB_REACH[side] * FACE_W) * w_mouth[:, None] * direction
    return out


def grid():
    """ワープの格子の点（(rows+1)×(cols+1) 個、行ごと、画素）"""
    x0, y0, x1, y1 = GRID_BOX
    xs, ys = np.meshgrid(np.linspace(x0, x1, GRID_COLS + 1), np.linspace(y0, y1, GRID_ROWS + 1))
    return np.column_stack([xs.ravel(), ys.ravel()])


def warp_points(p, moved_grid):
    """ワープと同じく、格子のマスの中で双一次補間して、点 p を動かした位置を返す（格子の外は、そのまま）"""
    p = np.asarray(p, dtype=float)
    x0, y0, x1, y1 = GRID_BOX
    u = (p[:, 0] - x0) / (x1 - x0) * GRID_COLS
    v = (p[:, 1] - y0) / (y1 - y0) * GRID_ROWS
    inside = (u >= 0) & (u <= GRID_COLS) & (v >= 0) & (v <= GRID_ROWS)
    i = np.clip(np.floor(u).astype(int), 0, GRID_COLS - 1)
    j = np.clip(np.floor(v).astype(int), 0, GRID_ROWS - 1)
    fu, fv = (u - i)[:, None], (v - j)[:, None]
    g = moved_grid.reshape(GRID_ROWS + 1, GRID_COLS + 1, 2)
    q = ((1 - fu) * (1 - fv) * g[j, i] + fu * (1 - fv) * g[j, i + 1]
         + (1 - fu) * fv * g[j + 1, i] + fu * fv * g[j + 1, i + 1])
    return np.where(inside[:, None], q, p)
