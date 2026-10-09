"""モデル用画像の PNG を、元と同じバイト数に揃えて差し替える（Cubism が開けるようにするため）。

CAFF 内のファイルの大きさを変えると Cubism が開けなかったので、新しい PNG が元より小さいときは、
PNG の終端（IEND）の後ろを 0 で埋めて、元の大きさに合わせる（PNG の読み込みは終端で止まる）。
実行  python -I scripts/live2d/replace-image-same-size.py 入力.cmo3 出力.cmo3 名前[,名前...]
  名前は CModelImage の名前。元寸の画像とキャッシュ（半分）の両方を差し替える。
"""
import glob
import io
import os
import re
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmo3_tool import Cmo3

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel', 'layers')
IMAGE = re.compile(r'<CModelImage [^>]*>\s*<CModelImageGuid xs.n="guid" xs.ref="#\d+" />\s*<s xs.n="name">([^<]*)</s>.*?</CModelImage>', re.S)


def fit(im, size):
    best = None
    for level in (9, 6, 3, 1):
        b = io.BytesIO()
        im.save(b, 'PNG', compress_level=level, optimize=(level == 9))
        data = b.getvalue()
        if len(data) <= size:
            return data + b'\x00' * (size - len(data))
        best = data
    raise ValueError('PNG が元より大きい: %d > %d' % (len(best), size))


def set_entry(c, path, data):
    e = [e for e in c.caff.entries if e.name == path][0]
    assert len(e.data) == len(data), (path, len(e.data), len(data))
    e.data = data


def main(src, dst, names):
    c = Cmo3(src)
    for name in names:
        m = [mm for mm in IMAGE.finditer(c.xml) if mm.group(1) == name][0]
        block = m.group(0)
        fid = re.search(r'<CImageResource xs.n="_filteredImage" xs.ref="(#\d+)"', block).group(1)
        raw = re.search(r'<CImageResource [^>]*xs.id="%s"[^>]*>\s*<file xs.n="imageFileBuf" path="([^"]+)"' % fid, c.xml).group(1)
        cache = re.search(r'<CImageResource xs.n="_cachedImageResource" width="\d+" height="\d+" type="INT_ARGB" imageFileBuf_size="\d+" previewFileBuf_size="\d+">\s*<file xs.n="imageFileBuf" path="([^"]+)"', block).group(1)
        full = Image.open(glob.glob(os.path.join(ROOT, '*', name + '.png'))[0]).convert('RGBA')
        old_raw = [e for e in c.caff.entries if e.name == raw][0]
        old_cache = [e for e in c.caff.entries if e.name == cache][0]
        set_entry(c, raw, fit(full, len(old_raw.data)))
        ow, oh = struct.unpack('>II', old_cache.data[16:24])
        half = full.resize((full.width // 2, full.height // 2), Image.LANCZOS)
        pad = Image.new('RGBA', (ow, oh), (0, 0, 0, 0))
        pad.paste(half, (0, 0))
        set_entry(c, cache, fit(pad, len(old_cache.data)))
        print('replaced', name, raw, cache)
    c.save(dst)
    print('IMAGES_REPLACED_SAME_SIZE')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3].split(','))
