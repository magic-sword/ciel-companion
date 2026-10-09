# -*- coding: utf-8 -*-
"""顎の裏・のど（K-2・K-3）を、Body_Base の画像に焼き込む。

上を向くと、顎が上がり、いまは顔に隠れている首の面が見える。その面を、体のレイヤー（顔より下、動かさない）に、
あらかじめ描いておく。正面では顔が覆うので見えない。
入力・出力  assets/ciel/layers/body/Body_Base.png（書き換える。元は Body_Base.prechin.png に退避）
実行  python -I scripts/live2d/bake-chin-into-body.py   完了表示 CHIN_BAKED
色：K の明るい所（90 パーセンタイル）を (246, 245, 248) に合わせる（陶器の白い肌）。
"""
import os
import shutil

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..', 'assets', 'ciel')
BODY = os.path.join(ROOT, 'layers', 'body', 'Body_Base.png')
UNDER = os.path.join(ROOT, 'generated', 'parts', 'underlayers')
CROP = (318, 236)
TARGET = np.array([246.0, 245.0, 248.0])
EXTRUDE = 230   # 上端の列を、上へ延ばす量（px）。顎が上がったとき、顎と首の間に隙間ができないように


def extrude_up(k):
    """各列の、いちばん上の不透明な画素を、上へ EXTRUDE px 延ばす。"""
    out = k.copy()
    h, w = k.shape[:2]
    solid = k[..., 3] > 200
    for x in range(w):
        col = np.nonzero(solid[:, x])[0]
        if len(col) == 0:
            continue
        top = col[0]
        y0 = max(0, top - EXTRUDE)
        out[y0:top, x, :3] = k[top + 2, x, :3]
        out[y0:top, x, 3] = 255
    # 列ごとの複製で縦縞ができるので、延ばした部分だけ、ぼかして縞を消す
    ext = (out[..., 3] > 0) & ~solid
    blur = np.asarray(Image.fromarray(out[..., :3].astype(np.uint8)).filter(ImageFilter.GaussianBlur(14))).astype(np.float32)
    out[ext, :3] = blur[ext]
    return out


def main():
    pre = BODY.replace('.png', '.prechin.png')
    if not os.path.exists(pre):
        shutil.copy(BODY, pre)
    body = Image.open(pre).convert('RGBA')
    for name in ('K-2_chin-throat_x0_yU15.png', 'K-3_chin-throat_x0_yU30.png'):
        k = np.asarray(Image.open(os.path.join(UNDER, name)).convert('RGBA')).astype(np.float32)
        solid = k[..., 3] > 200
        p90 = np.percentile(k[solid][:, :3], 90, axis=0)
        k[..., :3] = np.clip(k[..., :3] * (TARGET / p90), 0, 255)
        k = extrude_up(k)
        a = Image.fromarray(k[..., 3].astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
        k[..., 3] = np.asarray(a)
        layer = Image.new('RGBA', body.size, (0, 0, 0, 0))
        layer.paste(Image.fromarray(k.astype(np.uint8), 'RGBA'), CROP)
        body.alpha_composite(layer)
    body.save(BODY)
    print('CHIN_BAKED')


if __name__ == '__main__':
    main()
