"""顔の向きの見本（正面・左右15度・左右30度）から、顔の特徴の位置を測る。

入力  assets/ciel/requests/face-hair-crop-1536x1536_x318_y236.png（正面）
      assets/ciel/generated/pose-ref/pose_x{L30,L15,R15,R30}_y0.png（1536x1536。L=画面の左を向く、R=右を向く）
出力  標準出力に、各画像の特徴量を表で出す（assets/ciel/head-turn-measure.json にも保存）
実行  python -I scripts/live2d/measure-head-turn.py

測るもの：虹彩（青い大きな塊）の左右の重心と大きさ、顔の肌の領域（鼻から塗り広げた範囲）の重心と幅、
耳（上部の白い毛と、淡い青の影）の左右の最上端の位置。
見本は全体が描き直されているので、レイヤーには使わず、パーツの動き量を決めるために測る。
"""
import json
import os

import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel')
SAMPLES = [
    ('left30', 'generated/pose-ref/pose_xL30_y0.png', -30),
    ('left15', 'generated/pose-ref/pose_xL15_y0.png', -15),
    ('front', 'requests/face-hair-crop-1536x1536_x318_y236.png', 0),
    ('right15', 'generated/pose-ref/pose_xR15_y0.png', 15),
    ('right30', 'generated/pose-ref/pose_xR30_y0.png', 30),
]


def load(path):
    im = Image.open(os.path.join(ROOT, path)).convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return np.asarray(bg.convert('RGB').resize((1536, 1536), Image.LANCZOS)).astype(float)


def components(mask):
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    sizes = [0]
    for sy, sx in zip(*np.nonzero(mask)):
        if lab[sy, sx]:
            continue
        n = len(sizes)
        stack = [(sy, sx)]
        lab[sy, sx] = n
        size = 0
        while stack:
            y, x = stack.pop()
            size += 1
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    stack.append((ny, nx))
        sizes.append(size)
    return lab, sizes


def iris_blobs(img):
    # 青い虹彩：青が強く、赤が弱い。目の高さの範囲（切り抜き内 y 600-1000）に限る。
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    blue = (b - r > 90) & (b > 150)
    blue[:600] = False
    blue[1000:] = False
    # 高速化のため 1/3 に縮小して連結成分を求める
    small = blue[::3, ::3]
    lab, sizes = components(small)
    order = sorted(range(1, len(sizes)), key=lambda i: -sizes[i])[:2]
    out = []
    for i in order:
        ys, xs = np.nonzero(lab == i)
        out.append({'x': float(xs.mean() * 3), 'y': float(ys.mean() * 3), 'area': int(sizes[i] * 9),
                    'w': float((xs.max() - xs.min() + 1) * 3), 'h': float((ys.max() - ys.min() + 1) * 3)})
    out.sort(key=lambda d: d['x'])
    return out


def main():
    result = {}
    for name, path, angle in SAMPLES:
        img = load(path)
        blobs = iris_blobs(img)
        result[name] = {'angle': angle, 'iris': blobs}
        desc = ' | '.join('(%.0f,%.0f) area=%d w=%.0f h=%.0f' % (b['x'], b['y'], b['area'], b['w'], b['h']) for b in blobs)
        print('%-8s angle %+3d  iris(left→right): %s' % (name, angle, desc))
    with open(os.path.join(ROOT, 'head-turn-measure.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
