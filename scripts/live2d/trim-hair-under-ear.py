"""Hair_Under_Ear を、耳の下にかくれる範囲だけに絞る。

Hair_Under_Ear は、依頼E（耳を消した顔）の画素で、E は耳のあった所を白で塗っている。耳の外へはみ出した白い塊が
そのまま見えてしまうので、きれいにした Ear_R / Ear_L（clean-ear-layers.py の後）をふくらませた範囲との共通部分だけを残す。
入力・出力  assets/ciel/layers/head/Hair_Under_Ear.png（書き換える。元は Hair_Under_Ear.orig.png に退避）
実行  python -I scripts/live2d/trim-hair-under-ear.py   完了表示 HAIR_UNDER_EAR_TRIMMED
"""
import os
import shutil

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'layers', 'head')
GROW = 25   # 耳の縁より、少し外まで残す（MaxFilter の大きさ）


def main():
    path = os.path.join(ROOT, 'Hair_Under_Ear.png')
    orig = path.replace('.png', '.orig.png')
    if not os.path.exists(orig):
        shutil.copy(path, orig)
    im = np.asarray(Image.open(orig).convert('RGBA')).copy()
    ear = np.zeros(im.shape[:2], bool)
    for n in ('Ear_R', 'Ear_L'):
        ear |= np.asarray(Image.open(os.path.join(ROOT, n + '.png')).convert('RGBA'))[..., 3] > 8
    near = np.asarray(Image.fromarray((ear * 255).astype('uint8')).filter(ImageFilter.MaxFilter(GROW))) > 0
    im[~near, 3] = 0
    Image.fromarray(im, 'RGBA').save(path)
    print('HAIR_UNDER_EAR_TRIMMED')


if __name__ == '__main__':
    main()
