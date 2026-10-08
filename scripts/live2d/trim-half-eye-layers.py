"""半目レイヤーの後処理。

build-eye-layers.ps1 が作る {R,L}_iris_half.png は、まつ毛に隠れる虹彩の上部を楕円で補完するため、
半目ではまつ毛の上端より上に虹彩の青い線がはみ出す。各列でまつ毛の上端を求め、それより上の虹彩を消す。
実行: python -I scripts/live2d/trim-half-eye-layers.py   完了表示 HALF_EYE_TRIMMED
入出力: assets/ciel/layers/eyes/
"""
import os
import sys

import numpy as np
from PIL import Image

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..',
                    'assets', 'ciel', 'layers', 'eyes')
LASH_ALPHA = 100
IRIS = {'R': (921, 1057), 'L': (1288, 1044)}   # iris centre (x, y) in the 2172x2896 canvas
result = []
for side in ('R', 'L'):
    lash = np.asarray(Image.open(os.path.join(root, f'{side}_lash_half.png')).convert('RGBA'))[..., 3]
    path = os.path.join(root, f'{side}_iris_half.png')
    iris = np.array(Image.open(path).convert('RGBA'))
    h, w = lash.shape
    top = np.full(w, -1)
    for x in range(w):
        ys = np.nonzero(lash[:, x] >= LASH_ALPHA)[0]
        if ys.size:
            top[x] = ys[0]
    xs = np.nonzero(top >= 0)[0]
    if xs.size == 0:
        print('no lash found', side)
        sys.exit(1)
    # Columns without lash take the nearest column's lash top.
    for x in range(w):
        if top[x] < 0:
            top[x] = top[xs[np.argmin(np.abs(xs - x))]]
    erased = 0
    for x in range(w):
        col = iris[:int(top[x]), x, 3]
        erased += int((col > 0).sum())
        iris[:int(top[x]), x, 3] = 0
    # Anything outside the iris ellipse (same centre/radii as build-eye-layers.ps1, 8% margin) is not iris.
    icx, icy = IRIS[side]
    yy, xx = np.mgrid[0:iris.shape[0], 0:iris.shape[1]]
    outside = ((xx - icx) / (67.5 * 1.08)) ** 2 + ((yy - icy) / (69.5 * 1.08)) ** 2 > 1.0
    gone = outside & (iris[..., 3] > 0)
    erased += int(gone.sum())
    iris[gone, 3] = 0
    # Keep only the largest connected piece of the iris; the leftovers are specks along the lash edge.
    ys, xs = np.nonzero(iris[..., 3] > 0)
    if ys.size:
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        sub = iris[y0:y1, x0:x1, 3] > 0
        labels = np.zeros(sub.shape, dtype=np.int32)
        sizes = [0]
        for sy, sx in zip(*np.nonzero(sub)):
            if labels[sy, sx]:
                continue
            n = len(sizes)
            stack = [(sy, sx)]
            labels[sy, sx] = n
            size = 0
            while stack:
                cy, cx = stack.pop()
                size += 1
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < sub.shape[0] and 0 <= nx < sub.shape[1] and sub[ny, nx] and not labels[ny, nx]:
                        labels[ny, nx] = n
                        stack.append((ny, nx))
            sizes.append(size)
        keep = int(np.argmax(sizes))
        stray = (labels != keep) & sub
        erased += int(stray.sum())
        view = iris[y0:y1, x0:x1, 3]
        view[stray] = 0
        # Opening with an 11x11 square removes thin protrusions and blobs smaller than that (specks next to the lash tips).
        r = 5
        solid = view > 0
        pad = np.pad(solid, r, constant_values=False)
        eroded = np.ones_like(solid)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                eroded &= pad[r + dy:r + dy + solid.shape[0], r + dx:r + dx + solid.shape[1]]
        pad = np.pad(eroded, r, constant_values=False)
        opened = np.zeros_like(solid)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                opened |= pad[r + dy:r + dy + solid.shape[0], r + dx:r + dx + solid.shape[1]]
        gone = solid & ~opened
        erased += int(gone.sum())
        view[gone] = 0
    Image.fromarray(iris).save(path)
    # The lash colour was recovered by un-mixing against the eyeless face and picks up some of the iris blue
    # along the lash edge. Replace those pixels' colour with the local average of the clean lash pixels.
    lpath = os.path.join(root, f'{side}_lash_half.png')
    lash_rgba = np.array(Image.open(lpath).convert('RGBA')).astype(float)
    blue = (lash_rgba[..., 3] > 0) & (lash_rgba[..., 2] > lash_rgba[..., 0] + 40)
    clean = (lash_rgba[..., 3] >= 200) & ~blue
    fixed = int(blue.sum())
    if fixed:
        ys, xs = np.nonzero(blue)
        y0, y1, x0, x1 = max(ys.min() - 16, 0), ys.max() + 17, max(xs.min() - 16, 0), xs.max() + 17
        rgb = lash_rgba[y0:y1, x0:x1, :3]
        wgt = clean[y0:y1, x0:x1].astype(float)
        k = 15
        def box(a):
            p = np.pad(a, ((k, k), (k, k)) + ((0, 0),) * (a.ndim - 2))
            integral = np.zeros((p.shape[0] + 1, p.shape[1] + 1) + p.shape[2:])
            integral[1:, 1:] = p.cumsum(0).cumsum(1)
            s = 2 * k + 1
            h, w = a.shape[:2]
            return (integral[s:s + h, s:s + w] - integral[:h, s:s + w]
                    - integral[s:s + h, :w] + integral[:h, :w])
        num = box(rgb * wgt[..., None])
        den = box(wgt)[..., None]
        avg = np.where(den > 0, num / np.maximum(den, 1e-6), rgb)
        sub_blue = blue[y0:y1, x0:x1]
        rgb[sub_blue] = avg[sub_blue]
        lash_rgba[y0:y1, x0:x1, :3] = rgb
        Image.fromarray(lash_rgba.round().clip(0, 255).astype('uint8')).save(lpath)
    result.append(f'{side} erased={erased} lash_blue_fixed={fixed}')
print('HALF_EYE_TRIMMED ' + ' '.join(result))
