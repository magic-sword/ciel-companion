# -*- coding: utf-8 -*-
"""v6 のパーツ（`generated/v6/parts/<名前>.png`）を位置合わせして、作業キャンバスに組み立てる。

各パーツは `register-part.py` で基準画像に合わせ、`assets/ciel/layers/v6/<名前>.png`（2172×2896、Git 管理外）に置く。
すでに置いたパーツは、`--redo` を付けない限り位置合わせをやり直さない。最後に、重なり順に重ねた確認図を出す。

実行  python -I scripts/live2d/assemble-v6.py [--redo 名前,名前] [--only 名前,名前]
出力  assets/ciel/layers/v6/*.png・*.json・*.check.png、assets/ciel/layers/v6/_compose.png（全体）、_compose-head.png（頭）
"""
import json
import os
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
V6 = os.path.join(ROOT, 'assets', 'ciel', 'generated', 'v6')
OUT = os.path.join(ROOT, 'assets', 'ciel', 'layers', 'v6')

# 重なり順（下から）。設計書 5 章に合わせる
ORDER = ['Hair_Back_R', 'Hair_Back_L', 'Hair_Back_Upper', 'Body_Torso', 'Body_Skirt', 'Body_Belt',
         'Jacket_R', 'Jacket_L', 'Fur_Collar_R', 'Fur_Collar_L', 'Neck', 'Choker', 'Chest_Gem',
         'Hair_Side_R_Outer', 'Hair_Side_L_Outer', 'Ear_R', 'Ear_L', 'Hair_Crown', 'Face_Skin',
         'Nose', 'Mouth', 'Eye_R', 'Eye_L', 'Hair_Side_R_Inner', 'Hair_Side_L_Inner', 'Hair_Side_R', 'Hair_Side_L',
         'Hair_Front', 'Brow_R', 'Brow_L', 'Hair_Ahoge']


def main():
    args = sys.argv[1:]
    redo = set(args[args.index('--redo') + 1].split(',')) if '--redo' in args else set()
    only = set(args[args.index('--only') + 1].split(',')) if '--only' in args else None
    units = json.load(open(os.path.join(V6, 'units.json'), encoding='utf-8'))
    os.makedirs(OUT, exist_ok=True)
    # 手で決めた置き方（倍率, 回転[度], 中心x, 中心y）。自動の位置合わせが合わないパーツだけ
    fp = os.path.join(V6, 'placement-fixed.json')
    fixed = json.load(open(fp, encoding='utf-8')) if os.path.exists(fp) else {}
    placed = []
    for name in ORDER:
        src = os.path.join(V6, 'parts', name + '.png')
        if not os.path.exists(src) or (only and name not in only):
            continue
        dst = os.path.join(OUT, name + '.png')
        box_name = name if name in units else name.rsplit('_', 1)[0]
        if not os.path.exists(dst) or name in redo:
            box = ','.join(str(v) for v in units[box_name])
            cmd = [sys.executable, '-I', os.path.join(HERE, 'register-part.py'), src, box, dst]
            if name in fixed:
                cmd += ['--fixed', ','.join(str(v) for v in fixed[name])]
            r = subprocess.run(cmd,
                               capture_output=True, text=True, encoding='utf-8')
            print(name, (r.stdout.strip().splitlines() or ['?'])[-1], r.stderr.strip()[-300:])
        placed.append(name)
    if not placed:
        print('NO_PARTS')
        return
    canvas = Image.new('RGBA', (2172, 2896), (64, 72, 104, 255))
    for name in placed:
        canvas.alpha_composite(Image.open(os.path.join(OUT, name + '.png')).convert('RGBA'))
    canvas.convert('RGB').resize((1086, 1448), Image.LANCZOS).save(os.path.join(OUT, '_compose.png'))
    canvas.crop((300, 0, 1880, 1600)).convert('RGB').resize((790, 800), Image.LANCZOS).save(os.path.join(OUT, '_compose-head.png'))
    print('ASSEMBLE_V6_DONE', len(placed), 'parts')


if __name__ == '__main__':
    main()
