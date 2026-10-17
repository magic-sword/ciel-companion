# -*- coding: utf-8 -*-
"""ほっぺの変形を、アプリで付ける動き（押して離すと、ばねで揺れて戻る）と一緒に、GIF で試し描きする（v64）。

つつく：押す量を 0.08 秒で 1 にし、0.12 秒押したまま、離すとばね（spring.py と同じ式）で 0 へ戻る。
引っ張る：0.45 秒かけて外へ引き、0.3 秒そのまま、離すとばねで戻る（少し反対へ行き過ぎる）。

実行  python -I scripts/live2d/v64/preview_motion.py 正式モデル.cmo3 書き出したモデル.model3.json 出力.gif [--scale S]
"""
import importlib.util
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import cubism_core as cc  # noqa: E402
_spec = importlib.util.spec_from_file_location('cheek_preview', HERE / 'preview.py')
pv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pv)

FPS = 25
STIFFNESS, DAMPING = 420.0, 13.0   # ばね（1/秒²、1/秒）。小さく数回揺れて止まる


def spring(start, seconds):
    x, v, out = start, 0.0, []
    dt = 1.0 / FPS
    for _ in range(int(seconds * FPS)):
        for _ in range(8):   # 細かく刻んで積分する
            a = -STIFFNESS * x - DAMPING * v
            v += a * dt / 8
            x += v * dt / 8
        out.append(x)
    return out


def timeline():
    """（見出し、左の (poke, pull_x, pull_y)）の列"""
    frames = [('', (0, 0, 0))] * 5
    frames += [('つつく', (min(1.0, (k + 1) / 2), 0, 0)) for k in range(5)]   # 押す・押したまま
    frames += [('つつく', (x, 0, 0)) for x in spring(1.0, 0.9)]              # 離す
    frames += [('', (0, 0, 0))] * 4
    pull = [(k + 1) / 11 for k in range(11)]
    frames += [('つまんで引っ張る', (0, x, 0.15 * x)) for x in pull]
    frames += [('つまんで引っ張る', (0, 1, 0.15))] * 8
    frames += [('つまんで引っ張る', (0, x, 0.15 * x)) for x in spring(1.0, 1.0)]
    frames += [('', (0, 0, 0))] * 5
    return frames


def main():
    cmo3_path, model_path, out = sys.argv[1:4]
    scale = float(sys.argv[sys.argv.index('--scale') + 1]) if '--scale' in sys.argv else 0.45
    names = pv.members(cmo3_path)
    model = cc.Model(model_path)
    tex = pv.rm.load_textures(model)
    model.reset()
    model.update()
    images = []
    for title, left in timeline():
        model.reset()
        model.update()
        im = pv.rm.render(pv.Patched(model, names, left, (0, 0, 0)), tex, scale, pv.CROP)
        if title:
            from PIL import ImageDraw
            ImageDraw.Draw(im).text((10, 8), title, fill=(40, 60, 110), font=pv._font())
        images.append(im.convert('P', palette=Image.ADAPTIVE, colors=200))
    images[0].save(out, save_all=True, append_images=images[1:], duration=int(1000 / FPS), loop=0)
    print('CHEEK_MOTION_DONE', out, len(images), 'frames')


if __name__ == '__main__':
    main()
