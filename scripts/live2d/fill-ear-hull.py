"""耳のレイヤーの欠けた部分（耳の内側の白い面）を、基準画像から補う。

build-ear-layers.py は、依頼E との差が大きい所（毛のふさ）と、切り抜きの上にはみ出した所だけを耳にしているので、
耳の背の白い面が、切り抜きの上端（y=236）で横一直線に切れて、その下が抜けてしまう。
きれいにした Ear_R / Ear_L（clean-ear-layers.py の後）の凸包の中にある、基準画像の不透明な画素を耳に加える。
入力・出力  assets/ciel/layers/head/{Ear_R,Ear_L}.png（書き換える）
実行  python -I scripts/live2d/fill-ear-hull.py   完了表示 EAR_HULL_FILLED
"""
import os

import numpy as np
from PIL import Image, ImageDraw

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel')
STEP = 6   # 外周の点を間引く間隔（画素）


def hull(points):
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def main():
    master = np.asarray(Image.open(os.path.join(ASSETS, 'master', 'ciel-upper-body-2x.png')).convert('RGBA'))
    for name in ('Ear_R', 'Ear_L'):
        path = os.path.join(ASSETS, 'layers', 'head', name + '.png')
        im = np.asarray(Image.open(path).convert('RGBA')).copy()
        solid = im[..., 3] > 8
        ys, xs = np.nonzero(solid[::STEP, ::STEP])
        poly = hull(list(zip((xs * STEP).tolist(), (ys * STEP).tolist())))
        m = Image.new('L', (im.shape[1], im.shape[0]), 0)
        ImageDraw.Draw(m).polygon(poly, fill=255)
        inside = (np.asarray(m) > 0) & (master[..., 3] > 8)
        add = inside & (im[..., 3] < 250)
        im[add] = master[add]
        Image.fromarray(im, 'RGBA').save(path)
        print(name, 'added px', int(add.sum()))
    print('EAR_HULL_FILLED')


if __name__ == '__main__':
    main()
