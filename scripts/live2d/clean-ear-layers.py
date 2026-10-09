"""耳のレイヤーから、耳の外にはみ出した小さな切れ端（髪の塊の取り残し）を消す。

入力・出力  assets/ciel/layers/head/{Ear_R,Ear_L}.png（build-ear-layers.py の出力をそのまま書き換える）
実行  python -I scripts/live2d/clean-ear-layers.py   完了表示 EAR_LAYERS_CLEANED
考え方：不透明部分（α>8）を少しふくらませてつなぎ、いちばん大きい塊（耳）だけを残す。
"""
import os

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'layers', 'head')
GROW = 3   # つなぐ距離（MaxFilter の大きさ）
LOWER_FROM = 430   # これより上（耳の先〜中ほど）は開き処理をしない
OPEN = 41  # 耳の本体より細い突起を落とす開き処理の大きさ
SCALE = 4  # 塊の判定は 1/4 に縮めて行う


def largest_component(mask):
    """mask（bool）のうち、いちばん大きい 8 近傍の塊だけを True にして返す（scipy を使わない）。"""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    best, best_n = None, 0
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        stack = [(sy, sx)]
        seen[sy, sx] = True
        cells = []
        while stack:
            y, x = stack.pop()
            cells.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if len(cells) > best_n:
            best, best_n = cells, len(cells)
    out = np.zeros_like(mask)
    ys, xs = zip(*best)
    out[list(ys), list(xs)] = True
    return out, best_n


def clean(name):
    path = os.path.join(ROOT, name + '.png')
    im = Image.open(path).convert('RGBA')
    a = np.asarray(im)[..., 3]
    solid = a > 8
    opened = np.asarray(Image.fromarray((solid * 255).astype('uint8')).filter(ImageFilter.MinFilter(OPEN)).filter(ImageFilter.MaxFilter(OPEN))) > 0
    near = np.asarray(Image.fromarray((opened * 255).astype('uint8')).filter(ImageFilter.MaxFilter(OPEN // 2 + 1))) > 0
    ys_ = np.arange(solid.shape[0])[:, None]
    solid = solid & (near | (ys_ < LOWER_FROM))
    grown = np.asarray(Image.fromarray((solid * 255).astype('uint8')).filter(ImageFilter.MaxFilter(GROW))) > 0
    small = np.asarray(Image.fromarray((grown * 255).astype('uint8')).resize((a.shape[1] // SCALE, a.shape[0] // SCALE), Image.BILINEAR)) > 0
    comp, _ = largest_component(small)
    keep = np.asarray(Image.fromarray((comp * 255).astype('uint8')).resize((a.shape[1], a.shape[0]), Image.NEAREST)) > 0
    out = np.asarray(im).copy()
    out[~(keep & solid), 3] = 0
    Image.fromarray(out, 'RGBA').save(path)
    print(name, 'removed px', int(((np.asarray(im)[..., 3] > 8) & ~(keep & solid)).sum()))


if __name__ == '__main__':
    clean('Ear_R')
    clean('Ear_L')
    print('EAR_LAYERS_CLEANED')
