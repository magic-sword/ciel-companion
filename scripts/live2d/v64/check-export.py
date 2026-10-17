# -*- coding: utf-8 -*-
"""書き出したモデル（ほっぺ入り）を Core で描いて、押す・引っ張る・揺れ・赤みを並べた PNG にする（v64）。

実行  python -I scripts/live2d/v64/check-export.py 書き出したモデル.model3.json 出力.png
"""
import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cubism_core as cc  # noqa: E402

_spec = importlib.util.spec_from_file_location('render_moc', HERE.parent / 'render-moc.py')
rm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rm)

CROP = (760, 950, 1460, 1500)
SCALE = 0.6
CASES = [
    ('neutral', {}),
    ('poke L', {'ParamCielCheekPokeL': 1, 'ParamCheek': 0.35, 'ParamEyeLOpen': 0.78}),
    ('poke R', {'ParamCielCheekPokeR': 1, 'ParamCheek': 0.35, 'ParamEyeROpen': 0.78}),
    ('jiggle -1 L', {'ParamCielCheekJiggleL': -1}),
    ('jiggle +1 L', {'ParamCielCheekJiggleL': 1}),
    ('pull out L', {'ParamCielCheekPullXL': 1}),
    ('pull out+down R', {'ParamCielCheekPullXR': 1, 'ParamCielCheekPullYR': 1}),
    ('blush 1', {'ParamCheek': 1}),
]


def main():
    model_path, out = sys.argv[1:3]
    model = cc.Model(model_path)
    tex = rm.load_textures(model)
    tiles = []
    for label, params in CASES:
        model.reset()
        model.set(params)
        model.update()
        im = rm.render(model, tex, SCALE, CROP).convert('RGB')
        ImageDraw.Draw(im).text((8, 8), label, fill=(200, 0, 60))
        tiles.append(im)
    w, h = tiles[0].size
    sheet = Image.new('RGB', (w * 4, h * 2), 'white')
    for k, im in enumerate(tiles):
        sheet.paste(im, ((k % 4) * w, (k // 4) * h))
    sheet.save(out)
    print('CHECK_EXPORT_DONE', out)


if __name__ == '__main__':
    main()
