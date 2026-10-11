# -*- coding: utf-8 -*-
"""パーツ単体を Codex に描かせるための枠（2 倍の元の絵からの切り抜き）を作る（計画書 8.2）。

枠は、パーツの範囲（`layers/v7/canvas/<名前>.png` の不透明な範囲）に、描き足しのための余白を足し、
Codex の出力の縦横比（1:1・2:3・3:2・3:4・4:3・1:3・3:1）のうち近いものへ広げる。
出力は `generated/v8/frames/<名前>.png`（白背景、元の画素の大きさ）と `generated/v8/frames.json`（キャンバス上の枠）。
実行  python -I scripts/live2d/make-iso-frames.py
"""
import json
import os

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
CANVAS = os.path.join(ROOT, 'assets', 'ciel', 'layers', 'v7', 'canvas')
OUT = os.path.join(ROOT, 'assets', 'ciel', 'generated', 'v8')
MASTER = os.path.join(ROOT, 'assets', 'ciel', 'master', 'ciel-upper-body-2x.png')
RATIOS = [1.0, 2 / 3, 3 / 2, 3 / 4, 4 / 3, 1 / 3, 3.0]   # 幅 / 高さ
PARTS = {  # 名前: 余白（パーツの大きさに対する割合。描き足しが大きいものは広く）
    'Hair_Front': 0.15, 'Brow_R': 0.6, 'Brow_L': 0.6, 'Hair_Side_R': 0.12, 'Hair_Side_L': 0.12,
    'Hair_Ahoge': 0.2, 'Ear_R': 0.2, 'Ear_L': 0.2, 'Eye_R': 0.35, 'Eye_L': 0.35, 'Mouth': 1.2, 'Nose': 4.0,
    'Face_Skin': 0.15, 'Choker': 0.3, 'Neck': 0.6, 'Outer_R': 0.08, 'Outer_L': 0.08, 'Body': 0.06, 'Hair_Back': 0.04,
}


def main():
    os.makedirs(os.path.join(OUT, 'frames'), exist_ok=True)
    m = Image.open(MASTER).convert('RGBA')
    white = Image.new('RGBA', m.size, (255, 255, 255, 255))
    white.alpha_composite(m)
    W, H = m.size
    frames = {}
    for name, pad in PARTS.items():
        a = np.asarray(Image.open(os.path.join(CANVAS, name + '.png')))[..., 3]
        ys, xs = np.nonzero(a > 16)
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        w, h = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = w * (1 + 2 * pad), h * (1 + 2 * pad)
        r = min(RATIOS, key=lambda q: abs(np.log((w / h) / q)))
        if w / h < r:
            w = h * r
        else:
            h = w / r
        box = [int(round(cx - w / 2)), int(round(cy - h / 2)), int(round(cx + w / 2)), int(round(cy + h / 2))]
        frames[name] = dict(box=box, ratio=round(r, 4))
        # キャンバスの外は白で埋める
        crop = Image.new('RGB', (box[2] - box[0], box[3] - box[1]), (255, 255, 255))
        sx0, sy0 = max(0, box[0]), max(0, box[1])
        sx1, sy1 = min(W, box[2]), min(H, box[3])
        crop.paste(white.crop((sx0, sy0, sx1, sy1)).convert('RGB'), (sx0 - box[0], sy0 - box[1]))
        crop.save(os.path.join(OUT, 'frames', name + '.png'))
        print('%-12s box=%s ratio=%.3f size=%dx%d' % (name, box, r, crop.width, crop.height))
    json.dump(frames, open(os.path.join(OUT, 'frames.json'), 'w', encoding='utf-8'), indent=1)


if __name__ == '__main__':
    main()
