"""cmo3_tool.Cmo3 に対する、メッシュの細分化・切り詰めと、ワープデフォーマの格子の作り直し。

remesh_quad(doc, mesh, bbox, nx, ny)
    4頂点の四角形メッシュを、絵の範囲 bbox（画像座標 x0, y0, x1, y1）に切り詰めて、nx×ny のマス目に分ける。
    頂点が増えるので、ワープデフォーマの曲面に沿って、絵が曲がる（4頂点のままだと、四隅だけで決まる平らな変形になる）。
    point・uvs・indices・全キーフォームの positions を、四隅からの双線形補間で作り直す。
    親のデフォーマの座標（正規化座標）でも、画像座標でも、同じ式で動く。
retarget_warp(doc, name, x0, x1, y0, y1, col, row)
    ワープデフォーマの格子の範囲と分割数を変える。子のメッシュの positions は、画像上の同じ位置になるように、座標を変換する。
    キーフォームの格子は、新しい範囲の一様な格子に置き換える（形の情報は捨てる）。
meshes_in_warp(doc, name)
    ワープデフォーマを親に持つメッシュの名前の一覧。
"""
import re

from cmo3_tool import _fmt


def _arr(blk, name):
    m = re.search(r'<float-array xs\.n="%s" count="\d+">([^<]*)</float-array>' % name, blk)
    return [float(v) for v in m.group(1).split()]


def _bilinear(corners, tx, ty):
    """corners[(sx, sy)] = (a, b)。sx, sy は、小さい側が False・大きい側が True。"""
    out = []
    for k in range(len(corners[(False, False)])):
        out.append(corners[(False, False)][k] * (1 - tx) * (1 - ty) + corners[(True, False)][k] * tx * (1 - ty)
                   + corners[(False, True)][k] * (1 - tx) * ty + corners[(True, True)][k] * tx * ty)
    return out


def meshes_in_warp(doc, name):
    guid = doc.warp_info(name)['guid']
    res = []
    for m in re.finditer(r'<CArtMeshSource xs\.id="#\d+"[^>]*>.*?<s xs\.n="localName">([^<]*)</s>', doc.xml, flags=re.S):
        a, b = doc.mesh_block(m.group(1))
        if re.search(r'<CDeformerGuid xs\.n="targetDeformerGuid" xs\.ref="%s"' % re.escape(guid), doc.xml[a:b]):
            res.append(m.group(1))
    return res


def remesh_quad(doc, mesh, bbox, nx, ny):
    a, b = doc.mesh_block(mesh)
    blk = doc.xml[a:b]
    pt = re.search(r'(<float-array xs\.n="point" count=")(\d+)(">)([^<]*)(</float-array>)', blk)
    if pt.group(2) != '8':
        raise ValueError('%s: not a 4-vertex mesh' % mesh)
    P = [float(v) for v in pt.group(4).split()]
    px, py = P[0::2], P[1::2]
    X0, X1, Y0, Y1 = min(px), max(px), min(py), max(py)
    cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
    side = [(px[i] > cx, py[i] > cy) for i in range(4)]
    bx0, by0, bx1, by1 = bbox
    bx0, by0 = max(bx0, X0), max(by0, Y0)
    bx1, by1 = min(bx1, X1), min(by1, Y1)

    # 新しい頂点の画像座標と、四角形内の位置 (tx, ty)
    xs = [bx0 + (bx1 - bx0) * i / nx for i in range(nx + 1)]
    ys = [by0 + (by1 - by0) * j / ny for j in range(ny + 1)]
    params = [((x - X0) / (X1 - X0), (y - Y0) / (Y1 - Y0)) for y in ys for x in xs]
    n = len(params)

    def interp(vals):
        corners = {side[i]: (vals[2 * i], vals[2 * i + 1]) for i in range(4)}
        out = []
        for tx, ty in params:
            out += _bilinear(corners, tx, ty)
        return out

    def txt(v):
        return ' '.join(_fmt(q) for q in v)

    # 三角形・辺（元の向き：左上・右上・右下 と 右下・左下・左上。対角は 左上-右下）
    idx, edges, eprio = [], [], []
    w = nx + 1
    for j in range(ny + 1):
        for i in range(nx + 1):
            v = j * w + i
            if i < nx:
                edges.append((v, v + 1)); eprio.append(30 if j in (0, ny) else 10)
            if j < ny:
                edges.append((v, v + w)); eprio.append(30 if i in (0, nx) else 10)
            if i < nx and j < ny:
                edges.append((v, v + w + 1)); eprio.append(10)
                idx += [v, v + 1, v + w + 1, v + w + 1, v + w, v]
    # 1) editable mesh
    newpt = []
    for y in ys:
        for x in xs:
            newpt += [x, y]
    blk = blk[:pt.start()] + '<float-array xs.n="point" count="%d">%s</float-array>' % (2 * n, txt(newpt)) + blk[pt.end():]
    blk = re.sub(r'<byte-array xs\.n="pointPriority" count="\d+">[^<]*</byte-array>',
                 lambda m: '<byte-array xs.n="pointPriority" count="%d">%s</byte-array>' % (n, ' '.join(['20'] * n)), blk)
    blk = re.sub(r'<short-array xs\.n="edge" count="\d+">[^<]*</short-array>',
                 lambda m: '<short-array xs.n="edge" count="%d">%s</short-array>' % (2 * len(edges), ' '.join('%d %d' % e for e in edges)), blk)
    blk = re.sub(r'<byte-array xs\.n="edgePriority" count="\d+">[^<]*</byte-array>',
                 lambda m: '<byte-array xs.n="edgePriority" count="%d">%s</byte-array>' % (len(edges), ' '.join(str(p) for p in eprio)), blk)
    blk = re.sub(r'<int-array xs\.n="pointUid" count="\d+">[^<]*</int-array>',
                 lambda m: '<int-array xs.n="pointUid" count="%d">%s</int-array>' % (n, ' '.join(str(i) for i in range(n))), blk)
    blk = re.sub(r'nextPointUid="\d+"', 'nextPointUid="%d"' % n, blk, count=1)
    # 2) indices
    blk = re.sub(r'<int-array xs\.n="indices" count="\d+">[^<]*</int-array>',
                 lambda m: '<int-array xs.n="indices" count="%d">%s</int-array>' % (len(idx), ' '.join(str(i) for i in idx)), blk)
    # 3) keyforms の positions（それぞれの四隅から）
    k = blk.index('<carray_list xs.n="keyforms"')
    k2 = blk.index('</carray_list>', k) + len('</carray_list>')
    kf = blk[k:k2]
    kf = re.sub(r'(<float-array xs\.n="positions" count=")\d+(">)([^<]*)(</float-array>)',
                lambda m: m.group(1) + str(2 * n) + m.group(2) + txt(interp([float(v) for v in m.group(3).split()])) + m.group(4), kf)
    blk = blk[:k] + kf + blk[k2:]
    # 4) メッシュ直下の positions（画像座標）と uvs
    tail = blk.index('</carray_list>', blk.index('<carray_list xs.n="keyforms"')) + len('</carray_list>')
    rest = blk[tail:]
    rest = re.sub(r'(<float-array xs\.n="positions" count=")\d+(">)([^<]*)(</float-array>)',
                  lambda m: m.group(1) + str(2 * n) + m.group(2) + txt(newpt) + m.group(4), rest, count=1)
    uv = _arr(rest, 'uvs')
    rest = re.sub(r'(<float-array xs\.n="uvs" count=")\d+(">)([^<]*)(</float-array>)',
                  lambda m: m.group(1) + str(2 * n) + m.group(2) + txt(interp(uv)) + m.group(4), rest, count=1)
    blk = blk[:tail] + rest
    doc.xml = doc.xml[:a] + blk + doc.xml[b:]


def retarget_warp(doc, name, x0, x1, y0, y1, col, row):
    w = doc.warp_info(name)
    children = meshes_in_warp(doc, name)
    ox0, ox1, oy0, oy1 = w['x0'], w['x1'], w['y0'], w['y1']
    # 子のメッシュ：正規化座標 → 画像座標（旧範囲）→ 正規化座標（新範囲）
    for m in children:
        a, b = doc.mesh_block(m)
        blk = doc.xml[a:b]
        k = blk.index('<carray_list xs.n="keyforms"')
        k2 = blk.index('</carray_list>', k) + len('</carray_list>')

        def conv(mm):
            v = [float(q) for q in mm.group(2).split()]
            out = []
            for i in range(0, len(v), 2):
                cx = ox0 + v[i] * (ox1 - ox0)
                cy = oy0 + v[i + 1] * (oy1 - oy0)
                out += [(cx - x0) / (x1 - x0), (cy - y0) / (y1 - y0)]
            return mm.group(1) + ' '.join(_fmt(q) for q in out) + mm.group(3)
        kf = re.sub(r'(<float-array xs\.n="positions" count="\d+">)([^<]*)(</float-array>)', conv, blk[k:k2])
        blk = blk[:k] + kf + blk[k2:]
        doc.xml = doc.xml[:a] + blk + doc.xml[b:]
    # 元の格子（形を持たない基準の格子）
    pts = []
    for j in range(row + 1):
        for i in range(col + 1):
            pts += [x0 + (x1 - x0) * i / col, y0 + (y1 - y0) * j / row]
    ptxt = ' '.join(_fmt(q) for q in pts)
    seg_a, seg_b = doc.warp_block(name)
    blk = doc.xml[seg_a:seg_b]
    orig = re.search(r'<float-array xs\.n="positions" xs\.ref="(#\d+)"', blk).group(1)
    doc.xml = re.sub(r'(<float-array count=")\d+(" xs\.id="%s"[^>]*>)[^<]*(</float-array>)' % re.escape(orig),
                     lambda m: m.group(1) + str(len(pts)) + m.group(2) + ptxt + m.group(3), doc.xml, count=1)
    seg_a, seg_b = doc.warp_block(name)
    blk = doc.xml[seg_a:seg_b]
    blk = re.sub(r'<i xs\.n="col">\d+</i>', '<i xs.n="col">%d</i>' % col, blk)
    blk = re.sub(r'<i xs\.n="row">\d+</i>', '<i xs.n="row">%d</i>' % row, blk)
    blk = re.sub(r'(<float-array xs\.n="positions" count=")\d+(">)[^<]*(</float-array>)',
                 lambda m: m.group(1) + str(len(pts)) + m.group(2) + ptxt + m.group(3), blk)
    doc.xml = doc.xml[:seg_a] + blk + doc.xml[seg_b:]


def insert_second_key(doc, name, key_index, key_value, nx):
    """2 つのパラメータの格子を持つワープデフォーマで、2 番目のパラメータ（角度Y）に、キーを 1 つ挿入する。
    格子は、1 番目のパラメータ（nx 個のキー）が速く変わる順に並ぶ（キーフォームの並び = 行(2番目) × nx + 列(1番目)）。
    新しい行のキーフォームは、すぐ前の行（先頭に入れるときは、先頭の行）の複製（形は、あとで設定する）。"""
    import uuid
    NL = chr(10)
    a, b = doc.warp_block(name)
    blk = doc.xml[a:b]
    grid = re.search(r'<KeyformGridSource xs\.n="keyformGridSource" xs\.ref="(#\d+)"', blk).group(1)
    forms = list(re.finditer(r'<CWarpDeformerForm>.*?</CWarpDeformerForm>', blk, flags=re.S))
    rows = len(forms) // nx
    src_row = key_index - 1 if key_index > 0 else 0
    # 新しい CFormGuid を nx 個
    new_ids = []
    nid, nidx = doc._next_ids()
    for i in range(nx):
        new_ids.append(('#%d' % (nid + i), nidx + i))
    new_forms = []
    prev_refs = []
    for x in range(nx):
        src = forms[src_row * nx + x].group(0)
        prev_ref = re.search(r'<CFormGuid xs\.n="guid" xs\.ref="(#\d+)" />', src).group(1)
        prev_refs.append(prev_ref)
        new_forms.append(re.sub(r'<CFormGuid xs\.n="guid" xs\.ref="#\d+" />', '<CFormGuid xs.n="guid" xs.ref="%s" />' % new_ids[x][0], src))
    if key_index < rows:
        ins = forms[key_index * nx].start()
        blk2 = blk[:ins] + (NL + NL).join(new_forms) + NL + NL + blk[ins:]
    else:
        ins = forms[-1].end()
        blk2 = blk[:ins] + NL + NL + (NL + NL).join(new_forms) + blk[ins:]
    blk2 = re.sub(r'(<carray_list xs\.n="keyforms" count=")\d+(")', lambda mm: mm.group(1) + str(len(forms) + nx) + mm.group(2), blk2, count=1)
    doc.xml = doc.xml[:a] + blk2 + doc.xml[b:]
    # CFormGuid の定義（直前の行の定義の後ろに置く）
    for x in range(nx):
        dm = re.search(r'<CFormGuid uuid="[^"]*"[^>]*xs\.id="%s"[^>]*/>' % re.escape(prev_refs[x]), doc.xml)
        define = '<CFormGuid uuid="%s" note="Key [  ]" xs.id="%s" xs.idx="%d" />' % (uuid.uuid4(), new_ids[x][0], new_ids[x][1])
        doc.xml = doc.xml[:dm.end()] + NL + NL + define + doc.xml[dm.end():]
    # 格子の項目
    ga = doc.xml.index('<KeyformGridSource xs.id="%s"' % grid)
    gb = doc.xml.index('</KeyformGridSource>', ga)
    gblk = doc.xml[ga:gb]
    items = list(re.finditer(r'<KeyformOnGrid>.*?</KeyformOnGrid>', gblk, flags=re.S))
    texts = [it.group(0) for it in items]

    def second_idx(t):
        return [int(v) for v in re.findall(r'<i xs\.n="keyIndex">(\d+)</i>', t)][1]

    def shift(t):
        # 2 番目の keyIndex だけを、key_index 以上なら 1 増やす
        cnt = [0]

        def f(mm):
            cnt[0] += 1
            v = int(mm.group(1))
            if cnt[0] == 2 and v >= key_index:
                v += 1
            return '<i xs.n="keyIndex">%d</i>' % v
        return re.sub(r'<i xs\.n="keyIndex">(\d+)</i>', f, t)

    new_items = []
    for x in range(nx):
        t = texts[src_row * nx + x]
        cnt = [0]

        def setidx(mm):
            cnt[0] += 1
            return '<i xs.n="keyIndex">%d</i>' % (key_index if cnt[0] == 2 else int(mm.group(1)))
        t = re.sub(r'<i xs\.n="keyIndex">(\d+)</i>', setidx, t)
        t = re.sub(r'<CFormGuid xs\.n="keyformGuid" xs\.ref="#\d+" />', '<CFormGuid xs.n="keyformGuid" xs.ref="%s" />' % new_ids[x][0], t)
        new_items.append(t)
    shifted = [shift(t) for t in texts]
    out = shifted[:key_index * nx] + new_items + shifted[key_index * nx:]
    gblk2 = gblk[:items[0].start()] + (NL + NL).join(out) + gblk[items[-1].end():]
    gblk2 = re.sub(r'(<array_list xs\.n="keyformsOnGrid" count=")\d+(")', lambda mm: mm.group(1) + str(len(out)) + mm.group(2), gblk2, count=1)
    doc.xml = doc.xml[:ga] + gblk2 + doc.xml[gb:]
    # 2 番目のバインディングのキー
    binds = re.findall(r'<KeyformBindingSource xs\.ref="(#\d+)"', gblk)
    bind = binds[1] if len(binds) > 1 and binds[1] != binds[0] else [x for x in binds if x != binds[0]][0]
    ba = doc.xml.index('<KeyformBindingSource xs.id="%s"' % bind)
    bb = doc.xml.index('</KeyformBindingSource>', ba)
    bblk = doc.xml[ba:bb]
    km = re.search(r'<array_list xs\.n="keys" count="(\d+)">(.*?)</array_list>', bblk, flags=re.S)
    vals = re.findall(r'<f>([\d\.\-eE]+)</f>', km.group(2))
    vals.insert(key_index, _fmt(key_value))
    keys_xml = '<array_list xs.n="keys" count="%d">' % len(vals) + NL + NL + (NL + NL).join('<f>%s</f>' % v for v in vals) + NL + NL + '</array_list>'
    doc.xml = doc.xml[:ba] + bblk[:km.start()] + keys_xml + bblk[km.end():] + doc.xml[bb:]
