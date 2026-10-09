# -*- coding: utf-8 -*-
"""Cubism も Unity も使わずに、.cmo3 の頭の向き（角度X・角度Y）の見た目を、Python で近似して描く。

形の調整（head3d-keys.py）を、素早く試すための確認用。Unity の描画と完全には一致しない
（ワープデフォーマの補間を、双線形で近似している）。最終の確認は、Unity（CielRenderCheck）で行う。

入力  .cmo3、角度X、角度Y、出力 PNG
実行  python -I scripts/live2d/preview-pose.py 入力.cmo3 出力.png 角度X 角度Y [角度X 角度Y ...]
      複数の向きを並べるときは、X Y の組を続けて書く（左から順に並ぶ）。
描くもの：頭のレイヤー（Head_Warp の子）と、体・後ろ髪（動かさない）。目は開いた状態、口は閉じた状態。
切り出し：見本（pose-ref）と同じ範囲（キャンバスの x318・y236、1536 四方）を縮小。
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

ROOT = os.path.join(HERE, '..', '..', 'assets', 'ciel', 'layers')
KEYS = [-30.0, -15.0, 0.0, 15.0, 30.0]
SCALE = 0.5                     # 描く解像度（キャンバスの 1/2）
W, H = 2172, 2896
STATIC = ['Hair_Back', 'Body_Base', 'Outer_L', 'Outer_R', 'Waist_Belt', 'Chest_Gem', 'Neck_Gear']
SKIP = re.compile(r'(_Closed|_Half)$|^Face_Base$|^Mouth_(Small|Large)$')


def load_png(name):
    p = glob.glob(os.path.join(ROOT, '*', name + '.png'))[0]
    return np.asarray(Image.open(p).convert('RGBA')).astype(np.float32) / 255.0


def mesh_names(doc):
    return re.findall(r'<CArtMeshSource xs\.id="#\d+"[^>]*>.*?<s xs\.n="localName">([^<]*)</s>', doc.xml, flags=re.S)


def floats(blk, name):
    m = re.search(r'<float-array xs\.n="%s" count="\d+">([^<]*)</float-array>' % name, blk)
    return np.array([float(v) for v in m.group(1).split()], np.float64).reshape(-1, 2) if m else None


def read_mesh(doc, name):
    a, b = doc.mesh_block(name)
    blk = doc.xml[a:b]
    pts = floats(blk, 'point')
    idx = np.array([int(v) for v in re.search(r'<int-array xs\.n="indices" count="\d+">([^<]*)</int-array>', blk).group(1).split()]).reshape(-1, 3)
    k = blk.index('<carray_list xs.n="keyforms"')
    k2 = blk.index('</carray_list>', k)
    forms = re.findall(r'<CArtMeshForm>.*?</CArtMeshForm>', blk[k:k2], flags=re.S)
    kf = []
    for f in forms:
        kf.append((float(re.search(r'<f xs\.n="opacity">([^<]*)</f>', f).group(1)), int(re.search(r'<i xs\.n="drawOrder">(\d+)</i>', f).group(1)), floats(f, 'positions')))
    best = max(range(len(kf)), key=lambda i: (kf[i][0], -i))
    mm = re.search(r'<CDeformerGuid xs\.n="targetDeformerGuid" xs\.ref="(#\d+)"', blk)
    guid = mm.group(1) if mm else None
    return dict(name=name, pts=pts, idx=idx, opacity=kf[best][0], order=kf[best][1], pos=kf[best][2], target=guid)


def key_weights(v):
    v = min(30.0, max(-30.0, v))
    for i in range(4):
        if KEYS[i] <= v <= KEYS[i + 1]:
            w = (v - KEYS[i]) / (KEYS[i + 1] - KEYS[i])
            return i, w
    return 3, 1.0


def warp_grid(doc, name, x, y):
    forms = doc.warp_keyform_positions(name)
    info = doc.warp_info(name)
    n = len(forms[0])
    f = np.array(forms, np.float64)          # 25 x n x 2、並びは 行(Y) × 5 + 列(X)
    xi, xw = key_weights(x)
    yi, yw = key_weights(y)
    g = np.zeros((n, 2))
    for dy, wy in ((0, 1 - yw), (1, yw)):
        for dx, wx in ((0, 1 - xw), (1, xw)):
            g += f[(yi + dy) * 5 + (xi + dx)] * wy * wx
    side = int(round(n ** 0.5))
    return g.reshape(side, side, 2), info


def warp_points(grid, norm):
    side = grid.shape[0] - 1
    out = np.zeros_like(norm)
    for i, (u, v) in enumerate(norm):
        fu, fv = u * side, v * side
        cx = min(side - 1, max(0, int(np.floor(fu))))
        cy = min(side - 1, max(0, int(np.floor(fv))))
        tu, tv = fu - cx, fv - cy
        p = (grid[cy, cx] * (1 - tu) * (1 - tv) + grid[cy, cx + 1] * tu * (1 - tv)
             + grid[cy + 1, cx] * (1 - tu) * tv + grid[cy + 1, cx + 1] * tu * tv)
        out[i] = p
    return out


def draw_mesh(canvas, tex, src, dst, idx, opacity):
    """src：テクスチャ（画像座標）、dst：キャンバス上の位置（どちらも元寸の px）。三角形ごとに塗る。"""
    th, tw = tex.shape[:2]
    s = SCALE
    for tri in idx:
        d = dst[tri] * s
        sp = src[tri]
        x0, y0 = np.floor(d.min(0)).astype(int)
        x1, y1 = np.ceil(d.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, canvas.shape[1] - 1), min(y1, canvas.shape[0] - 1)
        if x1 <= x0 or y1 <= y0:
            continue
        det = (d[1, 1] - d[2, 1]) * (d[0, 0] - d[2, 0]) + (d[2, 0] - d[1, 0]) * (d[0, 1] - d[2, 1])
        if abs(det) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l0 = ((d[1, 1] - d[2, 1]) * (gx - d[2, 0]) + (d[2, 0] - d[1, 0]) * (gy - d[2, 1])) / det
        l1 = ((d[2, 1] - d[0, 1]) * (gx - d[2, 0]) + (d[0, 0] - d[2, 0]) * (gy - d[2, 1])) / det
        l2 = 1 - l0 - l1
        m = (l0 >= -0.001) & (l1 >= -0.001) & (l2 >= -0.001)
        if not m.any():
            continue
        sx = l0 * sp[0, 0] + l1 * sp[1, 0] + l2 * sp[2, 0]
        sy = l0 * sp[0, 1] + l1 * sp[1, 1] + l2 * sp[2, 1]
        ix = np.clip(sx.astype(int), 0, tw - 1)
        iy = np.clip(sy.astype(int), 0, th - 1)
        c = tex[iy, ix]
        a = c[..., 3] * opacity * m
        reg = canvas[y0:y1 + 1, x0:x1 + 1]
        reg[..., :3] = reg[..., :3] * (1 - a[..., None]) + c[..., :3] * a[..., None]
        reg[..., 3] = reg[..., 3] + a * (1 - reg[..., 3])


def render(doc, x, y, skin=None):
    """skin：(PNG のパス, キャンバス上の x, y) を渡すと、Face_Skin の代わりに、その画像を、動かさずに置く（実験用）。"""
    canvas = np.zeros((int(H * SCALE), int(W * SCALE), 4), np.float32)
    canvas[..., :3] = (60 / 255, 60 / 255, 100 / 255)
    canvas[..., 3] = 1.0
    grid, info = warp_grid(doc, 'Head_Warp', x, y)
    items = []
    for n in mesh_names(doc):
        if n in STATIC or SKIP.search(n):
            if n in STATIC:
                items.append((read_mesh(doc, n), n))
            continue
        items.append((read_mesh(doc, n), n))
    items = [(m, n, i) for i, (m, n) in enumerate(items)]
    items.sort(key=lambda it: (it[0]['order'], -it[2]))     # 同じ描画順では、リストの上（先）が前
    for m, n, _ in items:
        if m['opacity'] <= 0.001 or n in os.environ.get('HIDE', '').split(','):
            continue
        if skin and n == 'Face_Skin':
            im = np.asarray(Image.open(skin[0]).convert('RGBA')).astype(np.float32) / 255.0
            q = int(round(SCALE * 1536))
            im = np.asarray(Image.fromarray((im * 255).astype(np.uint8)).resize((q, q), Image.LANCZOS)).astype(np.float32) / 255.0
            ox, oy = int(skin[1] * SCALE), int(skin[2] * SCALE)
            reg = canvas[oy:oy + q, ox:ox + q]
            a = im[..., 3:4]
            reg[..., :3] = reg[..., :3] * (1 - a) + im[..., :3] * a
            continue
        tex = load_png(n)
        if m['target'] == info['guid']:
            norm = m['pos']
            dst = warp_points(grid, norm)
        else:
            dst = m['pos']
        draw_mesh(canvas, tex, m['pts'], dst, m['idx'], m['opacity'])
    return canvas


def main(src, out, pairs, skins=None):
    doc = t.Cmo3(src)
    tiles = []
    for k, (x, y) in enumerate(pairs):
        c = render(doc, x, y, skins[k] if skins else None)
        im = Image.fromarray((np.clip(c[..., :3], 0, 1) * 255).astype(np.uint8))
        s = SCALE
        tiles.append(im.crop((int(318 * s), int(236 * s), int((318 + 1536) * s), int((236 + 1536) * s))))
    sheet = Image.new('RGB', (tiles[0].width * len(tiles), tiles[0].height))
    for i, im in enumerate(tiles):
        sheet.paste(im, (i * im.width, 0))
    sheet.save(out)
    print('PREVIEW', out)


if __name__ == '__main__':
    a = sys.argv
    vals = [float(v) for v in a[3:]]
    main(a[1], a[2], list(zip(vals[0::2], vals[1::2])))
