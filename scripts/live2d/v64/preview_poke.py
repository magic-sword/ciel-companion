# -*- coding: utf-8 -*-
"""ほっぺをつついたときの動きを、GIF と、コマを並べた PNG で試し描きする（v64）。

画面の右（モデルの左）のほっぺを、押す → 押したまま → 離す（ばねで揺れ戻り、少しふくらんでから止まる）。
いっしょに動かすもの：
- くぼみのまわりを押しのける変形（cheek_squish.displacement の poke。負は揺れ戻りのふくらみ）
- くぼみの影の層（Codex の Cheek_Dimple_L_<案>.png）の不透明度：押した量 × SHADE
- 頬の赤み（ParamCheek）：押すと少し上がり、ゆっくり戻る
- 押された側の目を少し細める（ParamEyeLOpen を少し閉じる。笑い目 ParamEyeLSmile の途中の値は、目が二重に見えた）

実行  python -I scripts/live2d/v64/preview_poke.py 正式モデル.cmo3 書き出したモデル.model3.json 出力の名前（.gif と -strip.png） [--shade 0.3] [--variant A]
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import cubism_core as cc  # noqa: E402

_spec = importlib.util.spec_from_file_location('cheek_preview', HERE / 'preview.py')
pv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pv)
_spec = importlib.util.spec_from_file_location('cheek_motion', HERE / 'preview_motion.py')
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)

CROP = (1120, 1000, 1540, 1420)
SCALE = 0.9


def timeline():
    """（押す量、赤み、目の細め）の列。押す量は離したあと、ばねで負（ふくらみ）にも振れる"""
    poke = [0.0] * 4 + [0.6, 1.0] + [1.0] * 4 + pm.spring(1.0, 1.0) + [0.0] * 4
    blush, out = 0.0, []
    for k, x in enumerate(poke):
        target = 0.35 if 4 <= k < 10 else 0.0
        blush += (target - blush) * (0.5 if target > blush else 0.08)   # 赤みは早く上がり、ゆっくり引く
        out.append((x, blush, 0.22 * max(x, 0.0)))
    return out


def main():
    cmo3_path, model_path, out = sys.argv[1:4]
    arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
    shade, variant = float(arg('--shade', 0.3)), arg('--variant', 'A')
    names = pv.members(cmo3_path)
    model = cc.Model(model_path)
    tex = pv.rm.load_textures(model)
    layer = Image.open(ROOT / f'assets/ciel/generated/v64/Cheek_Dimple_L_{variant}.png').convert('RGBA')
    layer = layer.crop(CROP).resize((int((CROP[2] - CROP[0]) * SCALE), int((CROP[3] - CROP[1]) * SCALE)), Image.LANCZOS)
    frames = []
    for poke, blush, squint in timeline():
        model.reset()
        model.set({'ParamCheek': blush, 'ParamEyeLOpen': 1.0 - squint})
        model.update()
        im = pv.rm.render(pv.Patched(model, names, (poke, 0, 0), (0, 0, 0)), tex, SCALE, CROP).convert('RGBA')
        a = np.asarray(layer).copy()
        a[..., 3] = (a[..., 3] * float(np.clip(poke, 0, 1)) * shade).astype(np.uint8)
        im.alpha_composite(Image.fromarray(a))
        frames.append(im.convert('RGB'))
    pal = [f.convert('P', palette=Image.ADAPTIVE, colors=220) for f in frames]
    pal[0].save(out + '.gif', save_all=True, append_images=pal[1:], duration=int(1000 / pm.FPS), loop=0)
    pick = [3, 5, 9, 11, 13, 15, 18, 24]   # ふだん・押した・押したまま・離した直後・揺れ戻り…
    w, h = frames[0].size
    strip = Image.new('RGB', (w * 4, h * 2))
    for k, i in enumerate(pick):
        strip.paste(frames[min(i, len(frames) - 1)], ((k % 4) * w, (k // 4) * h))
    strip.save(out + '-strip.png')
    print('CHEEK_POKE_DONE', out, len(frames), 'frames')


if __name__ == '__main__':
    main()
