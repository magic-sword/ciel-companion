# -*- coding: utf-8 -*-
"""体（Body_Base）の首の上側（顔の下に隠れ、上を向くと見える面）を、明るい白磁の肌にする。

お手本の上向きでは、顎の下から首が明るく、顎の直下にだけ淡い影がある。v5 の体の首の上側は、
灰紫の一色（約 (222,218,232)）で、上を向くと顎の下が暗い板に見えた。首輪より上の首の範囲を、上ほど明るくする。
入力・出力  assets/ciel/layers/body/Body_Base.png（書き換える）
実行  python -I scripts/live2d/lighten-neck.py（install-v5-parts.ps1 の後）   完了表示 NECK_LIGHTENED
"""
import os

import numpy as np
from PIL import Image

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'layers', 'body', 'Body_Base.png')
TOP, BOTTOM = 1160, 1420     # 明るくする高さの範囲（BOTTOM は顎の先より少し下。そこから下は元のまま）
X0, X1 = 940, 1300           # 首の左右の範囲
LIGHT = np.array([246.0, 243.0, 248.0])
AMOUNT = 0.7                 # 上端での、明るい色への寄せ具合


def main():
    im = np.asarray(Image.open(PATH).convert('RGBA')).astype(np.float32)
    h, w = im.shape[:2]
    ys = np.arange(h, dtype=np.float32)[:, None]
    xs = np.arange(w, dtype=np.float32)[None, :]
    t = np.clip((BOTTOM - ys) / (BOTTOM - TOP), 0, 1)          # 上ほど 1
    t = t * t * (3 - 2 * t)
    side = np.clip(np.minimum(xs - X0, X1 - xs) / 40.0, 0, 1)  # 左右の端はなだらかに
    k = (AMOUNT * t * side)[..., None]
    k = k * (im[..., 3:4] > 0)
    im[..., :3] = im[..., :3] * (1 - k) + LIGHT * k
    Image.fromarray(np.clip(im, 0, 255).astype(np.uint8), 'RGBA').save(PATH)
    print('NECK_LIGHTENED')


if __name__ == '__main__':
    main()
