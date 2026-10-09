"""PSD の差し替えでずれたモデル用画像の中身を、XML の参照（ファイル名）の付け替えだけで直す。

画像の PNG 本体（CAFF の中のファイル）は書き換えず、CModelImage が指す imageFileBuf_N.png の名前と
サイズ属性を入れ替える。Face_Skin ← Hair_Under_Ear の画像、のように 1 つずつずれている分を戻す。
実行  python -I scripts/live2d/rotate-model-image-files.py 入力.cmo3 出力.cmo3 受け取る側=渡す側[,...]
例    Face_Skin=Hair_Under_Ear,Ear_L=Neck_Gear,Ear_R=Chest_Gem,Hair_Under_Ear=Waist_Belt
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmo3_tool import Cmo3

IMAGE = re.compile(r'<CModelImage [^>]*>\s*<CModelImageGuid xs.n="guid" xs.ref="#\d+" />\s*<s xs.n="name">([^<]*)</s>.*?</CModelImage>', re.S)
RAW = re.compile(r'<CImageResource width="\d+" height="\d+" type="INT_ARGB" imageFileBuf_size="(\d+)" previewFileBuf_size="0" xs.id="(#\d+)" xs.idx="\d+">\s*<file xs.n="imageFileBuf" path="([^"]+)" />')
CACHE = re.compile(r'<CImageResource xs.n="_cachedImageResource" width="\d+" height="\d+" type="INT_ARGB" imageFileBuf_size="(\d+)" previewFileBuf_size="0">\s*<file xs.n="imageFileBuf" path="([^"]+)" />')


def raw_info(xml, block):
    ref = re.search(r'xs.n="_filteredImage" xs.ref="(#\d+)"', block).group(1)
    for m in RAW.finditer(xml):
        if m.group(2) == ref:
            return m
    raise KeyError(ref)


def main(src, dst, pairs):
    c = Cmo3(src)
    xml = c.xml
    blocks = {m.group(1): m for m in IMAGE.finditer(xml)}
    infos = {}
    for n, m in blocks.items():
        infos[n] = (raw_info(xml, m.group(0)), CACHE.search(m.group(0)))
    edits = []  # (start, end, text)
    for recv, give in pairs:
        raw_r, cache_r = infos[recv]
        raw_g, cache_g = infos[give]
        t = raw_r.group(0).replace('imageFileBuf_size="%s"' % raw_r.group(1), 'imageFileBuf_size="%s"' % raw_g.group(1)).replace(raw_r.group(3), raw_g.group(3))
        edits.append((raw_r.start(), raw_r.end(), t))
        base = blocks[recv].start()
        t2 = cache_r.group(0).replace('imageFileBuf_size="%s"' % cache_r.group(1), 'imageFileBuf_size="%s"' % cache_g.group(1)).replace(cache_r.group(2), cache_g.group(2))
        edits.append((base + cache_r.start(), base + cache_r.end(), t2))
        print('%s <- %s  %s %s' % (recv, give, raw_g.group(3), cache_g.group(2)))
    for s, e, t in sorted(edits, reverse=True):
        xml = xml[:s] + t + xml[e:]
    c.xml = xml
    c.save(dst)
    print('MODEL_IMAGE_FILES_ROTATED')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], [p.split('=') for p in sys.argv[3].split(',')])
