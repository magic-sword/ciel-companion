# -*- coding: utf-8 -*-
"""後ろ髪のワープ（後ろ髪の曲面）に、角度X・Y・Z（3×3×3 キー）の形を設定する。根元は頭に付け、毛先ほど動かさない。

後ろ髪は頭の上から肩の下までの 1 枚なので、頭の回転にまるごと付けると毛先が肩の横で大きく振れる。そこで、
体の側（上半身の曲面Y の直下）に置いたまま、格子の各点を「頭と一緒に動いた位置」へ重み w だけ寄せる。
  w = 1（顎より上）→ 0（FREE_Y より下）。間はなめらかにつなぐ。
頭と一緒に動いた位置：
  角度Z … 顔の回転と同じ回転（書き出したモデルを Cubism Core で計算し、Face_Skin の動きから軸と角度を求める）
  角度X・Y … 頭の後ろなので、顔よりずっと小さく、向きと逆へ（docs/ciel-live2d-rig-design-ja.md 4 章：X −0.005、Y −0.025）

前提：Cubism で、後ろ髪の曲面に 角度X・角度Y・角度Z の「キーの3点追加」をしてある（±30 の 8 キーフォーム、または 0 を含む 27）。
実行  python -I scripts/live2d/back-hair-keys.py 入力.cmo3 書き出したモデル.model3.json 出力.cmo3
      書き出したモデル：顔の回転の角度Z のキーが入ったもの（後ろ髪のワープの有無は問わない）
"""
import importlib.util
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
import cubism_core as cc
from cmo3_tool import _fmt

_spec = importlib.util.spec_from_file_location('motion_keys', os.path.join(HERE, 'motion-keys.py'))
mk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mk)

WARP = '後ろ髪の曲面'
FACE_W = 700.0
RX, RY = -0.005, -0.025
FREE_Y = 2300.0         # これより下（キャンバスの px）は頭に付いて動かない


def rigid_fit(a, b):
    """a を b へ写す 2 次元の回転＋平行移動（角度、回転の中心）。"""
    ca, cb = a.mean(0), b.mean(0)
    h = (a - ca).T @ (b - cb)
    th = np.arctan2(h[0, 1] - h[1, 0], h[0, 0] + h[1, 1])
    r = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    tr = cb - r @ ca
    piv = np.linalg.solve(np.eye(2) - r, tr)       # r p + tr = p
    return th, piv


def main():
    src, model3, dst = sys.argv[1:4]
    doc = t.Cmo3(src)
    mk.load_params(doc.xml)

    # 頭の回転（角度Z = +30）と、顎の高さ
    core = cc.Model(model3)
    core.reset(); core.update()
    face0 = {d['id']: d['pos'] for d in core.drawables()}['Face_Skin']
    core.reset(); core.set({'ParamAngleZ': 30}); core.update()
    face1 = {d['id']: d['pos'] for d in core.drawables()}['Face_Skin']
    th30, piv = rigid_fit(face0, face1)
    chin_y = face0[:, 1].max()
    print('角度Z +30: %.2f 度、軸 (%.0f, %.0f)、顎 y=%.0f' % (np.degrees(th30), piv[0], piv[1], chin_y))

    # キャンバス px ⇔ 親（上半身の曲面Y）の座標：後ろ髪のメッシュの point（px）と、ワープの中での位置から
    ma, mb = doc.mesh_block('Hair_Back')
    mblk = doc.xml[ma:mb]
    pts = np.array(re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)<', mblk).group(1).split(), float).reshape(-1, 2)
    k = mblk.index('<carray_list xs.n="keyforms"')
    nrm = np.array(re.search(r'<float-array xs\.n="positions" count="\d+">([^<]*)<', mblk[k:]).group(1).split(), float).reshape(-1, 2)
    rest = np.array(doc.warp_keyform_positions(WARP)[0])
    lo, hi = rest.min(0), rest.max(0)
    q = lo + nrm * (hi - lo)                     # 親の座標でのメッシュの位置
    fx = np.polyfit(pts[:, 0], q[:, 0], 1)
    fy = np.polyfit(pts[:, 1], q[:, 1], 1)
    to_px = lambda g: np.stack([(g[:, 0] - fx[1]) / fx[0], (g[:, 1] - fy[1]) / fy[0]], 1)
    to_q = lambda p: np.stack([np.polyval(fx, p[:, 0]), np.polyval(fy, p[:, 1])], 1)

    x = doc.xml
    s, e = mk.block(x, 'CWarpDeformerSource', WARP)
    blk = x[s:e]
    keys = mk.form_keys(x, blk, 'CWarpDeformerForm')
    forms = mk.warp_forms(blk)
    if len(forms) not in (8, 27):
        raise SystemExit('キーフォームが 8 でも 27 でもない: %d' % len(forms))
    # キーを足した直後はどれも同じ形（正面の形）
    base = np.mean([f[2] for f in forms], 0)
    p0 = to_px(base)
    u = np.clip((p0[:, 1] - chin_y) / (FREE_Y - chin_y), 0, 1)
    w = 1 - u * u * (3 - 2 * u)
    out = blk
    for (a, b, _), kk in sorted(zip(forms, keys), key=lambda z: -z[0][0]):
        sx, sy, sz = kk['ParamAngleX'] / 30, kk['ParamAngleY'] / 30, kk['ParamAngleZ'] / 30
        # 回転は一次の近似（±30 の 2 キーだけのとき、間の 0 で元の形に戻るように）
        d = p0 - piv
        moved = p0 + th30 * sz * np.stack([-d[:, 1], d[:, 0]], 1)
        moved[:, 0] += RX * FACE_W * sx
        moved[:, 1] -= RY * FACE_W * sy * (0.9 if sy < 0 else 1.0)
        p = p0 + (moved - p0) * w[:, None]
        out = out[:a] + ' '.join(_fmt(v) for v in to_q(p).ravel()) + out[b:]
    doc.xml = x[:s] + out + x[e:]
    doc.save(dst)
    print('BACK_HAIR_KEYS_DONE')


if __name__ == '__main__':
    main()
