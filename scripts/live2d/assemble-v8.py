# -*- coding: utf-8 -*-
"""Codex がパーツ単体を同じ枠で描いた画像（`generated/v8/parts/`）を、枠の座標でキャンバス（2172×2896）へ戻して重ねる（計画書 8.2）。

実行  python -I scripts/live2d/assemble-v8.py [--alt 名前,名前]   （--alt：そのパーツは -alt 版を使う）
出力  assets/ciel/layers/v8/<名前>.png、_compose.png（重ね）、_check.png（元の絵と並べた図）、_exploded.png（分解図）
"""
import json
import os
import sys

from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
V8 = os.path.join(ROOT, 'assets', 'ciel', 'generated', 'v8')
OUT = os.path.join(ROOT, 'assets', 'ciel', 'layers', 'v8')
MASTER = os.path.join(ROOT, 'assets', 'ciel', 'master', 'ciel-upper-body-2x.png')
W, H = 2172, 2896
BG = (64, 72, 104, 255)
ORDER = ['Hair_Back', 'Body', 'Choker_Back', 'Neck', 'Outer_R', 'Outer_L', 'Choker', 'Face_Skin', 'Nose', 'Mouth', 'Eye_R', 'Eye_L',
         'Ear_R', 'Ear_L', 'Hair_Ahoge', 'Hair_Side_R', 'Hair_Side_L', 'Hair_Front', 'Brow_R', 'Brow_L']


def main():
    args = sys.argv[1:]
    alt = set(args[args.index('--alt') + 1].split(',')) if '--alt' in args else set()
    frames = json.load(open(os.path.join(V8, 'frames.json'), encoding='utf-8'))
    os.makedirs(OUT, exist_ok=True)
    comp = Image.new('RGBA', (W, H), BG)
    tiles = []
    for name in ORDER:
        # 描き直した版（-v2）があれば、そちらを使う
        base = name + '-v2' if os.path.exists(os.path.join(V8, 'parts', name + '-v2.png')) else name
        src = os.path.join(V8, 'parts', base + ('-alt' if name in alt else '') + '.png')
        if not os.path.exists(src):
            print('MISSING', name)
            continue
        im = Image.open(src).convert('RGBA')
        x0, y0, x1, y1 = frames[name]['box']
        fw, fh = x1 - x0, y1 - y0
        r_out, r_frame = im.width / im.height, fw / fh
        if abs(r_out / r_frame - 1) > 0.03:
            print('RATIO_MISMATCH', name, '%.3f vs %.3f' % (r_out, r_frame))
        part = im.resize((fw, fh), Image.LANCZOS)
        layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        layer.paste(part, (x0, y0))      # はみ出す所は切れる（キャンバスの外）
        layer.save(os.path.join(OUT, name + '.png'))
        comp.alpha_composite(layer)
        t = im.copy()
        t.thumbnail((300, 300))
        tile = Image.new('RGBA', (300, 320), BG)
        tile.alpha_composite(t, ((300 - t.width) // 2, (300 - t.height) // 2))
        tiles.append(tile)
    comp.convert('RGB').save(os.path.join(OUT, '_compose.png'))
    m = Image.open(MASTER).convert('RGBA')
    o = Image.new('RGBA', (W, H), BG)
    o.alpha_composite(m)
    sheet = Image.new('RGB', (W * 2, H))
    sheet.paste(o.convert('RGB'), (0, 0))
    sheet.paste(comp.convert('RGB'), (W, 0))
    sheet.resize((W, H // 2)).save(os.path.join(OUT, '_check.png'))
    head = Image.new('RGB', (1536 * 2, 1536))
    head.paste(o.crop((318, 236, 1854, 1772)).convert('RGB'), (0, 0))
    head.paste(comp.crop((318, 236, 1854, 1772)).convert('RGB'), (1536, 0))
    head.resize((1536, 768)).save(os.path.join(OUT, '_check-head.png'))
    ex = Image.new('RGB', (300 * 7, 320 * 3), (30, 30, 30))
    for i, t in enumerate(tiles):
        ex.paste(t.convert('RGB'), ((i % 7) * 300, (i // 7) * 320))
    ex.save(os.path.join(OUT, '_exploded.png'))
    print('ASSEMBLE_V8_DONE', len(ORDER))


if __name__ == '__main__':
    main()
