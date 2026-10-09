"""Body_Base の上の縁（髪の毛先が横一直線に切れている所）を、上から下へ少しずつ不透明にして、後ろ髪になじませる。

入力・出力  assets/ciel/layers/body/Body_Base.png（書き換える。元は Body_Base.orig.png に退避）
実行  python -I scripts/live2d/soften-body-top.py   完了表示 BODY_TOP_SOFTENED
考え方：列ごとに「最初に不透明になる行」を探し、そこから FADE 行かけて α を 0→元の値へ上げる。
顔の下にかくれる範囲なので、あごの下の首は変わらない。
"""
import os
import shutil

import numpy as np
from PIL import Image

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'layers', 'body', 'Body_Base.png')
FADE = 110
TOP_LIMIT = 1500


def main():
    orig = PATH.replace('.png', '.orig.png')
    if not os.path.exists(orig):
        shutil.copy(PATH, orig)
    im = np.asarray(Image.open(orig).convert('RGBA')).copy()
    a = im[..., 3].astype(float)
    h, w = a.shape
    solid = a > 8
    first = np.where(solid.any(0), solid.argmax(0), h)
    ys = np.arange(h)[:, None]
    ramp = np.clip((ys - first[None, :]) / FADE, 0, 1)
    ramp[:, first >= TOP_LIMIT] = 1.0   # 肩・腕など、下から始まる列は触らない
    im[..., 3] = (a * ramp).astype('uint8')
    Image.fromarray(im, 'RGBA').save(PATH)
    print('BODY_TOP_SOFTENED', int(first[first < h].min()), int(first[first < h].max()))


if __name__ == '__main__':
    main()
