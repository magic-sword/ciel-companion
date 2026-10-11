# -*- coding: utf-8 -*-
"""生成したパーツ（透明 PNG）を、基準画像の上の位置・大きさ・回転に合わせて、作業キャンバスへ置く。

生成した絵は基準画像と画素単位では一致しない（形・位置が少しずつ違う）。そこで、パーツの線（明るさの段差）が、
基準画像の線の近くに来るような、拡大縮小・回転・移動（相似変換）を探す。パーツの描き足し部分（基準画像では
隠れている所）の線は、基準画像に対応する線がないので、距離を打ち切って（TRUNC）影響を抑える。

実行  python -I scripts/live2d/register-part.py パーツ.png 位置の目安 出力.png [--base 基準画像] [--fit width|height|both]
      位置の目安は "x0,y0,x1,y1"（作業キャンバスの座標。パーツの不透明な範囲がおよそ収まる箱）
出力  出力.png（作業キャンバス 2172×2896 の透明 PNG）、出力.json（変換と、合い具合）、出力.check.png（確認用の重ね図）
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
BASE = os.path.join(ROOT, 'assets', 'ciel', 'master', 'ciel-upper-body-2x.png')
CANVAS = (2172, 2896)
TRUNC = 12.0          # 線どうしの距離の打ち切り（px）
COLOR_W = 1.0         # 色の差の重み（線の距離は TRUNC で割って 0〜1 にしてある）


def sobel(a, axis):
    """3×3 のソーベル（SciPy を使わない）。axis=1 は横、0 は縦の微分。"""
    p = np.pad(a, 1, mode='edge')
    if axis == 1:
        d = p[:, 2:] - p[:, :-2]
        return d[:-2] + 2 * d[1:-1] + d[2:]
    d = p[2:] - p[:-2]
    return d[:, :-2] + 2 * d[:, 1:-1] + d[:, 2:]


def chamfer(mask, trunc):
    """mask（線＝True）からの距離（打ち切り付き、3-4 チャンファー距離を px に換算）。"""
    inf = trunc * 3 + 10
    d = np.where(mask, 0.0, inf)
    for _ in range(int(trunc) + 2):
        p = np.pad(d, 1, mode='constant', constant_values=inf)
        n = np.minimum.reduce([p[1:-1, 1:-1], p[:-2, 1:-1] + 1, p[2:, 1:-1] + 1, p[1:-1, :-2] + 1, p[1:-1, 2:] + 1,
                               p[:-2, :-2] + 1.414, p[:-2, 2:] + 1.414, p[2:, :-2] + 1.414, p[2:, 2:] + 1.414])
        if np.array_equal(n, d):
            break
        d = n
    return np.minimum(d, trunc)


def bilinear(img, y, x, cval=0.0):
    h, w = img.shape
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = x - x0
    fy = y - y0
    out = np.zeros(x.shape, np.float64)
    for dy, wy in ((0, 1 - fy), (1, fy)):
        for dx, wx in ((0, 1 - fx), (1, fx)):
            xx = x0 + dx
            yy = y0 + dy
            ok = (xx >= 0) & (yy >= 0) & (xx < w) & (yy < h)
            v = np.full(x.shape, cval, np.float64)
            v[ok] = img[yy[ok], xx[ok]]
            out += v * wx * wy
    return out


def nelder_mead(f, x0, steps, iters=400, tol=1e-4):
    n = len(x0)
    pts = [np.array(x0, float)] + [np.array(x0, float) + np.eye(n)[i] * steps[i] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        o = np.argsort(vals)
        pts = [pts[i] for i in o]
        vals = [vals[i] for i in o]
        if vals[-1] - vals[0] < tol:
            break
        c = np.mean(pts[:-1], 0)
        r = c + (c - pts[-1]); fr = f(r)
        if fr < vals[0]:
            e = c + 2 * (c - pts[-1]); fe = f(e)
            pts[-1], vals[-1] = (e, fe) if fe < fr else (r, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = r, fr
        else:
            k = c + 0.5 * (pts[-1] - c); fk = f(k)
            if fk < vals[-1]:
                pts[-1], vals[-1] = k, fk
            else:
                pts = [pts[0]] + [pts[0] + 0.5 * (p - pts[0]) for p in pts[1:]]
                vals = [vals[0]] + [f(p) for p in pts[1:]]
    i = int(np.argmin(vals))
    return pts[i], vals[i]


def luminance(rgba, bg=1.0):
    a = rgba[..., 3:4]
    rgb = rgba[..., :3] * a + bg * (1 - a)
    return rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def edge_map(lum, alpha=None):
    gx = sobel(lum, 1)
    gy = sobel(lum, 0)
    e = np.hypot(gx, gy)
    if alpha is not None:
        e = np.maximum(e, np.hypot(sobel(alpha, 1), sobel(alpha, 0)))
    return e


def load(path):
    return np.asarray(Image.open(path).convert('RGBA')).astype(np.float32) / 255.0


def transform_points(pts, s, th, tx, ty, c):
    """パーツ画像の点（パーツの中心 c が原点）→ キャンバスの点。"""
    ct, st = math.cos(th), math.sin(th)
    x = (pts[:, 0] - c[0]) * s
    y = (pts[:, 1] - c[1]) * s
    return np.stack([x * ct - y * st + tx, x * st + y * ct + ty], 1)


def main():
    args = sys.argv[1:]
    part_path, box, out = args[0], [float(v) for v in args[1].split(',')], args[2]
    base_path = BASE
    fit = 'both'
    if '--base' in args:
        base_path = args[args.index('--base') + 1]
    if '--fit' in args:
        fit = args[args.index('--fit') + 1]

    part = load(part_path)
    alpha = part[..., 3]
    ys, xs = np.nonzero(alpha > 0.5)
    pb = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    pc = np.array([(pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2])

    # パーツの線の点（強い段差の上位）。多すぎると遅いので間引く
    pe = edge_map(luminance(part), alpha)
    pe[alpha < 0.05] = 0
    thr = np.percentile(pe[pe > 0], 85)
    py, px = np.nonzero(pe > thr)
    if len(px) > 20000:
        k = np.random.default_rng(0).choice(len(px), 20000, replace=False)
        px, py = px[k], py[k]
    pts = np.stack([px, py], 1).astype(np.float64)
    # 色の比較に使う点（不透明な所から間引き）と、その色（白背景に合成した RGB）
    cy, cx = np.nonzero(alpha > 0.9)
    k = np.random.default_rng(1).choice(len(cx), min(15000, len(cx)), replace=False)
    cpts = np.stack([cx[k], cy[k]], 1).astype(np.float64)
    ccol = part[cy[k], cx[k], :3]

    # 基準画像の、目安の箱を広げた範囲の線の距離マップ
    base = load(base_path)
    if base.shape[1] != CANVAS[0]:
        raise SystemExit('基準画像の大きさが作業キャンバスと違う: %s' % (base.shape,))
    bw, bh = box[2] - box[0], box[3] - box[1]
    m = 0.35
    rx0, ry0 = int(max(0, box[0] - bw * m)), int(max(0, box[1] - bh * m))
    rx1, ry1 = int(min(CANVAS[0], box[2] + bw * m)), int(min(CANVAS[1], box[3] + bh * m))
    reg = base[ry0:ry1, rx0:rx1]
    be = edge_map(luminance(reg), reg[..., 3])
    bthr = np.percentile(be, 88)
    dist = chamfer(be >= bthr, TRUNC)
    regw = reg[..., :3] * reg[..., 3:4] + (1 - reg[..., 3:4])   # 白背景に合成
    H, W = dist.shape

    sw = bw / (pb[2] - pb[0])
    sh = bh / (pb[3] - pb[1])
    s0 = {'width': sw, 'height': sh}.get(fit, math.sqrt(sw * sh))
    def cost(p):
        s, th, tx, ty = p
        if not (0.75 * s0 <= s <= 1.33 * s0) or abs(th) > math.radians(12):
            return 10.0
        q = transform_points(pts, s, th, tx, ty, pc) - [rx0, ry0]
        qx = np.clip(q[:, 0], 0, dist.shape[1] - 1)
        qy = np.clip(q[:, 1], 0, dist.shape[0] - 1)
        outside = (q[:, 0] < 0) | (q[:, 1] < 0) | (q[:, 0] > dist.shape[1] - 1) | (q[:, 1] > dist.shape[0] - 1)
        d = bilinear(dist, qy, qx)
        d[outside] = TRUNC
        line = float(d.mean()) / TRUNC
        q = transform_points(cpts, s, th, tx, ty, pc) - [rx0, ry0]
        inside = (q[:, 0] >= 0) & (q[:, 1] >= 0) & (q[:, 0] < W - 1) & (q[:, 1] < H - 1)
        diff = np.ones(len(q))
        if inside.any():
            qq = q[inside]
            col = np.stack([bilinear(regw[..., c], qq[:, 1], qq[:, 0]) for c in range(3)], 1)
            diff[inside] = np.minimum(np.abs(col - ccol[inside]).sum(1) / 0.6, 1.0)
        return line + COLOR_W * float(diff.mean())

    c0 = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    # 粗い探索 → 細かい最適化
    best = None
    for ds in np.linspace(0.8, 1.2, 9):
        for th in np.radians([-6, -3, 0, 3, 6]):
            for dx in np.linspace(-0.15, 0.15, 7) * bw:
                for dy in np.linspace(-0.15, 0.15, 7) * bh:
                    p = (s0 * ds, th, c0[0] + dx, c0[1] + dy)
                    c = cost(p)
                    if best is None or c < best[0]:
                        best = (c, p)
    if '--fixed' in args:
        fs, fr, fx, fy = [float(v) for v in args[args.index('--fixed') + 1].split(',')]
        s, th, tx, ty, final = fs, math.radians(fr), fx, fy, cost((fs, math.radians(fr), fx, fy))
    else:
      (s, th, tx, ty), final = nelder_mead(cost, best[1], [0.02 * s0, 0.02, 4.0, 4.0])

    # 置く：キャンバスの各画素 → パーツの画素（逆変換）で、双線形補間
    ct, st = math.cos(th), math.sin(th)
    corners = transform_points(np.array([[pb[0] - 4, pb[1] - 4], [pb[2] + 4, pb[1] - 4], [pb[0] - 4, pb[3] + 4], [pb[2] + 4, pb[3] + 4]], float), s, th, tx, ty, pc)
    X0, Y0 = np.floor(corners.min(0)).astype(int)
    X1, Y1 = np.ceil(corners.max(0)).astype(int)
    X0, Y0 = max(X0, 0), max(Y0, 0)
    X1, Y1 = min(X1, CANVAS[0]), min(Y1, CANVAS[1])
    gy, gx = np.mgrid[Y0:Y1, X0:X1].astype(np.float64)
    x = gx - tx
    y = gy - ty
    u = (x * ct + y * st) / s + pc[0]
    v = (-x * st + y * ct) / s + pc[1]
    canvas = np.zeros((CANVAS[1], CANVAS[0], 4), np.float32)
    # premultiplied で補間（縁の色にじみを防ぐ）
    pm = part.copy()
    pm[..., :3] *= pm[..., 3:4]
    for ch in range(4):
        canvas[Y0:Y1, X0:X1, ch] = bilinear(pm[..., ch], v, u)
    a = canvas[..., 3:4]
    canvas[..., :3] = np.where(a > 1e-4, canvas[..., :3] / np.maximum(a, 1e-4), 0)
    Image.fromarray((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8)).save(out)

    # 確認図：基準画像（薄く）の上に、パーツの線を赤で
    view = base[ry0:ry1, rx0:rx1].copy()
    lum = luminance(view)
    rgb = np.repeat(lum[..., None], 3, -1) * 0.6 + 0.4
    q = transform_points(pts, s, th, tx, ty, pc) - [rx0, ry0]
    ok = (q[:, 0] >= 0) & (q[:, 1] >= 0) & (q[:, 0] < rgb.shape[1] - 1) & (q[:, 1] < rgb.shape[0] - 1)
    qi = q[ok].astype(int)
    rgb[qi[:, 1], qi[:, 0]] = [1, 0, 0]
    Image.fromarray((rgb * 255).astype(np.uint8)).save(os.path.splitext(out)[0] + '.check.png')

    info = dict(part=part_path, box=box, scale=s, rotation_deg=math.degrees(th), center=[tx, ty],
                part_center=pc.tolist(), mean_line_distance_px=final, trunc=TRUNC,
                placed_bbox=[int(X0), int(Y0), int(X1), int(Y1)])
    json.dump(info, open(os.path.splitext(out)[0] + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('REGISTER_PART_DONE scale=%.3f rot=%.2f center=(%.1f,%.1f) dist=%.2f' % (s, math.degrees(th), tx, ty, final))


if __name__ == '__main__':
    main()
