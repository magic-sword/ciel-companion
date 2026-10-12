# -*- coding: utf-8 -*-
"""横を向いたときの頬の輪郭（cheek_shape.py の形）を、Face_Skin の角度X ±30 のキーフォームに書き込む。

前提：Face_Skin は remesh-face-contour.py の輪郭に沿ったメッシュで、角度X のキー（±30。0 があってもよい）が
正面の形のまま入っている。書き出したモデル（.model3.json）を Core で計算して、親の横向きの変形を得る。
親（顔の曲面）の ±30 の変形はアフィン（拡大と移動）なので、正面 → 横向きの対応を一次式で求め、目標の位置を
「正面ならどこにあたるか」へ戻してから、顔の曲面の正規化座標で書く。

実行  python -I scripts/live2d/cheek-keys.py 入力.cmo3 書き出したモデル.model3.json 出力.cmo3
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

_spec = importlib.util.spec_from_file_location('half_blink', os.path.join(HERE, 'half-blink-keys.py'))
hb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hb)


def main():
    src, model3, dst = sys.argv[1:4]
    doc = t.Cmo3(src)
    name = 'Face_Skin'
    core = cc.Model(model3)

    def pos(v):
        core.reset()
        core.set({'ParamAngleX': v})
        core.update()
        return {d['id']: d['pos'] for d in core.drawables()}[name]
    blocks = hb.keyform_blocks(doc, name)
    vals = hb.key_values(doc, name)
    base = np.mean([f[2] for f in blocks], 0)                   # キーを足した直後はどれも正面の形
    core_front = pos(0)
    # 正面の位置は、メッシュの point（画像座標。remesh-face-contour.py はキーフォームと同じ並びで書く）。
    # 親の ±30 の変形（アフィン）は、書き出したモデルの頂点から求める（メッシュを作り直した後でも、親は同じなので使える）
    a, b = doc.mesh_block(name)
    front = np.array(re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)<', doc.xml[a:b]).group(1).split(), float).reshape(-1, 2)
    A0 = np.c_[core_front, np.ones(len(core_front))]
    A = np.c_[front, np.ones(len(front))]
    to_n, *_ = np.linalg.lstsq(A, base, rcond=None)
    if np.abs(A @ to_n - base).max() > 1e-4:
        raise SystemExit('頂点の並びが合わない')
    for (s0, e0, _), v in sorted(zip(blocks, vals), key=lambda z: -z[0][0]):
        f = base.copy()
        if abs(v) > 1e-6:
            # 親の変形（正面 → 横向き）の一次式
            M, *_ = np.linalg.lstsq(A0, pos(v), rcond=None)
            cur = A @ M
            new, _ = cs.shape(cur, int(np.sign(v)))
            # 横向きの目標の位置を、正面の位置へ戻す：cur = [p, 1] @ M → p = (cur - M[2]) @ inv(M[:2])
            p = (new - M[2]) @ np.linalg.inv(M[:2])
            f = np.c_[p, np.ones(len(p))] @ to_n
        doc.xml = doc.xml[:s0] + ' '.join(_fmt(q) for q in f.ravel()) + doc.xml[e0:]
    doc.save(dst)
    print('CHEEK_KEYS_DONE', vals)


if __name__ == '__main__':
    main()
