# -*- coding: utf-8 -*-
"""ほっぺの変形（cheek_squish.py）を、Cubism で書き出さずに試し描きする（v64）。

書き出したモデルを Core で計算し、顔の曲面・口の曲面・鼻の曲面の下のメッシュの頂点を、ほっぺのワープ
（格子のマスでの双一次補間）で動かしてから描く。頭の傾き（角度Z）は 0 のときだけ正しい（ワープは顔の回転の下に入るため）。

実行  python -I scripts/live2d/v64/preview.py 正式モデル.cmo3 書き出したモデル.model3.json 出力.png [--scale S]
"""
import importlib.util
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import cmo3_tool as t
import cubism_core as cc
import cheek_squish as cs

_spec = importlib.util.spec_from_file_location('render_moc', HERE.parent / 'render-moc.py')
rm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rm)

PARENTS = ('顔の曲面', '口の曲面', '鼻の曲面')   # ほっぺのワープの子にするワープ
CROP = (700, 820, 1520, 1500)
if '--zoom' in sys.argv:   # 画面の右（モデルの左）のほっぺを拡大
    CROP = (1120, 1000, 1540, 1420)

# 並べる場面：（見出し、Core に渡すパラメーター、左の poke・pull_x・pull_y、右の poke・pull_x・pull_y）
SCENES = [
    ('ふだん', {}, (0, 0, 0), (0, 0, 0)),
    ('左を押す', {}, (1, 0, 0), (0, 0, 0)),
    ('右を押す', {}, (0, 0, 0), (1, 0, 0)),
    ('左を外へ引く', {}, (0, 1, 0), (0, 0, 0)),
    ('左を外・下へ引く', {}, (0, 0.8, 0.8), (0, 0, 0)),
    ('右を外・上へ引く', {}, (0, 0, 0), (0, 1, -0.6)),
    ('右を向いて左を押す', {'ParamAngleX': 30}, (1, 0, 0), (0, 0, 0)),
    ('嬉しい顔で右を引く', {'ParamHappy': 1, 'ParamEyeLSmile': 1, 'ParamEyeRSmile': 1}, (0, 0, 0), (0, 1, 0)),
]


def members(cmo3_path):
    """PARENTS のワープの直接の子のメッシュの名前"""
    doc = t.Cmo3(cmo3_path)
    x = doc.xml
    doc_guid = {doc.warp_info(name)['guid']: name for name in PARENTS}
    out = set()
    for m in re.finditer(r'<CArtMeshSource xs\.id="#\d+"', x):
        end = x.index('</CArtMeshSource>', m.start())
        blk = x[m.start():end]
        name = re.search(r'<s xs\.n="localName">([^<]*)</s>', blk).group(1)
        target = re.search(r'<CDeformerGuid xs\.n="targetDeformerGuid" xs\.ref="(#\d+)"', blk)
        if target and target.group(1) in doc_guid:
            out.add(name)
    return out


class Patched:
    def __init__(self, model, names, left, right):
        self.m, self.names = model, names
        self.canvas = model.canvas
        g = cs.grid()
        self.grid = g + cs.displacement(g, 'L', *left) + cs.displacement(g, 'R', *right)

    def drawables(self):
        ds = self.m.drawables()
        for d in ds:
            if d['id'] in self.names:
                d['pos'] = cs.warp_points(d['pos'], self.grid)
        return ds


def main():
    cmo3_path, model_path, out = sys.argv[1:4]
    scale = float(sys.argv[sys.argv.index('--scale') + 1]) if '--scale' in sys.argv else 0.5
    names = members(cmo3_path)
    print('ほっぺのワープの子になるメッシュ：%d 個' % len(names))
    model = cc.Model(model_path)
    tex = rm.load_textures(model)
    tiles = []
    for title, params, left, right in SCENES:
        model.reset()
        model.set(params)
        model.update()
        im = rm.render(Patched(model, names, left, right), tex, scale, CROP)
        ImageDraw.Draw(im).text((8, 6), title, fill=(255, 255, 255), font=_font())
        tiles.append(im)
    w, h = tiles[0].size
    cols = 4
    sheet = Image.new('RGB', (w * cols, h * ((len(tiles) + cols - 1) // cols)))
    for k, tile in enumerate(tiles):
        sheet.paste(tile, ((k % cols) * w, (k // cols) * h))
    sheet.save(out)
    print('CHEEK_PREVIEW_DONE', out)


def _font():
    for path in ('C:/Windows/Fonts/YuGothM.ttc', 'C:/Windows/Fonts/meiryo.ttc'):
        try:
            return ImageFont.truetype(path, 22)
        except OSError:
            pass
    return ImageFont.load_default()


if __name__ == '__main__':
    main()
