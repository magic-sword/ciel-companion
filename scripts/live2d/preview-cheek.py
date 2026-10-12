# -*- coding: utf-8 -*-
"""横を向いたときの頬の形（cheek_shape.py）を、Cubism で書き出さずに試し描きする。

書き出したモデル（Face_Skin が輪郭に沿ったメッシュで、頬の形のキーがまだ正面の形のもの）を Core で角度X ±30 にし、
Face_Skin と横髪の内側の束の頂点を、cheek_shape の位置に置き換えて描く。目標の曲線も重ねて描ける（--curve）。
実行  python -I scripts/live2d/preview-cheek.py モデル.model3.json 出力.png [--curve] [--scale S] [--crop x0,y0,x1,y1]
"""
import importlib.util
import os
import sys

import numpy as np
from PIL import ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cubism_core as cc
import cheek_shape as cs

_spec = importlib.util.spec_from_file_location('render_moc', os.path.join(HERE, 'render-moc.py'))
rm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rm)


class Patched:
    def __init__(self, model, s):
        self.m, self.s = model, s
        self.canvas = model.canvas
        self.curve = None

    def drawables(self):
        ds = self.m.drawables()
        if self.s:
            for d in ds:
                if d['id'] == 'Face_Skin':
                    d['pos'], self.curve = cs.shape(d['pos'], self.s)
                elif d['id'].startswith('Hair_Side_'):
                    d['pos'] = cs.hair_shape(d['id'], d['pos'], self.s)
        return ds


def main():
    src, dst = sys.argv[1:3]
    args = sys.argv[3:]
    scale = float(args[args.index('--scale') + 1]) if '--scale' in args else 0.5
    crop = tuple(float(v) for v in args[args.index('--crop') + 1].split(',')) if '--crop' in args else (700, 850, 1550, 1500)
    model = cc.Model(src)
    tex = rm.load_textures(model)
    tiles = []
    for v in (-30, 0, 30):
        model.reset()
        model.set({'ParamAngleX': v})
        model.update()
        p = Patched(model, int(np.sign(v)))
        im = rm.render(p, tex, scale, crop)
        if '--curve' in args and p.curve is not None:
            dr = ImageDraw.Draw(im)
            c = (p.curve - np.array(crop[:2])) * scale
            dr.line([tuple(q) for q in c], fill=(255, 0, 0), width=1)
        tiles.append(im)
    w, h = tiles[0].size
    from PIL import Image
    sheet = Image.new('RGB', (w * 3, h))
    for k, t in enumerate(tiles):
        sheet.paste(t, (k * w, 0))
    sheet.save(dst)
    print('PREVIEW_CHEEK_DONE', dst)


if __name__ == '__main__':
    main()
