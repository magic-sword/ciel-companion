# -*- coding: utf-8 -*-
"""上向きの顎の形（顔の下の輪郭）を、お手本と今のモデルで比べる。

お手本：pose-ref の上向き画像で、中央の列ごとに、口の下から下へたどり、明るい顔（白磁）が終わって
陰の色（顎の裏）に変わる高さを、顔の下の輪郭とする（基準画像の座標へ直す）。
モデル：顔の肌（Face_Skin）の下の輪郭の点を、head3d-keys.py の回転（上向き）で動かす。
head3d-keys.py の定数を引数で上書きして比べられる（例：CHIN_FWD=150）。両方を重ねた図も出す。
実行  python -I scripts/live2d/fit-jaw-curve.py 出力.png [名前=値 ...]
"""
import importlib.util
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('h3d', os.path.join(HERE, 'head3d-keys.py'))
h3d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h3d)
A = os.path.join(HERE, '..', '..', 'assets', 'ciel')
CROP = (318, 236)          # pose-ref の切り抜きの、基準画像での左上
POSES = {15.0: 'pose_x0_yU15_porcelain.png', 30.0: 'pose_x0_yU30_porcelain.png'}


def ref_curve(name, mouth_y):
    a = np.asarray(Image.open(os.path.join(A, 'generated', 'pose-ref', name)).convert('RGB')).astype(float)
    lum = a.mean(axis=2)
    pts = []
    for cx in range(820, 1390, 6):            # 基準画像の x
        x = cx - CROP[0]
        col = lum[:, x - 1:x + 2].mean(axis=1)
        y0 = int(mouth_y - CROP[1]) + 40
        for y in range(y0, min(len(col) - 6, y0 + 500)):
            if col[y:y + 6].max() < 238:      # 明るい顔が終わり、陰が 6 行続く
                pts.append((cx, y + CROP[1]))
                break
    return np.array(pts, float)


def face_bottom():
    a = np.asarray(Image.open(os.path.join(A, 'layers', 'head', 'Face_Skin.png')).convert('RGBA'))[..., 3] > 128
    pts = []
    for x in range(780, 1430, 6):
        ys = np.nonzero(a[1150:, x])[0]
        if len(ys):
            pts.append((float(x), float(1150 + ys.max())))
    return pts


def main(out, overrides):
    for o in overrides:
        k, v = o.split('=')
        setattr(h3d, k, float(v))
    base = face_bottom()
    # 口の高さ（お手本の上向きで、顔の中の口の位置）は、モデルで口の中心（1250）を動かした位置
    tiles = []
    for key, name in POSES.items():
        pitch = h3d.PITCH[key]
        model = np.array(h3d.rotated(base, 0.0, pitch))
        mouth = h3d.rotated([(1104.0, 1250.0)], 0.0, pitch)[0][1]
        ref = ref_curve(name, mouth)
        # 比較：同じ x での y の差
        diffs = []
        for x, y in ref:
            j = np.argmin(np.abs(model[:, 0] - x))
            if abs(model[j, 0] - x) < 8:
                diffs.append(model[j, 1] - y)
        diffs = np.array(diffs)
        print('up %2.0f  model - ref : mean %+6.1f  center %+6.1f  rms %5.1f  (n=%d)' % (
            key, diffs.mean(), diffs[len(diffs) // 2], np.sqrt((diffs ** 2).mean()), len(diffs)))
        im = Image.open(os.path.join(A, 'generated', 'pose-ref', name)).convert('RGB')
        d = ImageDraw.Draw(im)
        d.line([(x - CROP[0], y - CROP[1]) for x, y in ref], fill=(0, 200, 0), width=4)
        d.line([(x - CROP[0], y - CROP[1]) for x, y in model], fill=(255, 0, 0), width=4)
        tiles.append(im.crop((400, 400, 1150, 1200)).resize((450, 480)))
    sheet = Image.new('RGB', (450 * len(tiles), 480), 'white')
    for i, t in enumerate(tiles):
        sheet.paste(t, (450 * i, 0))
    sheet.save(out)
    print('JAW_CURVE', out)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
