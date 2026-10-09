# -*- coding: utf-8 -*-
"""preview-pose.py で描いた向きを、見本（pose-ref）と並べる。上段：見本、下段：プレビュー。

実行  python -I scripts/live2d/preview-vs-ref.py 入力.cmo3 出力.png 名前[,名前...]
  名前は pose_ の後ろ（xL30_y0、x0_yU30、xR15_yD15 など）。
"""
import os
import re
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
VX = {'L30': -30, 'L15': -15, '0': 0, 'R15': 15, 'R30': 30}
VY = {'U30': 30, 'U15': 15, '0': 0, 'D15': -15, 'D30': -30}
S = 440


def main(cmo3, out, names):
    args = []
    for n in names:
        m = re.match(r'x(.+)_y(.+)$', n)
        args += [str(VX[m.group(1)]), str(VY[m.group(2)])]
    tmp = os.path.join(ROOT, '.local', 'render-check', '_pv.png')
    subprocess.check_call([sys.executable, '-I', os.path.join(HERE, 'preview-pose.py'), cmo3, tmp] + args)
    pv = Image.open(tmp).convert('RGB')
    w = pv.width // len(names)
    sheet = Image.new('RGB', (S * len(names), S * 2))
    for i, n in enumerate(names):
        if n == 'x0_y0':
            ref = Image.open(os.path.join(ROOT, 'assets/ciel/requests/face-hair-crop-1536x1536_x318_y236.png')).convert('RGBA')
            bg = Image.new('RGBA', ref.size, (255, 255, 255, 255)); bg.alpha_composite(ref); ref = bg.convert('RGB')
        else:
            ref = Image.open(os.path.join(ROOT, 'assets/ciel/generated/pose-ref/pose_%s.png' % n)).convert('RGBA')
            bg = Image.new('RGBA', ref.size, (255, 255, 255, 255)); bg.alpha_composite(ref); ref = bg.convert('RGB')
        sheet.paste(ref.resize((S, S)), (i * S, 0))
        sheet.paste(pv.crop((i * w, 0, (i + 1) * w, pv.height)).resize((S, S)), (i * S, S))
    sheet.save(out)
    print('COMPARE', out)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3].split(','))
