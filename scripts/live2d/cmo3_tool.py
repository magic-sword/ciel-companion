"""Cubism Editor の .cmo3 を、スクリプトで書き換える最小のツール。

CAFF のコンテナ（caff.py）→ main.xml（ストリームZIP、中身は 'contents' のXML）→ XML文字列の編集 → 書き戻し。
XMLは再整形せず、文字列の置換だけで編集する（元の記述をそのまま残す）。

使い方（Pythonから）
    import cmo3_tool as t
    doc = t.Cmo3('assets/ciel/rig/ciel-blink-test.cmo3')
    doc.set_keyform_opacity('Mouth_Small', [0.0, 1.0])     # キーごとの不透明度
    doc.save('out.cmo3')

編集前のファイルは、必ずGitなどで復元できるようにしておく。書き換えたファイルは、Cubism Editorで開いて確かめる。
"""
import io
import re
import struct
import zlib

import caff


class Cmo3:
    def __init__(self, path):
        self.caff = caff.read(path)
        self._main = next(e for e in self.caff.entries if e.name == 'main.xml')
        raw = self._main.data
        sig, ver, flag, comp, mt, md, crc, csz, usz, nl, xl = struct.unpack('<IHHHHHIIIHH', raw[:30])
        if sig != 0x04034B50 or comp != 8:
            raise ValueError('unexpected main.xml container')
        self._zip_name = raw[30:30 + nl]
        self._zip_header = raw[:30 + nl + xl]
        self._zip_version = ver
        self._zip_flag = flag
        self._zip_time, self._zip_date = mt, md
        body = raw[30 + nl + xl:]
        d = zlib.decompressobj(-15)
        self.xml = d.decompress(body).decode('utf-8')
        self._tail = d.unused_data       # データ記述子など（長さと CRC を、保存時に更新する）

    # ---- 読み取り ----
    def mesh_block(self, name):
        """ArtMesh の名前から、そのメッシュの CArtMeshSource ブロックの (開始, 終了) を返す。"""
        m = re.search(r'<CArtMeshSource xs\.id="(#\d+)"[^>]*>\s*<ACDrawableSource xs\.n="super">\s*'
                      r'<ACParameterControllableSource xs\.n="super">\s*<s xs\.n="localName">%s</s>' % re.escape(name), self.xml)
        if not m:
            raise KeyError('mesh not found: ' + name)
        end = self.xml.index('</CArtMeshSource>', m.start()) + len('</CArtMeshSource>')
        return m.start(), end

    def mesh_keyforms(self, name):
        a, b = self.mesh_block(name)
        blk = self.xml[a:b]
        k = blk.index('<carray_list xs.n="keyforms"')
        k2 = blk.index('</carray_list>', k)
        return a + k, a + k2 + len('</carray_list>')

    # ---- 編集 ----
    def set_keyform_opacity(self, mesh, opacities):
        """メッシュの、キーフォームごとの不透明度を設定する。キーの数と一致している必要がある。"""
        a, b = self.mesh_keyforms(mesh)
        blk = self.xml[a:b]
        found = re.findall(r'<f xs\.n="opacity">[\d\.\-eE]+</f>', blk)
        if len(found) != len(opacities):
            raise ValueError('%s: %d keyforms, got %d values' % (mesh, len(found), len(opacities)))
        it = iter(opacities)
        new = re.sub(r'<f xs\.n="opacity">[\d\.\-eE]+</f>', lambda m: '<f xs.n="opacity">%s</f>' % _fmt(next(it)), blk)
        self.xml = self.xml[:a] + new + self.xml[b:]

    def set_draw_order(self, mesh, value):
        """メッシュの、全キーフォームの描画順を設定する。"""
        a, b = self.mesh_keyforms(mesh)
        blk = self.xml[a:b]
        new = re.sub(r'<i xs\.n="drawOrder">-?\d+</i>', '<i xs.n="drawOrder">%d</i>' % value, blk)
        self.xml = self.xml[:a] + new + self.xml[b:]

    # ---- 保存 ----
    def save(self, path):
        data = self.xml.encode('utf-8')
        comp = zlib.compressobj(6, zlib.DEFLATED, -15)
        body = comp.compress(data) + comp.flush()
        crc = zlib.crc32(data) & 0xFFFFFFFF
        # ローカルヘッダ（データ記述子つき：サイズとCRCは 0）は、元のまま。末尾にデータ記述子を付ける。
        desc = struct.pack('<IIII', 0x08074B50, crc, len(body), len(data))
        self._main.data = self._zip_header + body + desc
        caff.write(self.caff, path)


def _fmt(v):
    s = repr(float(v))
    return s


if __name__ == '__main__':
    import sys
    print(__doc__)
