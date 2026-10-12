# -*- coding: utf-8 -*-
"""横を向いたときの頬の輪郭（cheek_shape.py の形）を、Face_Skin の角度X ±30 のキーフォームに書き込む。

前提：Face_Skin は remesh-face-contour.py の輪郭に沿ったメッシュで、角度X のキー（±30。0 があってもよい）が
正面の形のまま入っている。書き出したモデル（.model3.json）を Core で計算して、親の横向きの変形を得る。
親（顔の曲面）の ±30 の変形はアフィン（拡大と移動）なので、正面 → 横向きの対応を一次式で求め、目標の位置を
「正面ならどこにあたるか」へ戻してから、顔の曲面の正規化座標で書く。

あわせて、横髪のワープの角度X ±30 の格子に、横髪の動き（cheek_shape.hair_shape）を足す（hair_keys）。

実行  python -I scripts/live2d/cheek-keys.py 入力.cmo3 書き出したモデル.model3.json 出力.cmo3 [正面の形の.cmo3]
      正面の形の .cmo3：すでに頬の形が入っているモデルを作り直すとき、形を付ける前のもの（Face_Skin の頂点の並びが同じ）。
      横髪の動きは足し算なので、横髪の動きがまだ入っていない入力に使う。
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
import cheek_shape as cs
from cmo3_tool import _fmt

def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


hb = _load('half_blink', 'half-blink-keys.py')
mk = _load('motion_keys', 'motion-keys.py')
sk = _load('sway_keys', 'sway-keys.py')


def main():
    src, model3, dst = sys.argv[1:4]
    rest_src = sys.argv[4] if len(sys.argv) > 4 else None
    doc = t.Cmo3(src)
    name = 'Face_Skin'
    core = cc.Model(model3)

    def pos(v, mesh):
        core.reset()
        core.set({'ParamAngleX': v})
        core.update()
        return {d['id']: d['pos'] for d in core.drawables()}[mesh]
    blocks = hb.keyform_blocks(doc, name)
    vals = hb.key_values(doc, name)
    if rest_src:   # 頬の形を作り直すとき：正面の形は、形を付ける前の .cmo3 から
        base = np.mean([f[2] for f in hb.keyform_blocks(t.Cmo3(rest_src), name)], 0)
    else:          # キーを足した直後はどれも正面の形
        base = np.mean([f[2] for f in blocks], 0)
    # 正面の位置は、メッシュの point（画像座標。remesh-face-contour.py はキーフォームと同じ並びで書く）。
    # 親（顔の曲面）の ±30 の変形（アフィン）は、同じ親の Face_Shadow_Hair（キーは正面のまま）の動きから求める
    # （書き出したモデルの Face_Skin に古い形のキーが入っていても使える）
    a, b = doc.mesh_block(name)
    front = np.array(re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)<', doc.xml[a:b]).group(1).split(), float).reshape(-1, 2)
    sh0 = pos(0, 'Face_Shadow_Hair')
    A0 = np.c_[sh0, np.ones(len(sh0))]
    A = np.c_[front, np.ones(len(front))]
    to_n, *_ = np.linalg.lstsq(A, base, rcond=None)
    if np.abs(A @ to_n - base).max() > 1e-4:
        raise SystemExit('頂点の並びが合わない')
    turned = {}
    for (s0, e0, _), v in sorted(zip(blocks, vals), key=lambda z: -z[0][0]):
        f = base.copy()
        if abs(v) > 1e-6:
            M, *_ = np.linalg.lstsq(A0, pos(v, 'Face_Shadow_Hair'), rcond=None)
            cur = A @ M
            new, _ = cs.shape(cur, int(np.sign(v)))
            turned[int(np.sign(v))] = new
            # 横向きの目標の位置を、正面の位置へ戻す：cur = [p, 1] @ M → p = (cur - M[2]) @ inv(M[:2])
            p = (new - M[2]) @ np.linalg.inv(M[:2])
            f = np.c_[p, np.ones(len(p))] @ to_n
        doc.xml = doc.xml[:s0] + ' '.join(_fmt(q) for q in f.ravel()) + doc.xml[e0:]
    cdx = {sg: cs.contour_dx(front, turned[sg], sg) for sg in turned}
    hair_keys(doc, cdx)
    doc.save(dst)
    print('CHEEK_KEYS_DONE', vals)


def hair_keys(doc, cdx):
    """横髪のワープ（左横髪の曲面・右横髪の曲面）の、角度X ±30 のキーの格子に、cheek_shape.hair_shape の動きを足す。
    ワープの中の束（内側の束と下の長い束）が一緒に動く。正面の格子は、同じほかのキーで角度X が 0 のキーの形。
    cdx：反対側の頬の輪郭の動き（cheek_shape.contour_dx、向きごと）。"""
    mk.load_params(doc.xml)
    for warp, mesh in (('左横髪の曲面', 'Hair_Side_L_Inner'), ('右横髪の曲面', 'Hair_Side_R_Inner')):
        fx, fy = sk.px_map(doc, warp, mesh)
        x = doc.xml
        s, e = mk.block(x, 'CWarpDeformerSource', warp)
        blk = x[s:e]
        keys = mk.form_keys(x, blk, 'CWarpDeformerForm')
        forms = mk.warp_forms(blk)
        out = blk
        to_px = lambda g: np.stack([(g[:, 0] - fx[1]) / fx[0], (g[:, 1] - fy[1]) / fy[0]], 1)
        for (a, b, g), k in sorted(zip(forms, keys), key=lambda z: -z[0][0]):
            v = k.get('ParamAngleX', 0.0)
            if abs(abs(v) - 30) > 1e-6:
                continue
            # 正面の格子：角度X だけ 0 で、ほかのキーが同じ形
            other = {p: q for p, q in k.items() if p != 'ParamAngleX'}
            rest = [g2 for (a2, b2, g2), k2 in zip(forms, keys)
                    if abs(k2.get('ParamAngleX', 0.0)) < 1e-6 and all(abs(k2.get(p, 0) - q) < 1e-6 for p, q in other.items())]
            if not rest:
                raise SystemExit('%s に角度X 0 のキーがない' % warp)
            sg = int(np.sign(v))
            px = to_px(g)
            moved = cs.hair_shape(mesh, px, to_px(rest[0]), sg, cdx[sg])
            g2 = g + np.stack([(moved[:, 0] - px[:, 0]) * fx[0], (moved[:, 1] - px[:, 1]) * fy[0]], 1)
            out = out[:a] + ' '.join(_fmt(q) for q in g2.ravel()) + out[b:]
        doc.xml = x[:s] + out + x[e:]
        print('横髪:', warp)


if __name__ == '__main__':
    main()
