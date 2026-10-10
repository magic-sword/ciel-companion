# -*- coding: utf-8 -*-
"""顎の裏（Chin_Under）の絵を、顔の肌の輪郭と首の輪郭から作る。

形：上の縁は、顔の肌（Face_Skin）の顎・頬の下側の輪郭より INSET px 内側（正面で顔に隠れる）。横幅は頬から頬まで。
下側は、左右の端から首の左右の輪郭へ、なめらかな曲線で細くなり、首の中へ入って、首の色の中で消える。
色：首（Body_Base）の、顎のすぐ下の陰の色を採って塗る。上の縁（顎の側）へ向かって、わずかに暗い。輪郭線は描かない。
入力  assets/ciel/generated/v5/parts/Face_Skin.png、Body_Base.png
出力  assets/ciel/generated/v5/parts/Chin_Under.png（install-v5-parts.ps1 で layers/head へ）
実行  python -I scripts/live2d/make-chin-under.py   完了表示 CHIN_UNDER_MADE
"""
import os

import numpy as np
from PIL import Image, ImageFilter

PARTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'generated', 'v5', 'parts')
INSET = 12           # 顔の輪郭より内側へ
TOP_Y = 1180         # この高さより下の、顔の下側の輪郭を使う（頬の下〜顎）
NECK_Y = 1420        # 首の左右の輪郭を測る高さ（顎の先より下）
DEPTH_INTO_NECK = 160   # 首の中へ入れる長さ（顎の先から下へ）
FADE = 70            # 下の端を消す幅
DARKEN = 0.06        # 上の縁の側を暗くする割合


def main():
    face = np.asarray(Image.open(os.path.join(PARTS, 'Face_Skin.png')).convert('RGBA'))[..., 3] > 128
    body = np.asarray(Image.open(os.path.join(PARTS, 'Body_Base.png')).convert('RGBA')).astype(np.float32)
    h, w = face.shape
    inner = np.asarray(Image.fromarray((face * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(2 * INSET + 1))) > 0

    # 顔の下側の輪郭（列ごとの、顔のいちばん下の y）
    cols = np.where(face[TOP_Y:].any(axis=0))[0]
    bottom = np.full(w, -1)
    for x in cols:
        bottom[x] = TOP_Y + np.nonzero(face[TOP_Y:, x])[0].max()
    x0, x1 = cols.min(), cols.max()
    chin_y = bottom[x0:x1 + 1].max()
    # 首の左右の輪郭
    row = body[NECK_Y, :, 3] > 128
    neck_cols = np.nonzero(row[900:1300])[0] + 900
    nl, nr = neck_cols.min(), neck_cols.max()
    end_y = chin_y + DEPTH_INTO_NECK

    # 形：顔の内側（上の部分）＋ 顔の下側の輪郭から、首の左右へ曲線で細くなる部分
    mask = np.zeros((h, w), np.float32)
    mask[TOP_Y:, :] = inner[TOP_Y:, :]
    ys = np.arange(h)[:, None]
    xs = np.arange(w)[None, :]
    for y in range(TOP_Y, end_y):
        t = np.clip((y - TOP_Y) / float(end_y - TOP_Y), 0, 1)
        e = t * t * (3 - 2 * t)
        left = x0 + INSET + (nl + 6 - (x0 + INSET)) * e
        right = x1 - INSET + (nr - 6 - (x1 - INSET)) * e
        top = np.where(bottom >= 0, bottom - INSET, y)
        span = (xs[0] >= left) & (xs[0] <= right) & (y >= top - 400)
        mask[y, span] = 1.0
    # 下の端は、なだらかに消す
    fade = np.clip((end_y - ys) / float(FADE), 0, 1)
    mask = mask * fade
    mask[:TOP_Y - 200] = 0
    mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5))).astype(np.float32) / 255

    # 色：首の、顎のすぐ下の陰の色（中央の帯の中央値）。上の縁へ向かってわずかに暗く
    shade = np.median(body[chin_y + 10:chin_y + 60, 1060:1150, :3].reshape(-1, 3), axis=0)
    out = np.zeros((h, w, 4), np.float32)
    k = np.clip((end_y - ys) / float(end_y - TOP_Y), 0, 1)
    out[..., :3] = shade[None, None, :] * (1.0 - DARKEN * k[..., None])
    out[..., 3] = 255 * mask
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), 'RGBA').save(os.path.join(PARTS, 'Chin_Under.png'))
    print('face x %d-%d chin_y %d neck %d-%d end %d shade %s' % (x0, x1, chin_y, nl, nr, end_y, shade.round()))
    print('CHIN_UNDER_MADE')


if __name__ == '__main__':
    main()
