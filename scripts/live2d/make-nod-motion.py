# -*- coding: utf-8 -*-
"""頷きのモーション（motion3.json）を作る。

公式サンプル（ひより）の頷き（hiyori_m08・m09）に近い動き：角度Y を素早く下げて戻すのを 2 回。
体の角度Y は少し遅れて小さく動く（体ごと少し前へ）。曲線は線分で細かく区切る（Unity の取り込みで扱いやすいように）。
実行  python -I scripts/live2d/make-nod-motion.py 出力.motion3.json
"""
import json
import math
import sys

DURATION = 1.4
FPS = 30.0
STEP = 1.0 / 30
NODS = 2
ANGLE_Y = -25.0       # 頷きの深さ（角度Y）
BODY_Y = -6.0         # 体の前への傾き（体の角度Y）
BODY_DELAY = 0.08     # 体の遅れ（秒）
NOD_TIME = 0.55       # 1 回の頷きの長さ（秒）


def nod(t):
    """0〜1 の 1 回の頷きの形（すばやく下げて、ややゆっくり戻す）。"""
    if t <= 0 or t >= 1:
        return 0.0
    return math.sin(math.pi * (t ** 0.8)) ** 1.5


def value(t, amp, delay):
    v = 0.0
    for i in range(NODS):
        v += nod((t - delay - i * NOD_TIME) / NOD_TIME) * amp
    return v


def curve(pid, amp, delay):
    n = int(round(DURATION / STEP))
    seg = [0.0, round(value(0, amp, delay), 3)]
    for k in range(1, n + 1):
        t = round(k * STEP, 4)
        seg += [0, t, round(value(t, amp, delay), 3)]
    return {'Target': 'Parameter', 'Id': pid, 'Segments': seg}, n, n + 1


def main():
    out = sys.argv[1]
    curves, segs, pts = [], 0, 0
    for pid, amp, delay in (('ParamAngleY', ANGLE_Y, 0.0), ('ParamBodyAngleY', BODY_Y, BODY_DELAY)):
        c, s, p = curve(pid, amp, delay)
        curves.append(c)
        segs += s
        pts += p
    data = {'Version': 3,
            'Meta': {'Duration': DURATION, 'Fps': FPS, 'Loop': False, 'AreBeziersRestricted': True,
                     'CurveCount': len(curves), 'TotalSegmentCount': segs, 'TotalPointCount': pts,
                     'UserDataCount': 0, 'TotalUserDataSize': 0},
            'Curves': curves}
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print('NOD_MOTION_DONE', out)


if __name__ == '__main__':
    main()
