# -*- coding: utf-8 -*-
"""頭の 3D の形（head3d-keys.py）を直したあと、頭について動くメッシュの 25 キーの位置を、作り直さずに計算し直す。

対象：後ろ髪（Hair_Back、hair-back-follow.py の moved）と、顎の裏と線（Chin_Under・Chin_Under_Line・Neck_Line、chin-under-keys.py の moved）。
どちらも、すでに角度X×角度Y の 25 キーを持つこと（キーの並びは Y ごとに X が 5 つ）。メッシュの基準の点から計算する。
実行  python -I scripts/live2d/rekey-head-followers.py 入力.cmo3 出力.cmo3   完了表示 HEAD_FOLLOWERS_REKEYED
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
from cmo3_tool import _fmt


def load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


h3d = load('h3d', 'head3d-keys.py')
chin = load('chin', 'chin-under-keys.py').moved
TARGETS = {'Hair_Back': load('hair', 'hair-back-follow.py').moved,
           'Chin_Under': chin, 'Chin_Under_Line': chin, 'Neck_Line': chin}


def rekey(d, mesh, moved):
    a0, b0 = d.mesh_block(mesh)
    blk = d.xml[a0:b0]
    vals = [float(v) for v in re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)</float-array>', blk).group(1).split()]
    rest = list(zip(vals[0::2], vals[1::2]))
    a, b = d.mesh_keyforms(mesh)
    kf = d.xml[a:b]
    n = len(re.findall(r'<float-array xs\.n="positions"', kf))
    if n != 25:
        raise SystemExit('%s: expected 25 keyforms, found %d' % (mesh, n))
    poses = []
    for ky in h3d.KEYS:
        for kx in h3d.KEYS:
            yaw = h3d.YAW[kx] + h3d.EXTRA_RATE * h3d.YAW_EXTRA.get(kx, {}).get(abs(ky), 0.0)
            pts = moved(rest, yaw, h3d.PITCH[ky])
            poses.append(' '.join(_fmt(v) for q in pts for v in q))
    it = iter(poses)
    kf = re.sub(r'(<float-array xs\.n="positions" count=")\d+(">)[^<]*(</float-array>)',
                lambda m: m.group(1) + str(2 * len(rest)) + m.group(2) + next(it) + m.group(3), kf)
    d.xml = d.xml[:a] + kf + d.xml[b:]


def main(src, dst):
    d = t.Cmo3(src)
    for mesh, moved in TARGETS.items():
        rekey(d, mesh, moved)
    d.save(dst)
    print('HEAD_FOLLOWERS_REKEYED', dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
