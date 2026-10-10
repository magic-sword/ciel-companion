# -*- coding: utf-8 -*-
"""Face_Skin の土台を、A2（顔〜首の素肌ベース。なめらかな輪郭と顎の線つき）の顔の部分にする。

元の Face_Skin は、顎の線を持たず（線は動かない Body_Base に描かれていた）、下端がぎざぎざだった。
上を向くと、顔は上へ動くのに顎の線は元の位置に残り、顔の下端が輪郭のない波打った形に見えていた。
ここでは、A2 の顔の部分を土台に敷き、その上に、元の Face_Skin の内側（鼻・口元・頬の陰影・髪の影）を重ねる。
画像は、Face_Skin のメッシュの範囲（MESH_BOX）に切り詰める（メッシュの外は描かれない）。

入力  assets/ciel/layers/head/Face_Skin.pre-a2.png（元の Face_Skin。初回に Face_Skin.png から退避）
      assets/ciel/generated/v4/A2_line_ref.png、A2_face-shape-mask.png
出力  assets/ciel/layers/head/Face_Skin.png（書き換える）
      assets/ciel/layers/head/Face_Base.png（顎の線だけのレイヤー。上を向くと消す。jaw-line-mesh.py で組み込む）
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
JAW_LINE = os.path.join(ROOT, 'layers', 'head', 'Face_Base.png')   # 顎の線のレイヤー（メッシュ名は Face_Base のまま）
JAW_LINE_Y0, JAW_LINE_Y1 = 1180.0, 1280.0   # この高さから下の線を、顎の線のレイヤーへ移す（間はなだらかに）
LINE_RGB = np.array([117.0, 102.0, 120.0])   # 基準画像の顎の線の色（Codex の測定の中央値）
INNER_JAW = 45   # 顎の付近で、元の Face_Skin の縁を削る幅（元の顎の線の切れ端を使わない）
LINE_GROW = 7 # 見える輪郭のマスクを太らせる幅（奇数。線の幅 約 3px を含める）
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

    # 顎の部分の線は、別のレイヤー（Face_Base.png、角度Y の上向きで消す）へ移す。
    # Face_Skin の側では、その線を肌の色で塗りつぶす（輪郭の形・不透明度は保つ）。
    lm = np.asarray(line).astype(np.float32) / 255
    ys = np.arange(lm.shape[0], dtype=np.float32)[:, None]
    zone = np.clip((ys - JAW_LINE_Y0) / (JAW_LINE_Y1 - JAW_LINE_Y0), 0, 1)
    zone = zone * zone * (3 - 2 * zone)
    take = lm * zone
    skin = np.median(a2[1240:1280, 1060:1150, :3].reshape(-1, 3), axis=0)
    # 線のレイヤーには、線の暗い画素だけを、線の色で入れる（周りの白い肌の縁を入れない）
    lum = a2[..., :3].mean(axis=2)
    dark = np.clip((skin.mean() - lum) / (skin.mean() - LINE_RGB.mean()), 0, 1)
    jaw = np.zeros_like(a2)
    jaw[..., :3] = LINE_RGB
    jaw[..., 3] = a2[..., 3] * take * dark
    base[..., :3] = base[..., :3] * (1 - take[..., None]) + skin * take[..., None]
    # 元の Face_Skin にも、顎の付近に、元の顎の線の切れ端がある。顎の付近では、もっと内側からだけ重ねる
    inner_jaw = Image.fromarray(((oa > 128) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(2 * INNER_JAW + 1))
    inner_jaw = np.asarray(inner_jaw.filter(ImageFilter.GaussianBlur(FADE / 2))).astype(np.float32) / 255
    top[..., 3] = np.asarray(orig).astype(np.float32)[..., 3] * (inner * (1 - zone) + inner_jaw * zone)

    out = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), 'RGBA')
    out.alpha_composite(Image.fromarray(np.clip(top, 0, 255).astype(np.uint8), 'RGBA'))
    Image.fromarray(np.clip(jaw, 0, 255).astype(np.uint8), 'RGBA').save(JAW_LINE)
    print('jaw line bbox', Image.open(JAW_LINE).getchannel('A').getbbox(), 'skin', skin)

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
