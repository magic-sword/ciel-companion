# -*- coding: utf-8 -*-
"""首（顎の下〜首輪の下）を、A2（v4 の素肌ベース）から作り、Body_Base の画像に焼き込む。

bake-chin-into-body.py（K-2・K-3 を焼き込み、上へ 230 px 延ばした）の置き換え。K の版は、顎の両脇に
幅の広い白い板ができ、横を向くと、動かない体側の板が顔の脇に「灰色の四角」として見えていた。
ここでは、首の幅（A2 の首のいちばん細い所）だけの柱にする。顔が横を向いて首が見えても、それは正しい首の面になる。

入力  assets/ciel/layers/body/Body_Base.prechin.png（焼き込み前）、assets/ciel/generated/v4/A2_line_ref.png
出力  assets/ciel/layers/body/Body_Base.png、Neck_Gear.png（書き換える）
実行  python -I scripts/live2d/bake-neck-from-a2.py   完了表示 NECK_BAKED
"""
import os

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..', 'assets', 'ciel')
BODY = os.path.join(ROOT, 'layers', 'body', 'Body_Base.png')
GEAR = os.path.join(ROOT, 'layers', 'body', 'Neck_Gear.png')   # 元は Neck_Gear.pre-a2.png に初回だけ退避
A2 = os.path.join(ROOT, 'generated', 'v4', 'A2_line_ref.png')
FACE_MASK = os.path.join(ROOT, 'generated', 'v4', 'A2_face-shape-mask.png')
SHADE_Y = 1410     # 顎の下の影の色を採る高さ（A2 の首の、影の中）
NECK_TOP = 1330   # これより下の A2 を首として使う（頬から首へ細くなり終わる高さ。キャンバス座標）
EXTRUDE = 230      # 首の上端を、上へ延ばす量（px）。上を向いて顎が上がったとき、顎と首の間に隙間ができないように
INSET = 10         # 延ばす柱の幅を、首のいちばん細い所から、左右それぞれ内側へ寄せる量
ARCH = 0.7         # 柱の左右の端で、上端を下げる割合（EXTRUDE に対して）
RAMP = 14         # 柱の左右の縁の、不透明度の変化幅


def main():
    pre = BODY.replace('.png', '.prechin.png')
    body = Image.open(pre).convert('RGBA')
    a2 = np.asarray(Image.open(A2).convert('RGBA')).astype(np.float32)
    h, w = a2.shape[:2]

    neck = np.zeros_like(a2)
    neck[NECK_TOP:] = a2[NECK_TOP:]

    # 顎の先（顔の一部。輪郭線を含む）は、動かない体に残すと、顔が動いたときにずれて見えるので、首の影の色で塗る。
    # 顔の範囲は、A2 の顔の形のマスクを、輪郭線の分だけ広げたもの。
    face = np.asarray(Image.open(FACE_MASK).convert('L')) > 16
    face = np.asarray(Image.fromarray((face * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(17))) > 0
    shade = np.median(a2[SHADE_Y - 10:SHADE_Y + 10, 1000:1230, :3].reshape(-1, 3), axis=0)
    hit = face & (neck[..., 3] > 0)
    neck[hit, :3] = shade
    neck[hit, 3] = 255   # 下の元絵（焼き込み前の Body_Base）にある顎の線も覆う

    # 首のいちばん細い所の幅で、上へ延ばす柱を作る（色は顎の下の影の色）
    solid = a2[..., 3] > 200
    rows = range(NECK_TOP, NECK_TOP + 200)
    spans = [(np.nonzero(solid[y])[0].min(), np.nonzero(solid[y])[0].max()) for y in rows if solid[y].any()]
    x0 = max(s[0] for s in spans) + INSET
    x1 = min(s[1] for s in spans) - INSET
    xs = np.arange(w)
    side = np.clip(np.minimum(xs - x0, x1 - xs) / RAMP, 0, 1)
    y0 = NECK_TOP - EXTRUDE
    # 柱の上端は、中央が高く、左右が低いアーチにする（顔が横・上を向いたとき、四角い角が見えないように）
    cx, hw = (x0 + x1) / 2, (x1 - x0) / 2
    top = y0 + (ARCH * EXTRUDE * np.clip((xs - cx) / hw, -1, 1) ** 2).astype(int)
    for y in range(y0, NECK_TOP):
        neck[y, :, :3] = shade
        # 上端から RAMP px で、なだらかに現れる
        neck[y, :, 3] = 255 * side * np.clip((y - top + 1) / RAMP, 0, 1)
    # 柱と A2 の首の境で、列ごとの色の段差が出ないように、延ばした部分だけ横にぼかす
    ext = np.zeros((h, w), bool)
    ext[y0:NECK_TOP] = True
    blur = np.asarray(Image.fromarray(neck[..., :3].astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))).astype(np.float32)
    neck[ext, :3] = blur[ext]

    # 焼き込み前の元絵には、顔の下に、顎の線・頬の輪郭の弧が残っている（顔が動くと、元の位置に見える）。
    # 顔の範囲の元絵は消す（後ろにある Hair_Back が見える）。
    b = np.asarray(body).copy()
    b[face, 3] = 0
    body = Image.fromarray(b, 'RGBA')
    layer = Image.fromarray(np.clip(neck, 0, 255).astype(np.uint8), 'RGBA')
    body.alpha_composite(layer)
    body.save(BODY)

    # 首輪（Neck_Gear）の切り抜きにも、元絵の顎の先（白い V 字と線）が入っている。首輪も動かないので、顔の範囲を消す。
    gear_pre = GEAR.replace('.png', '.pre-a2.png')
    if not os.path.exists(gear_pre):
        Image.open(GEAR).save(gear_pre)
    g = np.asarray(Image.open(gear_pre).convert('RGBA')).copy()
    g[face, 3] = 0
    Image.fromarray(g, 'RGBA').save(GEAR)
    print('neck column x %d..%d, y %d..%d' % (x0, x1, y0, NECK_TOP))
    print('NECK_BAKED')


if __name__ == '__main__':
    main()
