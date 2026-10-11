# -*- coding: utf-8 -*-
"""目の開閉（0・0.5・1）と口の開閉（0・0.5・1）のキーの不透明度を設定する（段階 4 の仮リグ）。

前提：Cubism で、目の各メッシュに「左目 開閉」「右目 開閉」、口の差分（Mouth_Small・Mouth_Large）に「口 開閉」の
キーの 3 点追加をしてある（キーの並びは値の小さい順）。
目：0 は閉じ目（*_Closed）だけ、0.5 と 1 は開いた目の層だけ（0.5 の半目の形は、後で形のキーで作る）。
口：0 は閉じた口（差分なし）、0.5 は Mouth_Small、1 は Mouth_Large。
実行  python -I scripts/live2d/blink-mouth-keys.py 入力.cmo3 出力.cmo3
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t

OPEN_LAYERS = ['Sclera', 'Iris', 'Highlight', 'LidSkin_Upper', 'LidSkin_Lower', 'LashUpper', 'LashLower', 'Crease']


def main():
    src, dst = sys.argv[1:3]
    doc = t.Cmo3(src)
    for side in 'LR':
        doc.set_keyform_opacity('Eye_%s_Closed' % side, [1, 0, 0])
        for l in OPEN_LAYERS:
            doc.set_keyform_opacity('Eye_%s_%s' % (side, l), [0, 1, 1])
    doc.set_keyform_opacity('Mouth_Small', [0, 1, 0])
    doc.set_keyform_opacity('Mouth_Large', [0, 0, 1])
    doc.save(dst)
    print('BLINK_MOUTH_KEYS_DONE')


if __name__ == '__main__':
    main()
