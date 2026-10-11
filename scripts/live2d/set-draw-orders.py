# -*- coding: utf-8 -*-
"""層の一覧（psd-manifest.json の下→上の順）から、.cmo3 の全メッシュの描画順を一括で設定する。

PSD から取り込んだ直後は、全メッシュの描画順が同じ（500）で、重なりは取り込んだ順で決まる。デフォーマで階層を
変えると重なりが崩れるので、層の一覧の順に、明示的な描画順を振る（下から START、STEP ずつ）。

実行  python -I scripts/live2d/set-draw-orders.py 入力.cmo3 出力.cmo3 psd-manifest.json [START=100] [STEP=10]
Cubism で開いているファイルに直接書かない（別名で出力し、Cubism で開き直す）。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t


def main():
    src, dst, manifest = sys.argv[1:4]
    start = int(sys.argv[4]) if len(sys.argv) > 4 else 100
    step = int(sys.argv[5]) if len(sys.argv) > 5 else 10
    names = [l['name'] for l in json.load(open(manifest, encoding='utf-8-sig'))['layers']]
    doc = t.Cmo3(src)
    missing = []
    for i, name in enumerate(names):
        try:
            doc.set_draw_order(name, start + i * step)
        except KeyError:
            missing.append(name)
    doc.save(dst)
    print('SET_DRAW_ORDERS_DONE', len(names) - len(missing), 'meshes', 'missing=%s' % missing if missing else '')


if __name__ == '__main__':
    main()
