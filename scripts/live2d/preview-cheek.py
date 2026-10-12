# -*- coding: utf-8 -*-
"""横を向いたときの頬の形（cheek_shape.py）を、Cubism で書き出さずに試し描きする。

書き出したモデル（Face_Skin が輪郭に沿ったメッシュ。横髪のワープには、頬に合わせた動きがまだ入っていないもの）を Core で角度X ±30 にし、
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
    def __init__(self, model, s, rest):
        self.m, self.s, self.rest = model, s, rest
        self.canvas = model.canvas
        self.curve = None

    def drawables(self):
        ds = self.m.drawables()
        if self.s:
            by = {d['id']: d for d in ds}
            face = by['Face_Skin']
            # Face_Skin のキーに古い形が入っていても使えるように、横向きの位置は、同じ親（顔の曲面）の
            # Face_Shadow_Hair（キーは正面のまま）の動きから一次式で求め、正面の頂点に当てはめる
            r0, r1 = self.rest['Face_Shadow_Hair'], by['Face_Shadow_Hair']['pos']
            M, *_ = np.linalg.lstsq(np.c_[r0, np.ones(len(r0))], r1, rcond=None)
            fr = self.rest['Face_Skin']
            face['pos'], self.curve = cs.shape(np.c_[fr, np.ones(len(fr))] @ M, self.s)
            cdx = cs.contour_dx(self.rest['Face_Skin'], face['pos'], self.s)
            for d in ds:
                if d['id'].startswith('Hair_Side_'):
                    d['pos'] = cs.hair_shape(d['id'], d['pos'], self.rest[d['id']], self.s, cdx)
        return ds


def main():
    src, dst = sys.argv[1:3]
    args = sys.argv[3:]
    scale = float(args[args.index('--scale') + 1]) if '--scale' in args else 0.5
    crop = tuple(float(v) for v in args[args.index('--crop') + 1].split(',')) if '--crop' in args else (700, 850, 1550, 1500)
    model = cc.Model(src)
    tex = rm.load_textures(model)
    model.reset()
    model.update()
    rest = {d['id']: d['pos'].copy() for d in model.drawables()}
    tiles = []
    for v in (-30, 0, 30):
        model.reset()
        model.set({'ParamAngleX': v})
        model.update()
        p = Patched(model, int(np.sign(v)), rest)
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
