"""4頂点（キャンバス全体）のメッシュを、各レイヤー画像の描画範囲へ切り詰める（アトラスを小さく・軽くする）。

使い方: python -I scripts/live2d/crop-quad-meshes.py <入力.cmo3> <出力.cmo3>
範囲は、assets/ciel/layers/ のレイヤー画像（と、Face_Base は目のない基準画像）の、不透明な画素から求める。
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmo3_tool as t

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel')
L = os.path.join(ROOT, 'layers')


def files():
    f = {}
    for side in ('L', 'R'):
        for p in ('crease', 'lash', 'iris', 'sclera'):
            f['%s_%s_Half' % (side, p.capitalize())] = os.path.join(L, 'eyes', '%s_%s_half.png' % (side, p))
        for p in ('crease', 'lash'):
            f['%s_%s_Closed' % (side, p.capitalize())] = os.path.join(L, 'eyes', '%s_%s_closed.png' % (side, p))
        f['%s_Crease' % side] = os.path.join(L, 'eyes', '%s_crease.png' % side)
    for n in ('Hair_Front', 'Face_Skin', 'Ear_L', 'Ear_R', 'Hair_Under_Ear', 'Hair_Back', 'Mouth_Large', 'Mouth_Small', 'Mouth_Closed'):
        f[n] = os.path.join(L, 'head', n + '.png')
    for n in ('Neck_Gear', 'Chest_Gem', 'Waist_Belt', 'Outer_L', 'Outer_R', 'Body_Base'):
        f[n] = os.path.join(L, 'body', n + '.png')
    f['Face_Base'] = os.path.join(ROOT, 'master', 'ciel-upper-body-2x-eyeless.png')
    return f


def main(src, dst):
    doc = t.Cmo3(src)
    done = []
    for name, path in files().items():
        a = np.asarray(Image.open(path).convert('RGBA'))[..., 3]
        ys, xs = np.nonzero(a > 0)
        try:
            doc.crop_quad_mesh(name, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())))
            done.append(name)
        except (KeyError, ValueError) as e:
            print('skip', name, e)
    doc.save(dst)
    print('cropped %d meshes -> %s' % (len(done), dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
