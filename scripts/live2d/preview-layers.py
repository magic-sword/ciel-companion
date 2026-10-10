# -*- coding: utf-8 -*-
"""レイヤーの PNG を、モデルと同じ動きの式で変形して重ね、頭の向きの見え方を確かめる（Cubism・Unity を使わない）。

素材（Codex の新しいパーツなど）を、モデルに組み込む前に確かめるためのもの。動きは、
  頭のパーツ：head3d-keys.py の顔の表面の回転（目の部分は平ら）、
  顎の裏と線（Chin_Under・Chin_Under_Line）：chin-under-keys.py（上の縁は顔の顎、下の縁は首に付けて伸び縮み）、
  後ろ髪：hair-back-follow.py、
  体・首・首輪・首の線：動かない。
モデルの Head_Warp（格子の双線形）とは少し違う近似。最終の確認は Unity で行う。
実行  python -I scripts/live2d/preview-layers.py 出力.png [--parts 素材のフォルダ] 角度X 角度Y [角度X 角度Y ...]
  --parts を付けると、その中の PNG を layers/ の同じ名前より優先して使う（例：assets/ciel/generated/v5/parts）。
"""
import importlib.util
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..', 'assets', 'ciel', 'layers')


def load_module(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


h3d = load_module('h3d', 'head3d-keys.py')
chin = load_module('chin', 'chin-under-keys.py')
hair = load_module('hair', 'hair-back-follow.py')

W, H = 2172, 2896
BOX = (500, 200, 1700, 1800)     # 描く範囲（頭と首）
SCALE = 0.5
STEP = 8                         # 変形を計算する格子の間隔（画素）

# (名前, 動き, 不透明度の決め方)。下から上の順
STACK = [
    ('Hair_Back', 'hair', None), ('Body_Base', 'static', None), ('Outer_L', 'static', None), ('Outer_R', 'static', None),
    ('Body_Fur', 'static', None), ('Waist_Belt', 'static', None), ('Chest_Gem', 'static', None),
    ('Neck_Line', 'static', 'up'), ('Chin_Under_Line', 'chin', 'up'), ('Chin_Under', 'chin', 'up'), ('Neck_Gear', 'static', None),
    ('Face_Skin', 'head', None), ('Face_JawLine', 'head', 'jaw'), ('Face_Blush', 'head', 0.7), ('Face_Nose', 'head', None),
    ('Mouth_Closed', 'head', None),
    ('R_sclera', 'head', None), ('R_iris', 'head', None), ('R_lash', 'head', None), ('R_crease', 'head', None),
    ('L_sclera', 'head', None), ('L_iris', 'head', None), ('L_lash', 'head', None), ('L_crease', 'head', None),
    ('Hair_Crown', 'head', None), ('Ear_L', 'head', None), ('Ear_R', 'head', None),
    ('Hair_Side_L', 'head', None), ('Hair_Side_R', 'head', None), ('Hair_Front', 'head', None),
    ('Brow_L', 'head', None), ('Brow_R', 'head', None), ('Hair_Ahoge', 'head', None),
]
JAW_OPACITY = {-30.0: 1.0, -15.0: 1.0, 0.0: 1.0, 15.0: 0.35, 30.0: 0.0}


def interp_key(table, v):
    keys = sorted(table)
    v = max(keys[0], min(keys[-1], v))
    for a, b in zip(keys, keys[1:]):
        if a <= v <= b:
            t = (v - a) / (b - a) if b > a else 0.0
            return table[a] + (table[b] - table[a]) * t
    return table[keys[-1]]


def interp_angle(table, v):
    return interp_key(table, v)


def find(name, parts_dir):
    if parts_dir:
        p = os.path.join(parts_dir, name + '.png')
        if os.path.exists(p):
            return p
        p = os.path.join(parts_dir, 'eyes', name + '.png')
        if os.path.exists(p):
            return p
    for sub in ('head', 'body', 'eyes'):
        p = os.path.join(ROOT, sub, name + '.png')
        if os.path.exists(p):
            return p
    return None


def displacement(kind, ax, ay):
    """格子の点ごとの、元の位置 → 動いた位置の差（dx, dy）。"""
    yaw = interp_angle(h3d.YAW, ax)
    pitch = interp_angle(h3d.PITCH, ay)
    xs = np.arange(BOX[0], BOX[2] + STEP, STEP, dtype=np.float64)
    ys = np.arange(BOX[1], BOX[3] + STEP, STEP, dtype=np.float64)
    pts = [(x, y) for y in ys for x in xs]
    if kind == 'head':
        moved = h3d.rotated(pts, yaw, pitch)
    elif kind == 'chin':
        moved = chin.moved(pts, yaw, pitch)
    elif kind == 'hair':
        moved = hair.moved(pts, yaw, pitch)
    else:
        return None
    d = np.array(moved) - np.array(pts)
    return d[:, 0].reshape(len(ys), len(xs)), d[:, 1].reshape(len(ys), len(xs))


def upsample(a, w, h):
    return np.asarray(Image.fromarray(a.astype(np.float32), 'F').resize((w, h), Image.BILINEAR))


def sample(img, x, y):
    """img（h×w×4、float）を、座標 x, y（同じ大きさの配列）で双線形に読む。範囲外は透明。"""
    h, w = img.shape[:2]
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    out = np.zeros(x.shape + (4,), np.float32)
    for dx, dy, wgt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        v = np.zeros(x.shape + (4,), np.float32)
        v[ok] = img[yi[ok], xi[ok]]
        out += v * wgt
    return out


def render(ax, ay, parts_dir):
    bw, bh = BOX[2] - BOX[0], BOX[3] - BOX[1]
    ow, oh = int(bw * SCALE), int(bh * SCALE)
    gx, gy = np.meshgrid(np.arange(ow) / SCALE + BOX[0], np.arange(oh) / SCALE + BOX[1])
    canvas = np.zeros((oh, ow, 3), np.float32)
    canvas[:] = (60, 60, 100)
    cache = {}
    for name, kind, op in STACK:
        p = find(name, parts_dir)
        if p is None:
            continue
        if op == 'up':
            alpha = interp_key(chin.OPACITY_Y, ay)
        elif op == 'jaw':
            alpha = interp_key(JAW_OPACITY, ay)
        elif op is None:
            alpha = 1.0
        else:
            alpha = op
        if alpha <= 0:
            continue
        img = np.asarray(Image.open(p).convert('RGBA')).astype(np.float32)
        if kind == 'static':
            sx, sy = gx, gy
        else:
            if kind not in cache:
                dx, dy = displacement(kind, ax, ay)
                gw = dx.shape[1]
                gh = dx.shape[0]
                # 格子（STEP 間隔）→ 出力の画素へ
                cache[kind] = (upsample(dx, int(gw * STEP * SCALE), int(gh * STEP * SCALE))[:oh, :ow],
                               upsample(dy, int(gw * STEP * SCALE), int(gh * STEP * SCALE))[:oh, :ow])
            ddx, ddy = cache[kind]
            # 逆写像：出力の点 p について、元の点 x を x = p - d(x) の反復で求める
            sx, sy = gx.copy(), gy.copy()
            for _ in range(6):
                u = np.clip(((sx - BOX[0]) * SCALE).astype(int), 0, ow - 1)
                v = np.clip(((sy - BOX[1]) * SCALE).astype(int), 0, oh - 1)
                sx = gx - ddx[v, u]
                sy = gy - ddy[v, u]
        layer = sample(img, sx, sy)
        a = layer[..., 3:4] / 255.0 * alpha
        canvas = canvas * (1 - a) + layer[..., :3] * a
    return Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))


def main(argv):
    parts_dir = None
    if '--parts' in argv:
        i = argv.index('--parts')
        parts_dir = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    out = argv[0]
    angles = [(float(argv[i]), float(argv[i + 1])) for i in range(1, len(argv), 2)]
    tiles = [render(ax, ay, parts_dir) for ax, ay in angles]
    sheet = Image.new('RGB', (sum(t.width for t in tiles), tiles[0].height + 20), 'white')
    d = ImageDraw.Draw(sheet)
    x = 0
    for (ax, ay), t in zip(angles, tiles):
        sheet.paste(t, (x, 20))
        d.text((x + 4, 4), 'X %+.0f  Y %+.0f' % (ax, ay), fill='red')
        x += t.width
    sheet.save(out)
    print('PREVIEW_LAYERS', out)


if __name__ == '__main__':
    main(sys.argv[1:])
