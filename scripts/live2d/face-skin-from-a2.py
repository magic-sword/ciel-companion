# -*- coding: utf-8 -*-
"""Face_Skin の土台を、A2（顔〜首の素肌ベース。なめらかな輪郭と顎の線つき）の顔の部分にする。

元の Face_Skin は、顎の線を持たず（線は動かない Body_Base に描かれていた）、下端がぎざぎざだった。
上を向くと、顔は上へ動くのに顎の線は元の位置に残り、顔の下端が輪郭のない波打った形に見えていた。
ここでは、A2 の顔の部分を土台に敷き、その上に、元の Face_Skin の内側（鼻・口元・頬の陰影・髪の影）を重ねる。
画像は、Face_Skin のメッシュの範囲（MESH_BOX）に切り詰める（メッシュの外は描かれない）。

入力  assets/ciel/layers/head/Face_Skin.pre-a2.png（元の Face_Skin。初回に Face_Skin.png から退避）
      assets/ciel/generated/v4/A2_line_ref.png、A2_face-shape-mask.png
出力  assets/ciel/layers/head/Face_Skin.png（書き換える）
実行  python -I scripts/live2d/face-skin-from-a2.py   完了表示 FACE_SKIN_FROM_A2
"""
import os
import shutil

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..', 'assets', 'ciel')
FACE = os.path.join(ROOT, 'layers', 'head', 'Face_Skin.png')
V4 = os.path.join(ROOT, 'generated', 'v4')
INNER = 14   # 元の Face_Skin の縁を、この幅だけ内側へ削ってから重ねる（ぎざぎざの縁を使わない）
FADE = 10    # 削った縁から内側へ、この幅で、なだらかに元の絵へ移る
LINE_GROW = 7   # 見える輪郭のマスクを太らせる幅（奇数。線の幅 約 3px を含める）
MESH_BOX =(720, 484, 1474, 1390)   # Face_Skin のメッシュの範囲（ciel-blink-test.cmo3 の point の最小・最大。画像座標）


def main():
    pre = FACE.replace('.png', '.pre-a2.png')
    if not os.path.exists(pre):
        shutil.copy(FACE, pre)
    orig = Image.open(pre).convert('RGBA')
    box = MESH_BOX

    a2 = np.asarray(Image.open(os.path.join(V4, 'A2_line_ref.png')).convert('RGBA')).astype(np.float32)
    face = np.asarray(Image.open(os.path.join(V4, 'A2_face-shape-mask.png')).convert('L')).astype(np.float32) / 255
    # 顔の形のマスクは、輪郭線のすぐ内側で終わる。見える輪郭のマスクを太らせて足し、顎・頬の線も含める
    line = Image.open(os.path.join(V4, 'A2_visible-contour-mask.png')).convert('L').filter(ImageFilter.MaxFilter(LINE_GROW))
    face = np.maximum(face, np.asarray(line).astype(np.float32) / 255)
    base = a2.copy()
    base[..., 3] *= face

    # 元の Face_Skin の内側だけを、なだらかな縁で重ねる
    oa = np.asarray(orig.getchannel('A'))
    inner = Image.fromarray(((oa > 128) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(2 * INNER + 1))
    inner = np.asarray(inner.filter(ImageFilter.GaussianBlur(FADE / 2))).astype(np.float32) / 255
    top = np.asarray(orig).astype(np.float32)
    top[..., 3] *= inner

    out = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), 'RGBA')
    out.alpha_composite(Image.fromarray(np.clip(top, 0, 255).astype(np.uint8), 'RGBA'))

    # メッシュの範囲の外は消す
    arr = np.asarray(out).copy()
    mask = np.zeros(arr.shape[:2], bool)
    mask[box[1]:box[3], box[0]:box[2]] = True
    arr[~mask] = 0
    Image.fromarray(arr, 'RGBA').save(FACE)
    print('bbox', Image.fromarray(arr, 'RGBA').getchannel('A').getbbox(), 'mesh', box)
    print('FACE_SKIN_FROM_A2')


if __name__ == '__main__':
    main()
