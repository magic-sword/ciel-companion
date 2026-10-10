# -*- coding: utf-8 -*-
"""アートメッシュを非表示（isVisible=false）にする。非表示のメッシュは、moc3 に書き出されない。

使い道：Face_Base（向きごとの素肌のシート）を外す。アトラス編集（ctrl+t）→ OK で、Face_Base の画像が
PSD の古いレイヤー（耳・髪・体を焼き込んだ上半身全体）から作り直され、シート用の UV と合わなくなり、
Unity で、頭の横に腕などの絵が四角く出た。素肌は、A2（首の柱は Body_Base に焼き込み済み）で補う方針。
実行  python -I scripts/live2d/hide-mesh.py 入力.cmo3 出力.cmo3 名前[,名前...]   完了表示 MESH_HIDDEN
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmo3_tool as t


def main(src, dst, names):
    d = t.Cmo3(src)
    for name in names.split(','):
        a, b = d.mesh_block(name)
        blk = d.xml[a:b]
        if '<b xs.n="isVisible">true</b>' not in blk:
            raise SystemExit('isVisible=true not found in ' + name)
        d.xml = d.xml[:a] + blk.replace('<b xs.n="isVisible">true</b>', '<b xs.n="isVisible">false</b>', 1) + d.xml[b:]
        print('hidden', name)
    d.save(dst)
    print('MESH_HIDDEN', dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
