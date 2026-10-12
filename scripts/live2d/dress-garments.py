# -*- coding: utf-8 -*-
"""1 つの物として描いた上着と首輪を、前と後ろに切り分けて、シエルに着せる（v16）。

絵そのものには手を加えない（画素を描き足さない）。行うのは、マスクで前後に分けることだけ。
- 体（Body）：胴の範囲（胴の輪郭線の内側）を、中心から外へ向かって最初の濃い輪郭線までとして行ごとに求める。
- 上着：Jacket_Back＝上着の全体（体の後ろ）。Jacket_Front＝上着から「胴の範囲」と「肩より上の裏地（シアン）」を除いたもの
  （体の前。袖と肩のファー、胴の脇の裏地が、体の腕を覆う）。
- 首輪：Choker_Back＝輪の奥側（輪の穴より上の部分。首の後ろ）。Choker_Front＝それ以外（首の前の帯・金具・飾り）。

実行  python -I scripts/live2d/dress-garments.py 置いた服のフォルダ 出力フォルダ
入力  <置いた服のフォルダ>/{Body,Jacket,Choker}.png（キャンバス 2172×2896）
出力  Body.png（そのまま）、Jacket_Back.png、Jacket_Front.png、Choker_Back.png、Choker_Front.png、_masks.png（確認用）
"""
import os
import sys

import numpy as np
from PIL import Image


def load(p):
    return np.asarray(Image.open(p).convert('RGBA')).astype(np.float32)


def save(a, p):
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA').save(p)


def torso_span(body):
    """行ごとの胴の範囲。体の絵は、胴の両脇に腕が描かれている。外側から内側へ見て、
    腕の外側の輪郭線 → 腕の肌 → 胴と腕の境の輪郭線、の順に並ぶので、2 本目の線（または腕と胴の間の透明）の内側を胴とする。
    見つからない行は、上下の行から補う。"""
    a = body[..., 3] > 128
    dark = a & (body[..., :3].mean(-1) < 170)
    H, W = a.shape
    ys, xs = np.nonzero(a)
    cx = int(np.median(xs))
    bounds = {}

    def inner_edge(row_a, row_d, xs_):
        # xs_：外側から中心へ向かう x の並び
        state = 0   # 0: 外の透明, 1: 外側の線, 2: 腕の中, 3: 境の線
        for x in xs_:
            if state == 0:
                if row_a[x]:
                    state = 1 if row_d[x] else 2
            elif state == 1:
                if not row_a[x]:
                    state = 0
                elif not row_d[x]:
                    state = 2
            elif state == 2:
                if not row_a[x]:      # 腕と胴の間の透明
                    state = 4
                elif row_d[x]:
                    return x
            elif state == 4:
                if row_a[x]:
                    return x
            if abs(x - cx) < 60:
                return None
        return None

    for y in range(ys.min(), ys.max() + 1):
        l = inner_edge(a[y], dark[y], range(0, cx))
        r = inner_edge(a[y], dark[y], range(W - 1, cx, -1))
        if l is not None and r is not None:
            bounds[y] = (l, r)
    rows = sorted(bounds)
    mask = np.zeros_like(a)
    if not rows:
        return mask
    Ls = np.interp(np.arange(rows[0], rows[-1] + 1), rows, [bounds[y][0] for y in rows])
    Rs = np.interp(np.arange(rows[0], rows[-1] + 1), rows, [bounds[y][1] for y in rows])
    k = 9
    Ls = np.array([np.median(Ls[max(0, i - k):i + k + 1]) for i in range(len(Ls))])
    Rs = np.array([np.median(Rs[max(0, i - k):i + k + 1]) for i in range(len(Rs))])
    for i, y in enumerate(range(rows[0], rows[-1] + 1)):
        mask[y, int(Ls[i]):int(Rs[i]) + 1] = True
    # 見つかった行より下（腰・スカート）は、最後の行の範囲のまま体の下端まで
    for y in range(rows[-1] + 1, ys.max() + 1):
        mask[y, int(Ls[-1]):int(Rs[-1]) + 1] = True
    return mask & a


def main():
    src, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    body = load(os.path.join(src, 'Body.png'))
    jacket = load(os.path.join(src, 'Jacket.png'))
    choker = load(os.path.join(src, 'Choker.png'))

    a = body[..., 3] > 128
    torso = torso_span(body)
    rows = np.nonzero(torso.any(1))[0]

    ja = jacket[..., 3] > 8
    r, g, b = jacket[..., 0], jacket[..., 1], jacket[..., 2]
    lining = ja & (b > 180) & (g > 140) & (r < 140)
    # 腋の高さ：胴の幅が最も狭くなる行より上を「肩より上」とする（胸の上の裏地は後ろ）
    armpit = int(np.percentile(rows, 30))
    top_lining = lining.copy()
    top_lining[armpit:] = False
    front = ja & ~torso & ~top_lining
    jf = jacket.copy()
    jf[..., 3] *= front
    save(jacket, os.path.join(out, 'Jacket_Back.png'))
    save(jf, os.path.join(out, 'Jacket_Front.png'))

    # 首輪：輪の穴（透明）より上を奥側
    ca = choker[..., 3] > 8
    cys, cxs = np.nonzero(ca)
    x0, x1, y0, y1 = cxs.min(), cxs.max(), cys.min(), cys.max()
    back = np.zeros_like(ca)
    for x in range(x0, x1 + 1):
        col = ca[y0:y1 + 1, x]
        ys_ = np.nonzero(col)[0]
        if len(ys_) == 0:
            continue
        # 列の中で、上から見て最初の不透明の塊の後に透明があり、その後また不透明になる → 最初の塊が奥側
        first_end = None
        for i in range(ys_[0], len(col)):
            if not col[i]:
                first_end = i
                break
        if first_end is not None and col[first_end:].any():
            back[y0 + ys_[0]:y0 + first_end, x] = True
    cb = choker.copy()
    cb[..., 3] *= back
    cf = choker.copy()
    cf[..., 3] *= ~back
    save(cb, os.path.join(out, 'Choker_Back.png'))
    save(cf, os.path.join(out, 'Choker_Front.png'))
    save(body, os.path.join(out, 'Body.png'))

    vis = np.zeros(body.shape[:2] + (3,), np.uint8)
    vis[a] = (90, 90, 90)
    vis[torso] = (200, 200, 200)
    vis[front] = (255, 120, 0)
    vis[ja & ~front] = (0, 120, 255)
    vis[back] = (255, 0, 255)
    Image.fromarray(vis).resize((543, 724)).save(os.path.join(out, '_masks.png'))
    print('DRESS_GARMENTS_DONE armpit_y=%d' % armpit)


if __name__ == '__main__':
    main()
