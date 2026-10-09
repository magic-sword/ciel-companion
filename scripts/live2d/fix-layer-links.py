"""モデル用画像（CModelImage）が参照している PSD のレイヤーを、名前の一致するレイヤーへ付け替える。

PSD を差し替えたあと、レイヤーの順番がずれて、Face_Skin の画像に Mouth_Large のレイヤーが
結び付いてしまったことがあった。その修復用。
実行  python -I scripts/live2d/fix-layer-links.py 入力.cmo3 出力.cmo3
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmo3_tool import Cmo3

IMAGE = re.compile(r'<CModelImage [^>]*>\s*<CModelImageGuid xs.n="guid" xs.ref="#\d+" />\s*<s xs.n="name">([^<]*)</s>.*?</CModelImage>', re.S)


def main(src, dst):
    c = Cmo3(src)
    layer_by_name = {}
    for m in re.finditer(r'<CLayer xs.id="(#\d+)"[^>]*>(.*?)</CLayer>', c.xml, flags=re.S):
        nm = re.search(r'<s xs.n="name">([^<]*)', m.group(2))
        if nm:
            layer_by_name[nm.group(1)] = m.group(1)
    fixed = []

    def fix(m):
        body = m.group(0)
        want = layer_by_name.get(m.group(1))
        cur = re.search(r'<CLayer xs.n="layer" xs.ref="(#\d+)"', body)
        if want and cur and cur.group(1) != want:
            fixed.append((m.group(1), cur.group(1), want))
            body = body.replace('<CLayer xs.n="layer" xs.ref="%s"' % cur.group(1), '<CLayer xs.n="layer" xs.ref="%s"' % want)
        return body

    c.xml = IMAGE.sub(fix, c.xml)
    c.save(dst)
    for f in fixed:
        print('fixed', f)
    print('LAYER_LINKS_FIXED', len(fixed))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
