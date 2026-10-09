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
import uuid
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


    def _next_ids(self):
        ids = [int(x) for x in re.findall(r'xs\.id="#(\d+)"', self.xml)]
        idxs = [int(x) for x in re.findall(r'xs\.idx="(\d+)"', self.xml)]
        return max(ids) + 1, max(idxs) + 1

    def mesh_id(self, name):
        a, b = self.mesh_block(name)
        return re.match(r'<CArtMeshSource xs\.id="(#\d+)"', self.xml[a:b]).group(1)

    def mesh_grid_and_binding(self, mesh):
        """メッシュの KeyformGridSource の xs.id と、その唯一の KeyformBindingSource の xs.id を返す。"""
        a, b = self.mesh_block(mesh)
        grid = re.search(r'<KeyformGridSource xs\.n="keyformGridSource" xs\.ref="(#\d+)"', self.xml[a:b]).group(1)
        ga = self.xml.index('<KeyformGridSource xs.id="%s"' % grid)
        gb = self.xml.index('</KeyformGridSource>', ga)
        binds = set(re.findall(r'KeyformBindingSource xs\.ref="(#\d+)"', self.xml[ga:gb]))
        if len(binds) != 1:
            raise ValueError('%s: expected one binding, found %s' % (mesh, binds))
        return grid, binds.pop()

    def insert_keyform(self, mesh, key_index, key_value, opacity):
        """メッシュに、キーを 1 つ挿入する。key_index は、挿入後の、キーの位置（0 始まり）。
        既存のキーフォーム（直前のキー）を複製し、不透明度だけ変える。パラメーターのキーの値（key_value）も挿入する。"""
        NL = chr(10)
        grid, bind = self.mesh_grid_and_binding(mesh)
        new_id, new_idx = self._next_ids()
        new_ref = '#%d' % new_id

        # 1) 形のコピー元：直前のキー（なければ先頭）の CArtMeshForm
        a, b = self.mesh_keyforms(mesh)
        blk = self.xml[a:b]
        forms = [m for m in re.finditer(r'<CArtMeshForm>.*?</CArtMeshForm>', blk, flags=re.S)]
        src = forms[key_index - 1] if key_index > 0 else forms[0]
        form = src.group(0)
        form = re.sub(r'<CFormGuid xs\.n="guid" xs\.ref="#\d+" />', '<CFormGuid xs.n="guid" xs.ref="%s" />' % new_ref, form)
        form = re.sub(r'<f xs\.n="opacity">[\d\.\-eE]+</f>', '<f xs.n="opacity">%s</f>' % _fmt(opacity), form)
        if key_index < len(forms):
            ins = forms[key_index].start()
            blk2 = blk[:ins] + form + NL + NL + blk[ins:]
        else:
            ins = forms[-1].end()
            blk2 = blk[:ins] + NL + NL + form + blk[ins:]
        blk2 = re.sub(r'(<carray_list xs\.n="keyforms" count=")\d+(")', lambda m: m.group(1) + str(len(forms) + 1) + m.group(2), blk2, count=1)
        self.xml = self.xml[:a] + blk2 + self.xml[b:]

        # 2) CFormGuid の定義を、コピー元のキーの定義の後ろに足す
        prev_ref = re.search(r'<CFormGuid xs\.n="guid" xs\.ref="(#\d+)" />', src.group(0)).group(1)
        dm = re.search(r'<CFormGuid uuid="[^"]*"[^>]*xs\.id="%s"[^>]*/>' % re.escape(prev_ref), self.xml)
        define = '<CFormGuid uuid="%s" note="Key [  ]" xs.id="%s" xs.idx="%d" />' % (uuid.uuid4(), new_ref, new_idx)
        self.xml = self.xml[:dm.end()] + NL + NL + define + self.xml[dm.end():]

        # 3) KeyformGridSource：KeyformOnGrid を足し、後ろの keyIndex をずらす
        ga = self.xml.index('<KeyformGridSource xs.id="%s"' % grid)
        gb = self.xml.index('</KeyformGridSource>', ga)
        gblk = self.xml[ga:gb]
        items = list(re.finditer(r'<KeyformOnGrid>.*?</KeyformOnGrid>', gblk, flags=re.S))
        new_item = items[min(key_index, len(items) - 1)].group(0)
        new_item = re.sub(r'<i xs\.n="keyIndex">\d+</i>', '<i xs.n="keyIndex">%d</i>' % key_index, new_item)
        new_item = re.sub(r'<CFormGuid xs\.n="keyformGuid" xs\.ref="#\d+" />', '<CFormGuid xs.n="keyformGuid" xs.ref="%s" />' % new_ref, new_item)

        def shift(m):
            i = int(m.group(1))
            return '<i xs.n="keyIndex">%d</i>' % (i + 1 if i >= key_index else i)
        shifted = [re.sub(r'<i xs\.n="keyIndex">(\d+)</i>', shift, it.group(0)) for it in items]
        new_items = shifted[:key_index] + [new_item] + shifted[key_index:]
        first, last = items[0].start(), items[-1].end()
        gblk2 = gblk[:first] + (NL + NL).join(new_items) + gblk[last:]
        gblk2 = re.sub(r'(<array_list xs\.n="keyformsOnGrid" count=")\d+(")', lambda m: m.group(1) + str(len(items) + 1) + m.group(2), gblk2, count=1)
        self.xml = self.xml[:ga] + gblk2 + self.xml[gb:]

        # 4) KeyformBindingSource：keys に値を挿入
        ba = self.xml.index('<KeyformBindingSource xs.id="%s"' % bind)
        bb = self.xml.index('</KeyformBindingSource>', ba)
        bblk = self.xml[ba:bb]
        km = re.search(r'<array_list xs\.n="keys" count="(\d+)">(.*?)</array_list>', bblk, flags=re.S)
        vals = re.findall(r'<f>([\d\.\-eE]+)</f>', km.group(2))
        vals.insert(key_index, _fmt(key_value))
        keys_xml = '<array_list xs.n="keys" count="%d">' % len(vals) + NL + NL + (NL + NL).join('<f>%s</f>' % v for v in vals) + NL + NL + '</array_list>'
        bblk2 = bblk[:km.start()] + keys_xml + bblk[km.end():]
        self.xml = self.xml[:ba] + bblk2 + self.xml[bb:]

    def crop_quad_mesh(self, mesh, bbox, canvas=(2172, 2896), margin=2):
        """4頂点（キャンバス全体を覆う四角形）のメッシュを、絵の範囲（bbox=(x0, y0, x1, y1)、画素・両端を含む）に切り詰める。
        頂点の位置（point と、全キーフォームの positions）と、UV を書き換える。頂点の並び順・三角形・キーの構造は変えない。"""
        W, H = canvas
        x0, y0, x1, y1 = bbox
        x0 = max(0, x0 - margin); y0 = max(0, y0 - margin)
        x1 = min(W - 1, x1 + margin); y1 = min(H - 1, y1 + margin)
        a, b = self.mesh_block(mesh)
        blk = self.xml[a:b]
        pt = re.search(r'<float-array xs\.n="point" count="8">([^<]*)</float-array>', blk)
        if not pt:
            raise ValueError('%s: not a 4-vertex mesh' % mesh)
        old = [float(v) for v in pt.group(1).split()]
        # 元の四角形（point）は、(W+1, -1)・(-1, -1)・(W+1, H+1)・(-1, H+1) の順（実ファイルで確認）。
        # 頂点ごとに、x と y のどちら側（小さい側 / 大きい側）かを見て、同じ側へ、新しい矩形の端を割り当てる。
        xs_new = {False: float(x0), True: float(x1 + 1)}
        ys_new = {False: float(y0), True: float(y1 + 1)}
        cx = (min(old[0::2]) + max(old[0::2])) / 2
        cy = (min(old[1::2]) + max(old[1::2])) / 2
        new = []
        for i in range(4):
            new.append(xs_new[old[2 * i] > cx])
            new.append(ys_new[old[2 * i + 1] > cy])
        txt = ' '.join(_fmt(v) for v in new)
        blk2 = re.sub(r'(<float-array xs\.n="(?:point|positions)" count="8">)[^<]*(</float-array>)',
                      lambda m: m.group(1) + txt + m.group(2), blk)
        # UV：テクスチャ（アトラス）内の位置。元の uvs は、元の四角形（全体）の、アトラス上の矩形。
        uv = re.search(r'<float-array xs\.n="uvs" count="8">([^<]*)</float-array>', blk2)
        u = [float(v) for v in uv.group(1).split()]
        uxs = sorted(set(u[0::2])); uys = sorted(set(u[1::2]))
        if len(uxs) != 2 or len(uys) != 2:
            raise ValueError('%s: unexpected uvs %s' % (mesh, u))
        # 元の頂点 i が、元の四角形のどの隅か（x 側 / y 側）が、そのまま、UV にも、対応している。
        W2 = (max(old[0::2]) - min(old[0::2]))
        H2 = (max(old[1::2]) - min(old[1::2]))
        ox, oy = min(old[0::2]), min(old[1::2])
        du = uxs[1] - uxs[0]; dv = uys[1] - uys[0]
        newuv = []
        for i in range(4):
            # 元の頂点 i の、元の四角形内での、正規化位置 → 新しい頂点の、正規化位置
            nx = (new[2 * i] - ox) / W2
            ny = (new[2 * i + 1] - oy) / H2
            # 元の UV は、(隅 → uv) の対応。新しい位置の UV は、同じ、隅の対応を、線形補間する
            bu = u[0::2]; bv = u[1::2]
            # 元の四角形の隅 j の UV を、(sx, sy) 側で区別して、補間する
            def corner(sx, sy):
                for j in range(4):
                    if (old[2 * j] > cx) == sx and (old[2 * j + 1] > cy) == sy:
                        return bu[j], bv[j]
            u00, v00 = corner(False, False); u10, v10 = corner(True, False)
            u01, v01 = corner(False, True); u11, v11 = corner(True, True)
            uu = (u00 * (1 - nx) * (1 - ny) + u10 * nx * (1 - ny) + u01 * (1 - nx) * ny + u11 * nx * ny)
            vv = (v00 * (1 - nx) * (1 - ny) + v10 * nx * (1 - ny) + v01 * (1 - nx) * ny + v11 * nx * ny)
            newuv += [uu, vv]
        uvtxt = ' '.join(_fmt(v) for v in newuv)
        blk2 = re.sub(r'(<float-array xs\.n="uvs" count="8">)[^<]*(</float-array>)', lambda m: m.group(1) + uvtxt + m.group(2), blk2)
        self.xml = self.xml[:a] + blk2 + self.xml[b:]

    def warp_info(self, name):
        """ワープデフォーマの、xs.id・guid（CDeformerGuid の ref）・CoordType（デフォーマ座標）・元の格子の範囲を返す。"""
        x = self.xml
        i = x.index('<s xs.n="localName">%s</s>' % name)
        st = x.rfind('<CWarpDeformerSource', 0, i)
        en = x.index('</CWarpDeformerSource>', i)
        seg = x[st:en]
        wid = re.match(r'<CWarpDeformerSource xs\.id="(#\d+)"', seg).group(1)
        guid = re.search(r'<CDeformerGuid xs\.n="guid" xs\.ref="(#\d+)"', seg).group(1)
        coord = re.search(r'<CoordType xs\.n="coordType" xs\.ref="(#\d+)"', seg).group(1)
        orig = re.search(r'<float-array xs\.n="positions" xs\.ref="(#\d+)"', seg).group(1)
        m = re.search(r'<float-array count="\d+" xs\.id="%s"[^>]*>([^<]*)' % re.escape(orig), x)
        v = [float(q) for q in m.group(1).split()]
        xs, ys = v[0::2], v[1::2]
        return dict(id=wid, guid=guid, coord=coord, x0=min(xs), x1=max(xs), y0=min(ys), y1=max(ys))

    def move_mesh_into_warp(self, mesh, warp_name):
        """メッシュを、ワープデフォーマの子にする。targetDeformerGuid と、全キーフォームの CoordType・positions を、
        デフォーマの正規化座標（元の格子の範囲を 0〜1）へ変換する。point（元の画像座標）と uvs は、変えない。"""
        w = self.warp_info(warp_name)
        a, b = self.mesh_block(mesh)
        blk = self.xml[a:b]
        blk = re.sub(r'(<CDeformerGuid xs\.n="targetDeformerGuid" xs\.ref=")#\d+(")', lambda m: m.group(1) + w['guid'] + m.group(2), blk)
        W = w['x1'] - w['x0']
        H = w['y1'] - w['y0']

        def conv(m):
            vals = [float(q) for q in m.group(2).split()]
            out = []
            for i in range(0, len(vals), 2):
                out += [(vals[i] - w['x0']) / W, (vals[i + 1] - w['y0']) / H]
            return m.group(1) + ' '.join(_fmt(v) for v in out) + m.group(3)
        # keyforms の中の positions だけを変換する（メッシュ直下の positions は、元のまま）
        k = blk.index('<carray_list xs.n="keyforms"')
        k2 = blk.index('</carray_list>', k) + len('</carray_list>')
        kf = blk[k:k2]
        kf = re.sub(r'(<float-array xs\.n="positions" count="\d+">)([^<]*)(</float-array>)', conv, kf)
        kf = re.sub(r'(<CoordType xs\.n="coordType" xs\.ref=")#\d+(")', lambda m: m.group(1) + w['coord'] + m.group(2), kf)
        blk = blk[:k] + kf + blk[k2:]
        self.xml = self.xml[:a] + blk + self.xml[b:]

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
