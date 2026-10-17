# -*- coding: utf-8 -*-
"""書き出したモデルで、ほっぺを押して離す動きを、物理演算の揺れ込みで GIF にする（v64）。

押す量（ParamCielCheekPokeL）を 0 → 1 → 保つ → 0 と動かし、揺れ（ParamCielCheekJiggleL）は、
package-runtime.py の物理演算の設定を、Unity の Cubism SDK と同じ式（CubismPhysicsSubRig.UpdateParticles）で計算して入れる。
赤み（ParamCheek）と目の細め（ParamEyeLOpen）も、Unity で入れる予定の動きで合わせる。

実行  python -I scripts/live2d/v64/preview_physics.py 書き出したモデル.model3.json 出力の名前（.gif と -strip.png）
"""
import importlib.util
import math
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cubism_core as cc  # noqa: E402


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rm = module('render_moc', HERE.parent / 'render-moc.py')
pkg = module('package_runtime', HERE / 'package-runtime.py')

FPS = 30
CROP = (1120, 1000, 1540, 1420)
SCALE = 0.9


def poke_curve():
    """押す量の列（FPS ごと）：少し待つ → 0.08 秒で押す → 0.45 秒押したまま → 0.05 秒で離す → 揺れが収まるまで"""
    out, t, dt = [], 0.0, 1.0 / FPS
    while t < 1.6:
        if t < 0.15:
            p = 0.0
        elif t < 0.23:
            p = (t - 0.15) / 0.08
        elif t < 0.68:
            p = 1.0
        elif t < 0.73:
            p = 1.0 - (t - 0.68) / 0.05
        else:
            p = 0.0
        out.append(p)
        t += dt
    return out


def jiggle(pokes, group, substeps=2):
    """Unity の物理演算と同じ式で、振り子 1 本を動かし、出力の角度 × Scale を返す（−1〜1）"""
    v0, v1 = group['Vertices']
    norm = group['Normalization']['Position']['Maximum']
    scale = group['Output'][0]['Scale']
    mob, delay_k, acc, radius = v1['Mobility'], v1['Delay'], v1['Acceleration'], v1['Radius']
    p1, vel, out = [-norm, radius], [0.0, 0.0], []
    dt = 1.0 / FPS / substeps
    for p in pokes:
        for _ in range(substeps):
            p0 = [-norm + 2 * norm * p, 0.0]   # 押す量 0〜1 を、真ん中を 0 に −norm〜norm へ
            last = p1[:]
            d = delay_k * dt * 30
            pos = [p1[0] + vel[0] * d, p1[1] + vel[1] * d + acc * d * d]
            nd = [pos[0] - p0[0], pos[1] - p0[1]]
            ln = math.hypot(*nd)
            p1 = [p0[0] + nd[0] / ln * radius, p0[1] + nd[1] / ln * radius]
            vel = [(p1[0] - last[0]) / d * mob, (p1[1] - last[1]) / d * mob]
        ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0]) - math.pi / 2
        out.append(max(-1.0, min(1.0, ang * scale)))
    return out


def main():
    model_path, out = sys.argv[1:3]
    pokes = poke_curve()
    jig = jiggle(pokes, pkg.cheek_group('L'))
    model = cc.Model(model_path)
    tex = rm.load_textures(model)
    frames, blush = [], 0.0
    for p, j in zip(pokes, jig):
        blush += ((0.35 if p > 0.5 else 0.0) - blush) * (0.5 if p > 0.5 else 0.06)
        model.reset()
        model.set({'ParamCielCheekPokeL': p, 'ParamCielCheekJiggleL': j,
                   'ParamCheek': blush, 'ParamEyeLOpen': 1.0 - 0.22 * p})
        model.update()
        frames.append(rm.render(model, tex, SCALE, CROP).convert('RGB'))
    pal = [f.convert('P', palette=Image.ADAPTIVE, colors=220) for f in frames]
    pal[0].save(out + '.gif', save_all=True, append_images=pal[1:], duration=int(1000 / FPS), loop=0)
    pick = [2, 9, 18, 22, 24, 26, 28, 32]   # ふだん・押した・押したまま・離した直後〜揺れ
    w, h = frames[0].size
    strip = Image.new('RGB', (w * 4, h * 2))
    for k, i in enumerate(pick):
        strip.paste(frames[min(i, len(frames) - 1)], ((k % 4) * w, (k // 4) * h))
    strip.save(out + '-strip.png')
    print('CHEEK_PHYSICS_PREVIEW', out, len(frames), 'frames', 'jiggle', ' '.join('%+.2f' % v for v in jig[20:36]))


if __name__ == '__main__':
    main()
