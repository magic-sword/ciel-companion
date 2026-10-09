"""お手本（pose-ref）と、Unity での描画（.local/render-check/pose_*.png）を、上下に並べた比較画像にする。

実行  python -I scripts/live2d/compare-pose.py 出力.png 名前[,名前...]   例: x0_yU30,x0_yU15,x0_yD15,x0_yD30
描画の画像の切り出し：CielRenderCheck のカメラ（高さ 1.5、768x1024）で、お手本と同じ範囲（キャンバスの x318・y236、1536 四方）。
"""
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
S = 440


def main(out, names):
    sheet = Image.new('RGB', (S * len(names), S * 2 + 24), 'white')
    for i, n in enumerate(names):
        ref = Image.open(os.path.join(ROOT, 'assets/ciel/generated/pose-ref/pose_%s.png' % n)).convert('RGB').resize((S, S))
        r = Image.open(os.path.join(ROOT, '.local/render-check/pose_%s.png' % n)).convert('RGB').crop((143, 131, 625, 614)).resize((S, S))
        sheet.paste(ref, (i * S, 0))
        sheet.paste(r, (i * S, S + 24))
        ImageDraw.Draw(sheet).text((i * S + 6, S + 6), n, fill=(0, 0, 0))
    sheet.save(out)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2].split(','))
