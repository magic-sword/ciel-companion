# -*- coding: utf-8 -*-
"""顔の肌（Face_Skin）の、顎・頬の下側の輪郭線を、別のレイヤー Face_JawLine に分ける。

上を向くと、お手本では顎の輪郭線がほぼ消え、顎の下が首へなめらかにつながる。線を別のレイヤーにして、
角度Y の上向きで不透明度を下げる（add-jaw-line-keys.py）。Face_Skin の側では、線を肌の色に塗り替える（形・不透明度は保つ）。
入力・出力  assets/ciel/layers/head/Face_Skin.png（書き換える）、Face_JawLine.png（新規）
実行  python -I scripts/live2d/split-jaw-line.py（install-v5-parts.ps1 の後）   完了表示 JAW_LINE_SPLIT
"""
import os

import numpy as np
from PIL import Image, ImageFilter

HEAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'layers', 'head')
Y0, Y1 = 1150, 1230   # この高さから下の輪郭線を分ける（間はなだらかに）
EDGE = 7              # 縁から内側へ、この幅までを線とみなす


def main():
    path = os.path.join(HEAD, 'Face_Skin.png')
    im = np.asarray(Image.open(path).convert('RGBA')).astype(np.float32)
    rgb, a = im[..., :3], im[..., 3]
    solid = a > 128
    inner = np.asarray(Image.fromarray((solid * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(2 * EDGE + 1))) > 0
    near_edge = (a > 0) & ~inner
    skin = np.median(rgb[1180:1220, 1060:1150].reshape(-1, 3), axis=0)
    # 線らしさ：肌より暗いほど 1
    dark = np.clip((skin.mean() - rgb.mean(axis=2)) / 60.0, 0, 1)
    ys = np.arange(a.shape[0], dtype=np.float32)[:, None]
    zone = np.clip((ys - Y0) / (Y1 - Y0), 0, 1)
    take = dark * near_edge * zone
    line = np.zeros_like(im)
    line[..., :3] = rgb
    line[..., 3] = a * take
    out = im.copy()
    out[..., :3] = rgb * (1 - take[..., None]) + skin * take[..., None]
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), 'RGBA').save(path)
    Image.fromarray(np.clip(line, 0, 255).astype(np.uint8), 'RGBA').save(os.path.join(HEAD, 'Face_JawLine.png'))
    print('line bbox', Image.open(os.path.join(HEAD, 'Face_JawLine.png')).getchannel('A').getbbox(), 'skin', skin)
    print('JAW_LINE_SPLIT')


if __name__ == '__main__':
    main()
