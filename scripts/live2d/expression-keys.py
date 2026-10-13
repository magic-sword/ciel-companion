# -*- coding: utf-8 -*-
"""表情のための変形（眉・口の形・目線・耳）の形を、キーフォームに設定する。目標は表情の見本 v22（assets/ciel/generated/v22/）。

前提：Cubism で次のキーを「キーの3点追加」してある（-1/0/1。ほかのキーとの組み合わせはそのまま）。
  右/左まゆ毛の位置   ParamBrowRY / ParamBrowLY        +1 上がる、-1 下がる
  右/左まゆ毛の角度   ParamBrowRAngle / ParamBrowLAngle +1 困り眉（眉頭が上がる）、-1 怒り眉（眉頭が下がる）
  右/左まゆ毛の曲面   ParamBrowRForm / ParamBrowLForm   +1 山なり、-1 平ら〜少しへこむ
  口の曲面           ParamMouthForm                    +1 口角が上がる、-1 への字
  右/左目玉の曲面     ParamEyeBallX / ParamEyeBallY     +1 画面の右・上を見る
  右/左耳の曲面       ParamEar                          +1 ぴんと立つ、-1 横に倒れる
形は、同じほかのキーで、そのパラメーターが 0 の形からの差として作る（何度実行しても同じ）。
量は格子の大きさに対する比（格子は部品を囲む大きさなので、部品の大きさに比例する）。

実行  python -I scripts/live2d/expression-keys.py 入力.cmo3 出力.cmo3
"""
import importlib.util
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t

_spec = importlib.util.spec_from_file_location('motion_keys', os.path.join(HERE, 'motion-keys.py'))
mk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mk)

BROW_Y = 0.55        # 眉の上下（眉の格子の高さに対する比）
BROW_TILT = 0.55     # 眉頭の上下（格子の高さに対する比）
BROW_ARCH = 0.35     # 眉の山なり
MOUTH_CORNER = 0.10  # 口角の上下（口の格子の高さに対する比）
EYE_X, EYE_Y = 0.22, 0.16   # 目線（目玉の格子の幅・高さに対する比）
EAR_DOWN_DEG = 38.0  # 耳を横に倒す角度
EAR_UP = 0.08        # 耳を立てる（縦に伸ばす比）


def box(g):
    lo, hi = g.min(0), g.max(0)
    return (lo + hi) / 2, hi - lo


def brow_y(g, v):
    c, (w, h) = box(g)
    n = g.copy()
    n[:, 1] -= v * BROW_Y * h
    return n


def brow_angle(inner_sign):
    """inner_sign：眉頭が x の + 側なら +1（画面の左の眉＝キャラクターの右眉）。"""
    def fn(g, v):
        c, (w, h) = box(g)
        u = (g[:, 0] - c[0]) / (w / 2) * inner_sign      # 眉頭 +1、眉尻 -1
        n = g.copy()
        n[:, 1] -= v * BROW_TILT * h * u
        return n
    return fn


def brow_form(g, v):
    c, (w, h) = box(g)
    u = (g[:, 0] - c[0]) / (w / 2)
    n = g.copy()
    n[:, 1] -= v * BROW_ARCH * h * (1 - u ** 2)
    return n


def mouth_form(g, v):
    c, (w, h) = box(g)
    u = (g[:, 0] - c[0]) / (w / 2)
    n = g.copy()
    n[:, 1] -= v * MOUTH_CORNER * h * (u ** 2 - 0.3)    # 口角が上がり、真ん中は少し下がる（+1 で笑顔）
    n[:, 0] = c[0] + (g[:, 0] - c[0]) * (1 + 0.04 * v)
    return n


def eye_x(g, v):
    c, (w, h) = box(g)
    n = g.copy()
    n[:, 0] += v * EYE_X * w
    return n


def eye_y(g, v):
    c, (w, h) = box(g)
    n = g.copy()
    n[:, 1] -= v * EYE_Y * h
    return n


def ear(outward_sign):
    """outward_sign：耳の外側が x の + 側なら +1（画面の右の耳＝キャラクターの左耳）。付け根（下端の中央）を軸に動かす。"""
    def fn(g, v):
        c, (w, h) = box(g)
        pivot = np.array([c[0], g[:, 1].max()])
        d = g - pivot
        if v > 0:   # ぴんと立つ：上へ少し伸ばす
            return pivot + d * np.array([1.0, 1 + EAR_UP * v])
        # 根元の下側 25% を固定し、先端ほど曲げる。根元を含む剛体回転は切り口を露出させる。
        height = np.clip(-d[:, 1] / h, 0, 1)
        bend = np.clip((height - 0.25) / 0.75, 0, 1)
        bend = bend * bend * (3 - 2 * bend)
        th = math.radians(EAR_DOWN_DEG * -v) * outward_sign * bend
        out = np.stack([d[:, 0] * np.cos(th) - d[:, 1] * np.sin(th),
                        d[:, 0] * np.sin(th) + d[:, 1] * np.cos(th)], axis=1)
        out[:, 1] *= 1 - 0.12 * -v * bend
        return pivot + out
    return fn


def main():
    src, dst = sys.argv[1:3]
    doc = t.Cmo3(src)
    mk.load_params(doc.xml)
    mk.edit_warp(doc, '右まゆ毛の位置', 'ParamBrowRY', brow_y)
    mk.edit_warp(doc, '左まゆ毛の位置', 'ParamBrowLY', brow_y)
    mk.edit_warp(doc, '右まゆ毛の角度', 'ParamBrowRAngle', brow_angle(+1))
    mk.edit_warp(doc, '左まゆ毛の角度', 'ParamBrowLAngle', brow_angle(-1))
    mk.edit_warp(doc, '右まゆ毛の曲面', 'ParamBrowRForm', brow_form)
    mk.edit_warp(doc, '左まゆ毛の曲面', 'ParamBrowLForm', brow_form)
    mk.edit_warp(doc, '口の曲面', 'ParamMouthForm', mouth_form)
    for side in ('右', '左'):
        mk.edit_warp(doc, side + '目玉の曲面', 'ParamEyeBallX', eye_x)
        mk.edit_warp(doc, side + '目玉の曲面', 'ParamEyeBallY', eye_y)
    mk.edit_warp(doc, '右耳の曲面', 'ParamEar', ear(-1))
    mk.edit_warp(doc, '左耳の曲面', 'ParamEar', ear(+1))
    doc.save(dst)
    print('EXPRESSION_KEYS_DONE')


if __name__ == '__main__':
    main()
