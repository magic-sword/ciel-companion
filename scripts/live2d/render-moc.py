# -*- coding: utf-8 -*-
"""書き出したモデル（.model3.json と .moc3・テクスチャ）を、Cubism Core の計算で描く。

Unity を起動せずに、数秒で向き・表情を確かめるための道具。頂点・不透明度・描画順・クリッピングは Core が計算したものを使い、
三角形の塗りだけを numpy で行う（テクスチャは双線形補間、通常・加算・乗算の合成）。

実行  python -I scripts/live2d/render-moc.py モデル.model3.json 出力.png [オプション] [ID=値 ...]
      ID=値 は 1 回分のパラメーター。複数の向きを並べるときは、";" で区切る（例 "ParamAngleX=30;ParamAngleX=-30"）。
オプション
  --scale S      描く倍率（キャンバスの画素に対して。既定 0.25）
  --crop x0,y0,x1,y1  キャンバスの画素での切り出し（既定は全体）
  --bg r,g,b     背景色（既定 64,72,104）
  --cols N       並べるときの列数
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cubism_core as cc


def load_textures(model):
    return [np.asarray(Image.open(p).convert('RGBA')).astype(np.float32) / 255.0 for p in model.textures]


def sample(tex, u, v):
    """テクスチャ（H×W×4、straight alpha）を、uv（0〜1、v は上向き）で双線形補間。premultiplied で返す。"""
    h, w = tex.shape[:2]
    x = np.clip(u * w - 0.5, 0, w - 1)
    y = np.clip((1.0 - v) * h - 0.5, 0, h - 1)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0)[:, None]
    fy = (y - y0)[:, None]

    def pm(yy, xx):
        c = tex[yy, xx]
        return np.concatenate([c[:, :3] * c[:, 3:4], c[:, 3:4]], 1)
    return (pm(y0, x0) * (1 - fx) * (1 - fy) + pm(y0, x1) * fx * (1 - fy)
            + pm(y1, x0) * (1 - fx) * fy + pm(y1, x1) * fx * fy)


def raster(d, tex, W, H, scale, off):
    """1 メッシュを、premultiplied RGBA の画像（H×W×4）へ塗る。塗った範囲の画像を返す。"""
    out = np.zeros((H, W, 4), np.float32)
    pos = (d['pos'] - off) * scale
    uv = d['uv']
    tri = d['tri']
    # 三角形の番号を塗った画像（0 は無し）。PIL の多角形塗りは C で速い
    idimg = Image.new('I', (W, H), 0)
    dr = ImageDraw.Draw(idimg)
    for k, (a, b, c) in enumerate(tri):
        dr.polygon([tuple(pos[a]), tuple(pos[b]), tuple(pos[c])], fill=k + 1)
    ids = np.asarray(idimg)
    yy, xx = np.nonzero(ids)
    if len(yy) == 0:
        return out
    t = tri[ids[yy, xx] - 1]
    p0, p1, p2 = pos[t[:, 0]], pos[t[:, 1]], pos[t[:, 2]]
    px = xx + 0.5
    py = yy + 0.5
    den = (p1[:, 1] - p2[:, 1]) * (p0[:, 0] - p2[:, 0]) + (p2[:, 0] - p1[:, 0]) * (p0[:, 1] - p2[:, 1])
    den = np.where(np.abs(den) < 1e-9, 1e-9, den)
    w0 = ((p1[:, 1] - p2[:, 1]) * (px - p2[:, 0]) + (p2[:, 0] - p1[:, 0]) * (py - p2[:, 1])) / den
    w1 = ((p2[:, 1] - p0[:, 1]) * (px - p2[:, 0]) + (p0[:, 0] - p2[:, 0]) * (py - p2[:, 1])) / den
    w0 = np.clip(w0, 0, 1)
    w1 = np.clip(w1, 0, 1 - w0)
    w2 = 1.0 - w0 - w1
    u = w0 * uv[t[:, 0], 0] + w1 * uv[t[:, 1], 0] + w2 * uv[t[:, 2], 0]
    v = w0 * uv[t[:, 0], 1] + w1 * uv[t[:, 1], 1] + w2 * uv[t[:, 2], 1]
    out[yy, xx] = sample(tex, u, v)
    return out


def raster_slow(d, tex, W, H, scale, off):
    """三角形ごとに塗る、遅いが素直な版（検算用）。"""
    out = np.zeros((H, W, 4), np.float32)
    pos = (d['pos'] - off) * scale
    uv = d['uv']
    for a, b, c in d['tri']:
        p0, p1, p2 = pos[a], pos[b], pos[c]
        xmin = max(int(np.floor(min(p0[0], p1[0], p2[0]))), 0)
        xmax = min(int(np.ceil(max(p0[0], p1[0], p2[0]))), W - 1)
        ymin = max(int(np.floor(min(p0[1], p1[1], p2[1]))), 0)
        ymax = min(int(np.ceil(max(p0[1], p1[1], p2[1]))), H - 1)
        if xmin > xmax or ymin > ymax:
            continue
        den = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
        if abs(den) < 1e-9:
            continue
        ys, xs = np.mgrid[ymin:ymax + 1, xmin:xmax + 1]
        px = xs.ravel() + 0.5
        py = ys.ravel() + 0.5
        w0 = ((p1[1] - p2[1]) * (px - p2[0]) + (p2[0] - p1[0]) * (py - p2[1])) / den
        w1 = ((p2[1] - p0[1]) * (px - p2[0]) + (p0[0] - p2[0]) * (py - p2[1])) / den
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        w0, w1, w2 = w0[inside], w1[inside], w2[inside]
        u = w0 * uv[a, 0] + w1 * uv[b, 0] + w2 * uv[c, 0]
        v = w0 * uv[a, 1] + w1 * uv[b, 1] + w2 * uv[c, 1]
        col = sample(tex, u, v)
        yy = ys.ravel()[inside]
        xx = xs.ravel()[inside]
        # 三角形どうしが重なる所は、後の三角形で上書き（Cubism と同じく、1 メッシュの中では合成しない扱いに近い）
        out[yy, xx] = col
    return out


def render(model, textures, scale=0.25, crop=None, bg=(64, 72, 104)):
    cw, ch = model.canvas
    x0, y0, x1, y1 = crop if crop else (0, 0, cw, ch)
    W = int(round((x1 - x0) * scale))
    H = int(round((y1 - y0) * scale))
    off = np.array([x0, y0], np.float64)
    ds = model.drawables()
    img = np.zeros((H, W, 4), np.float32)
    img[..., :3] = np.array(bg, np.float32) / 255.0
    img[..., 3] = 1.0
    cache = {}

    def layer(i):
        if i not in cache:
            d = ds[i]
            cache[i] = raster(d, textures[d['texture']], W, H, scale, off)
        return cache[i]

    for d in sorted(ds, key=lambda d: d['render_order']):
        if not d['visible'] or d['opacity'] <= 0.001 or len(d['tri']) == 0:
            continue
        src = layer(d['index']).copy()
        if d['masks']:
            cov = np.zeros((H, W), np.float32)
            for mi in d['masks']:
                if mi >= 0:
                    cov = np.maximum(cov, layer(mi)[..., 3])
            if d['inverted_mask']:
                cov = 1.0 - cov
            src *= cov[..., None]
        mulc = np.array(d['multiply'], np.float32)
        scrc = np.array(d['screen'], np.float32)
        a = src[..., 3:4]
        rgb = src[..., :3] * mulc
        rgb = rgb + scrc * a - rgb * scrc
        src = np.concatenate([rgb, a], -1) * d['opacity']
        if d['blend'] == 'add':
            img[..., :3] += src[..., :3]
        elif d['blend'] == 'mul':
            img[..., :3] = img[..., :3] * (src[..., :3] + (1 - src[..., 3:4]))
        else:
            img = src + img * (1 - src[..., 3:4])
    return Image.fromarray((np.clip(img[..., :3], 0, 1) * 255 + 0.5).astype(np.uint8))


def parse_params(s):
    out = {}
    for kv in s.split():
        k, v = kv.split('=')
        out[k] = float(v)
    return out


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    src, dst = args[0], args[1]
    scale, crop, bg, cols = 0.25, None, (64, 72, 104), None
    rest = []
    i = 2
    while i < len(args):
        a = args[i]
        if a == '--scale':
            scale = float(args[i + 1]); i += 2
        elif a == '--crop':
            crop = tuple(float(v) for v in args[i + 1].split(',')); i += 2
        elif a == '--bg':
            bg = tuple(int(v) for v in args[i + 1].split(',')); i += 2
        elif a == '--cols':
            cols = int(args[i + 1]); i += 2
        else:
            rest.append(a); i += 1
    poses = ' '.join(rest).split(';') if rest else ['']
    model = cc.Model(src)
    tex = load_textures(model)
    tiles = []
    for p in poses:
        model.reset()
        miss = model.set(parse_params(p))
        if miss:
            print('NO_SUCH_PARAM', miss)
        model.update()
        tiles.append(render(model, tex, scale, crop, bg))
    cols = cols or len(tiles)
    rows = (len(tiles) + cols - 1) // cols
    w, h = tiles[0].size
    sheet = Image.new('RGB', (w * cols, h * rows), bg)
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * w, (k // cols) * h))
    sheet.save(dst)
    print('RENDER_MOC_DONE', dst, sheet.size)


if __name__ == '__main__':
    main()
