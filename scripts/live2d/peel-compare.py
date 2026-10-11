# -*- coding: utf-8 -*-
"""「パーツを消した絵」を元の絵に重ね合わせ、消えたパーツのレイヤーを取り出す（パーツを剥がす方式、計画書 8.1）。

1. 消した絵を、元の絵に重なるように、拡大縮小と移動で合わせる（大半の画素が変わっていない前提で、差の中央値が最小になる所）。
2. 差の大きい範囲（変わった所）を求める。変わっていない所の差（RMS）が小さいほど、消した絵は元の絵に忠実。
3. 変わった所の、元の絵の画素 → 消えたパーツのレイヤー。変わった所の、消した絵の画素 → 下の描き足し。
4. 下の描き足しの上にレイヤーを重ね直した絵と、元の絵との差を出す（正面の見た目が元どおりかの確認）。

実行  python -I scripts/live2d/peel-compare.py 元の絵.png 消した絵.png 出力の接頭辞 [しきい値=24]
出力  <接頭辞>-layer.png（取り出したパーツ、透明）、-under.png（位置を合わせた消した絵）、-mask.png、-check.png（並べた確認図）、.json
"""
import json
import sys

import numpy as np
from PIL import Image


def load_rgb(p, size=None):
    im = Image.open(p).convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    im = bg.convert('RGB')
    if size and im.size != size:
        im = im.resize(size, Image.LANCZOS)
    return np.asarray(im).astype(np.float32)


def warp(img, s, dx, dy):
    """出力の画素 (x, y) ← 入力の ((x - cx - dx)/s + cx, (y - cy - dy)/s + cy)。双線形。"""
    h, w = img.shape[:2]
    cy, cx = (h - 1) / 2, (w - 1) / 2
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (xs - cx - dx) / s + cx
    v = (ys - cy - dy) / s + cy
    u = np.clip(u, 0, w - 1.001)
    v = np.clip(v, 0, h - 1.001)
    x0 = u.astype(np.int32)
    y0 = v.astype(np.int32)
    fx = (u - x0)[..., None]
    fy = (v - y0)[..., None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
            + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)


def score(a, b, step=4):
    d = np.abs(a[::step, ::step] - b[::step, ::step]).sum(-1)
    return float(np.median(d)), float(np.mean(np.minimum(d, 60)))


def main():
    orig_p, edit_p, out = sys.argv[1:4]
    thr = float(sys.argv[4]) if len(sys.argv) > 4 else 24.0
    a = load_rgb(orig_p)
    h, w = a.shape[:2]
    b = load_rgb(edit_p, (w, h))
    # 粗い探索は 1/4 に縮めた画像で、細かい探索は 1/2 で行う（全画素で何百回も変形すると遅い）
    def small(x, k):
        hh, ww = x.shape[0] // k * k, x.shape[1] // k * k
        return x[:hh, :ww].reshape(hh // k, k, ww // k, k, 3).mean((1, 3))
    a4, b4, a2, b2 = small(a, 4), small(b, 4), small(a, 2), small(b, 2)
    best = (1e9, 1.0, 0.0, 0.0)
    for s in np.linspace(0.97, 1.03, 7):
        for dx in range(-24, 25, 4):
            for dy in range(-24, 25, 4):
                c = score(a4, warp(b4, s, dx / 4, dy / 4), 1)[1]
                if c < best[0]:
                    best = (c, s, dx, dy)
    _, s0, x0, y0 = best
    best = (1e9, s0, x0, y0)
    for s in np.linspace(s0 - 0.006, s0 + 0.006, 5):
        for dx in np.arange(x0 - 4, x0 + 4.1, 1):
            for dy in np.arange(y0 - 4, y0 + 4.1, 1):
                c = score(a2, warp(b2, s, dx / 2, dy / 2), 1)[1]
                if c < best[0]:
                    best = (c, s, dx, dy)
    _, s, dx, dy = best
    bw = warp(b, s, dx, dy)
    d = np.abs(a - bw).sum(-1)
    # 変わった所：差が大きい画素を、少し太らせて穴を埋める（ゆるい形態処理）
    m = d > thr
    for _ in range(3):
        p = np.pad(m, 1)
        m = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    for _ in range(3):
        p = np.pad(m, 1, constant_values=True)
        m = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    unchanged = ~m
    rms_un = float(np.sqrt(np.mean(((a - bw) ** 2)[unchanged]))) if unchanged.any() else -1
    # 取り出したレイヤーと、重ね直し
    alpha = m.astype(np.float32)
    layer = np.concatenate([a, alpha[..., None] * 255], -1)
    recompose = bw * (1 - alpha[..., None]) + a * alpha[..., None]
    rms_all = float(np.sqrt(np.mean((recompose - a) ** 2)))
    Image.fromarray(layer.astype(np.uint8), 'RGBA').save(out + '-layer.png')
    Image.fromarray(np.clip(bw, 0, 255).astype(np.uint8)).save(out + '-under.png')
    Image.fromarray((m * 255).astype(np.uint8)).save(out + '-mask.png')
    # 確認図：元 | 消した絵（合わせた後） | 差（変わっていない所の差を強調） | 取り出したレイヤー（暗い背景）
    diffv = np.clip(d * 3, 0, 255)
    diffv = np.stack([diffv, diffv * unchanged, diffv * unchanged], -1)
    lay = a * alpha[..., None] + np.array([64, 72, 104], np.float32) * (1 - alpha[..., None])
    sheet = np.concatenate([a, bw, diffv, lay], 1)
    Image.fromarray(np.clip(sheet, 0, 255).astype(np.uint8)).resize((sheet.shape[1] // 2, sheet.shape[0] // 2), Image.LANCZOS).save(out + '-check.png')
    info = dict(original=orig_p, edited=edit_p, scale=float(s), shift=[float(dx), float(dy)],
                changed_ratio=float(m.mean()), rms_unchanged=rms_un, rms_recompose=rms_all, threshold=thr)
    json.dump(info, open(out + '.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('PEEL_COMPARE_DONE scale=%.4f shift=(%.1f,%.1f) changed=%.1f%% rms_unchanged=%.2f' % (s, dx, dy, 100 * m.mean(), rms_un))


if __name__ == '__main__':
    main()
