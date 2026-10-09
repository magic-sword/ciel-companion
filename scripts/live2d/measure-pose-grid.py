"""頭の向きの見本 25 枚（左右 5 段階 × 上下 5 段階）から、虹彩の位置を測り、X と Y が足し算で表せるか確かめる。

入力  assets/ciel/requests/face-hair-crop-1536x1536_x318_y236.png（正面）、assets/ciel/generated/pose-ref/pose_x*_y*.png
出力  標準出力に表、assets/ciel/pose-grid-measure.json
実行  python -I scripts/live2d/measure-pose-grid.py
ファイル名：pose_x{L30,L15,0,R15,R30}_y{U30,U15,0,D15,D30}.png（L・R は画面の左・右、U・D は上・下を向く）
"""
import importlib.util
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('mht', os.path.join(HERE, 'measure-head-turn.py'))
mht = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mht)
ROOT = mht.ROOT
XS = ['L30', 'L15', '0', 'R15', 'R30']
YS = ['U30', 'U15', '0', 'D15', 'D30']


def path(x, y):
    if x == '0' and y == '0':
        return 'requests/face-hair-crop-1536x1536_x318_y236.png'
    return 'generated/pose-ref/pose_x%s_y%s.png' % (x, y)


def main():
    res = {}
    for y in YS:
        for x in XS:
            b = mht.iris_blobs(mht.load(path(x, y)))
            res['x%s_y%s' % (x, y)] = b
    cx = lambda k: (res[k][0]['x'] + res[k][1]['x']) / 2 if len(res[k]) == 2 else float('nan')
    cy = lambda k: (res[k][0]['y'] + res[k][1]['y']) / 2 if len(res[k]) == 2 else float('nan')
    gap = lambda k: (res[k][1]['x'] - res[k][0]['x']) if len(res[k]) == 2 else float('nan')
    print('両目の中心 x（行=上下、列=左右）')
    print('      ' + ' '.join('%7s' % ('x' + x) for x in XS))
    for y in YS:
        print('%-6s' % ('y' + y) + ' '.join('%7.0f' % cx('x%s_y%s' % (x, y)) for x in XS))
    print('両目の中心 y')
    for y in YS:
        print('%-6s' % ('y' + y) + ' '.join('%7.0f' % cy('x%s_y%s' % (x, y)) for x in XS))
    print('両目の間隔（x）')
    for y in YS:
        print('%-6s' % ('y' + y) + ' '.join('%7.0f' % gap('x%s_y%s' % (x, y)) for x in XS))
    print('足し算とのずれ（実測 − (X だけ + Y だけ − 正面)）  x方向 / y方向')
    f = 'x0_y0'
    for y in YS:
        row = []
        for x in XS:
            if x == '0' or y == '0':
                row.append('      -      ')
                continue
            k = 'x%s_y%s' % (x, y)
            px = cx('x%s_y0' % x) + cx('x0_y%s' % y) - cx(f)
            py = cy('x%s_y0' % x) + cy('x0_y%s' % y) - cy(f)
            row.append('%+5.0f/%+5.0f ' % (cx(k) - px, cy(k) - py))
        print('%-6s' % ('y' + y) + ' '.join(row))
    with open(os.path.join(ROOT, 'pose-grid-measure.json'), 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
