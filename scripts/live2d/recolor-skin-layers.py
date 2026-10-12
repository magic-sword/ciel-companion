# -*- coding: utf-8 -*-
"""顔の土台（Face_Skin）を差し替えたとき、目・口のまわりの肌色の層の色を、新しい土台の肌の色に合わせる。

肌色の層（口のまわり 2 枚、まぶたの肌 4 枚）は、もとの土台と同じ色の肌で塗られている。新しい土台との色の差
（顔の内側の平均の差、チャンネルごと）だけ、色の値をずらす。形・透明度は変えない（描き足し・塗りはしない）。
出力は、指定のフォルダへ同じ名前で。あわせて、全層の組み上げ（正面）を作る。

実行  python -I scripts/live2d/recolor-skin-layers.py 新しいFace_Skin.png 出力フォルダ
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
CUR = os.path.join(ROOT, 'assets', 'ciel', 'current')
SKIN_LAYERS = ['Mouth_Skin_Upper', 'Mouth_Skin_Lower',
               'Eye_R_LidSkin_Upper', 'Eye_R_LidSkin_Lower', 'Eye_L_LidSkin_Upper', 'Eye_L_LidSkin_Lower']
# 顔の内側（輪郭の線や髪の影から離れた所）で色の差を測る
REGION = (880, 850, 1340, 1300)   # x0, y0, x1, y1


def rgba(p):
    return np.asarray(Image.open(p).convert('RGBA')).astype(np.float64)


def main():
    new_path, out_dir = sys.argv[1:3]
    os.makedirs(out_dir, exist_ok=True)
    old = rgba(os.path.join(CUR, 'layers', 'Face_Skin.png'))
    new = rgba(new_path)
    x0, y0, x1, y1 = REGION
    m = (old[y0:y1, x0:x1, 3] > 250) & (new[y0:y1, x0:x1, 3] > 250)
    off = new[y0:y1, x0:x1, :3][m].mean(0) - old[y0:y1, x0:x1, :3][m].mean(0)
    print('色の差（R, G, B）:', off.round(2))
    for n in SKIN_LAYERS:
        a = rgba(os.path.join(CUR, 'layers', n + '.png'))
        a[..., :3] = np.clip(a[..., :3] + off, 0, 255)
        Image.fromarray((a + 0.5).astype(np.uint8)).save(os.path.join(out_dir, n + '.png'))
    Image.open(new_path).save(os.path.join(out_dir, 'Face_Skin.png'))
    # 組み上げ（正面）
    d = json.load(open(os.path.join(CUR, 'layers.json'), encoding='utf-8-sig'))
    canvas = Image.new('RGBA', tuple(d['canvas']), (255, 255, 255, 255))
    for l in d['layers']:
        if not l.get('visible', True):
            continue
        p = os.path.join(out_dir, l['name'] + '.png')
        if not os.path.exists(p):
            p = os.path.join(CUR, 'layers', l['name'] + '.png')
        canvas.alpha_composite(Image.open(p).convert('RGBA'))
    canvas.convert('RGB').save(os.path.join(out_dir, 'assembled.png'))
    print('RECOLOR_SKIN_LAYERS_DONE', json.dumps({'offset': off.round(3).tolist()}))


if __name__ == '__main__':
    main()
