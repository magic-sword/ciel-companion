# -*- coding: utf-8 -*-
"""使っていない Face_Base メッシュを、「向きごとの素肌」（C-L30・C-R30）を出すメッシュに作り変える。

考え方
  - C-L30（画面の左を向く 30° の素肌）と C-R30 を、1 枚のシート（キャンバスと同じ大きさの PNG）に並べ、
    1 つのメッシュの 2 つの領域（それぞれ 格子）にする。メッシュは Head_Warp の子。
  - 各領域の頂点は、角度X ＝ ∓30°・角度Y ＝ 0 のときの Head_Warp の曲面で、見本と同じ位置（キャンバス座標）に出るように、
    曲面の逆変換で、Head_Warp の正規化座標へ戻して置く。→ その向きでは、見本の素肌の輪郭にぴったり重なる。
    他の向き・角度Yでは、Head_Warp の変形に従って動く（顔と一緒に動く）。
  - 角度Xのキー（-30, -15, 0, 15, 30）ごとに、不透明度と、見せない領域の「点への縮小」を設定する。
  - 描画順は Face_Skin（200）の上、口（250）の下の 205。
入力  Head_Warp が 角度X×角度Y の 25 キー（head3d-keys.py のあと）を持つ .cmo3
出力  .cmo3 と、assets/ciel/layers/head/Face_Base.png（シート）
      そのあと、replace-image-same-size.py で、Face_Base の画像を差し替え、Cubism で開いてアトラス編集 OK → 書き出し。
実行  python -I scripts/live2d/build-skin-pose.py 入力.cmo3 出力.cmo3
"""
import os
import re
import sys
import uuid

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
from cmo3_tool import _fmt

ROOT = os.path.join(HERE, '..', '..', 'assets', 'ciel')
UNDER = os.path.join(ROOT, 'generated', 'parts', 'underlayers')
CROP = (318, 236)                  # 見本（1536 四方）の、キャンバス上の位置
CANVAS = (2172, 2896)
N = 12                             # 領域ごとの分割数（N×N）
MARGIN = 6
OPACITY = {-30.0: 1.0, -15.0: 0.3, 0.0: 0.0, 15.0: 0.3, 30.0: 1.0}
KEYS = [-30.0, -15.0, 0.0, 15.0, 30.0]
DRAW_ORDER = 205
REGIONS = [('L', 'C-L30_face-rounded_xL30_y0.png', -30.0), ('R', 'C-R30_face-rounded_xR30_y0.png', 30.0)]


def bilinear(grid, u):
    side = grid.shape[0] - 1
    fu, fv = u[0] * side, u[1] * side
    cx = min(side - 1, max(0, int(np.floor(fu))))
    cy = min(side - 1, max(0, int(np.floor(fv))))
    tu, tv = fu - cx, fv - cy
    return (grid[cy, cx] * (1 - tu) * (1 - tv) + grid[cy, cx + 1] * tu * (1 - tv)
            + grid[cy + 1, cx] * (1 - tu) * tv + grid[cy + 1, cx + 1] * tu * tv)


def invert(grid, target, u0):
    """grid（(S+1)×(S+1)×2、キャンバス座標）の双線形曲面で、target に写る正規化座標 u を求める（ニュートン法）。"""
    u = np.array(u0, float)
    for _ in range(40):
        f = bilinear(grid, u) - target
        if np.hypot(*f) < 0.05:
            break
        e = 1e-4
        J = np.zeros((2, 2))
        for k in range(2):
            d = np.zeros(2); d[k] = e
            J[:, k] = (bilinear(grid, u + d) - bilinear(grid, u - d)) / (2 * e)
        try:
            step = np.linalg.solve(J, f)
        except np.linalg.LinAlgError:
            break
        u = np.clip(u - step, -0.2, 1.2)
    return u


def clean_edge(im):
    """生成画像の輪郭に付いている茶色の細い線を消す：縁を 4 px 内側へ削り、縁の帯の色を、内側の平均の肌色にする。"""
    from PIL import ImageFilter
    arr = np.asarray(im).copy()
    a = Image.fromarray(arr[..., 3])
    eroded = np.asarray(a.filter(ImageFilter.MinFilter(9)))
    inner = np.asarray(a.filter(ImageFilter.MinFilter(33))) > 200
    mean = arr[inner][:, :3].mean(0)
    band = (~inner) & (eroded > 0)
    arr[band, :3] = mean.astype(np.uint8)
    soft = Image.fromarray(eroded).filter(ImageFilter.GaussianBlur(1.5))
    arr[..., 3] = np.asarray(soft)
    return Image.fromarray(arr, 'RGBA')


def region_data(name):
    im = Image.open(os.path.join(UNDER, name)).convert('RGBA')
    im = clean_edge(im)
    a = np.asarray(im)[..., 3]
    ys, xs = np.nonzero(a > 8)
    x0, x1 = max(0, xs.min() - MARGIN), min(im.width, xs.max() + 1 + MARGIN)
    y0, y1 = max(0, ys.min() - MARGIN), min(im.height, ys.max() + 1 + MARGIN)
    return im.crop((x0, y0, x1, y1)), (x0, y0)


def main(src, dst):
    d = t.Cmo3(src)
    forms = d.warp_keyform_positions('Head_Warp')
    info = d.warp_info('Head_Warp')
    side = int(round(len(forms[0]) ** 0.5))
    W = info['x1'] - info['x0']; H = info['y1'] - info['y0']

    def grid_of(i):
        return np.array(forms[i], float).reshape(side, side, 2)
    rest = grid_of(2 * 5 + 2)
    gridL, gridR = grid_of(2 * 5 + 0), grid_of(2 * 5 + 4)

    sheet = Image.new('RGBA', CANVAS, (0, 0, 0, 0))
    pts, uvs_pt, norm = [], [], {'L': [], 'R': []}
    idx, edges, eprio = [], [], []
    sy = 16
    for tag, fname, angle in REGIONS:
        crop, (cx0, cy0) = region_data(fname)
        sx = 16
        sheet.paste(crop, (sx, sy))
        grid = gridL if tag == 'L' else gridR
        base = len(pts)
        for j in range(N + 1):
            for i in range(N + 1):
                lx = crop.width * i / N
                ly = crop.height * j / N
                pts.append((sx + lx, sy + ly))                                  # シート上の位置（メッシュの point）
                target = np.array([cx0 + lx + CROP[0], cy0 + ly + CROP[1]])     # 見本と同じ、キャンバス上の位置
                u0 = ((target[0] - info['x0']) / W, (target[1] - info['y0']) / H)
                norm[tag].append(invert(grid, target, u0))
        w = N + 1
        for j in range(N + 1):
            for i in range(N + 1):
                v = base + j * w + i
                if i < N:
                    edges.append((v, v + 1)); eprio.append(30 if j in (0, N) else 10)
                if j < N:
                    edges.append((v, v + w)); eprio.append(30 if i in (0, N) else 10)
                if i < N and j < N:
                    edges.append((v, v + w + 1)); eprio.append(10)
                    idx += [v, v + 1, v + w + 1, v + w + 1, v + w, v]
        sy += crop.height + 16
    n = len(pts)
    P = np.array(pts)

    a, b = d.mesh_block('Face_Base')
    blk = d.xml[a:b]
    # 元の四角形の point・uvs から、point → uv のアフィン変換を求める
    pt0 = np.array([float(v) for v in re.search(r'<float-array xs\.n="point" count="8">([^<]*)</float-array>', blk).group(1).split()]).reshape(4, 2)
    uv0 = np.array([float(v) for v in re.search(r'<float-array xs\.n="uvs" count="8">([^<]*)</float-array>', blk).group(1).split()]).reshape(4, 2)
    A = np.c_[pt0, np.ones(4)]
    coef, *_ = np.linalg.lstsq(A, uv0, rcond=None)
    UV = np.c_[P, np.ones(n)] @ coef

    def txt(v):
        return ' '.join(_fmt(float(q)) for q in np.asarray(v).ravel())
    nl = chr(10)
    # --- 編集用メッシュ
    blk = re.sub(r'<float-array xs\.n="point" count="8">[^<]*</float-array>', lambda m: '<float-array xs.n="point" count="%d">%s</float-array>' % (2 * n, txt(P)), blk)
    blk = re.sub(r'<byte-array xs\.n="pointPriority" count="\d+">[^<]*</byte-array>', lambda m: '<byte-array xs.n="pointPriority" count="%d">%s</byte-array>' % (n, ' '.join(['20'] * n)), blk)
    blk = re.sub(r'<short-array xs\.n="edge" count="\d+">[^<]*</short-array>', lambda m: '<short-array xs.n="edge" count="%d">%s</short-array>' % (2 * len(edges), ' '.join('%d %d' % e for e in edges)), blk)
    blk = re.sub(r'<byte-array xs\.n="edgePriority" count="\d+">[^<]*</byte-array>', lambda m: '<byte-array xs.n="edgePriority" count="%d">%s</byte-array>' % (len(edges), ' '.join(str(p) for p in eprio)), blk)
    blk = re.sub(r'<int-array xs\.n="pointUid" count="\d+">[^<]*</int-array>', lambda m: '<int-array xs.n="pointUid" count="%d">%s</int-array>' % (n, ' '.join(str(i) for i in range(n))), blk)
    blk = re.sub(r'nextPointUid="\d+"', 'nextPointUid="%d"' % n, blk, count=1)
    blk = re.sub(r'<int-array xs\.n="indices" count="\d+">[^<]*</int-array>', lambda m: '<int-array xs.n="indices" count="%d">%s</int-array>' % (len(idx), ' '.join(str(i) for i in idx)), blk)
    # メッシュ直下の positions と uvs（keyforms の外）
    k = blk.index('<carray_list xs.n="keyforms"'); k2 = blk.index('</carray_list>', k) + len('</carray_list>')
    rest_txt = blk[k2:]
    rest_txt = re.sub(r'(<float-array xs\.n="positions" count=")\d+(">)[^<]*(</float-array>)', lambda m: m.group(1) + str(2 * n) + m.group(2) + txt(P) + m.group(3), rest_txt, count=1)
    rest_txt = re.sub(r'(<float-array xs\.n="uvs" count=")\d+(">)[^<]*(</float-array>)', lambda m: m.group(1) + str(2 * n) + m.group(2) + txt(UV) + m.group(3), rest_txt, count=1)
    # --- Head_Warp の子にする
    blk_head = blk[:k]
    blk_head = re.sub(r'<CDeformerGuid xs\.n="targetDeformerGuid"[^>]*/>', '<CDeformerGuid xs.n="targetDeformerGuid" xs.ref="%s" />' % info['guid'], blk_head)
    if 'xs.ref="%s"' % info['guid'] not in blk_head:
        raise SystemExit('targetDeformerGuid を Head_Warp にできなかった')
    # --- キーフォーム
    kf_old = blk[k:k2]
    form = re.search(r'<CArtMeshForm>.*?</CArtMeshForm>', kf_old, flags=re.S).group(0)
    nid, nidx = d._next_ids()
    form_ids = [('#%d' % (nid + i), nidx + i) for i in range(len(KEYS))]
    collapse = np.array([0.5, 0.5])
    new_forms = []
    for ki, key in enumerate(KEYS):
        pos = []
        for tag, _, ang in REGIONS:
            active = (key <= 0 and ang < 0) or (key >= 0 and ang > 0)
            if key == 0.0:
                active = False
            arr = norm[tag] if active else [collapse] * len(norm[tag])
            pos += [(float(q[0]), float(q[1])) for q in arr]
        f = re.sub(r'<CFormGuid xs\.n="guid" xs\.ref="#\d+" />', '<CFormGuid xs.n="guid" xs.ref="%s" />' % form_ids[ki][0], form)
        f = re.sub(r'<f xs\.n="opacity">[^<]*</f>', '<f xs.n="opacity">%s</f>' % _fmt(OPACITY[key]), f)
        f = re.sub(r'<i xs\.n="drawOrder">\d+</i>', '<i xs.n="drawOrder">%d</i>' % DRAW_ORDER, f)
        f = re.sub(r'<CoordType xs\.n="coordType" xs\.ref="#\d+" />', '<CoordType xs.n="coordType" xs.ref="%s" />' % info['coord'], f)
        f = re.sub(r'(<float-array xs\.n="positions" count=")\d+(">)[^<]*(</float-array>)', lambda m: m.group(1) + str(2 * len(pos)) + m.group(2) + txt(pos) + m.group(3), f)
        new_forms.append(f)
    kf_new = '<carray_list xs.n="keyforms" count="%d">' % len(KEYS) + nl + (nl + nl).join(new_forms) + nl + '</carray_list>'
    # --- 格子と結びつけ（角度X）
    grid_id, grid_idx = '#%d' % (nid + len(KEYS)), nidx + len(KEYS)
    bind_id, bind_idx = '#%d' % (nid + len(KEYS) + 1), nidx + len(KEYS) + 1
    items = []
    for ki in range(len(KEYS)):
        items.append('<KeyformOnGrid>' + nl + '<KeyformGridAccessKey xs.n="accessKey">' + nl + '<array_list xs.n="_keyOnParameterList" count="1">' + nl
                     + '<KeyOnParameter>' + nl + '<KeyformBindingSource xs.n="binding" xs.ref="%s" />' % bind_id + nl + '<i xs.n="keyIndex">%d</i>' % ki + nl
                     + '</KeyOnParameter>' + nl + '</array_list>' + nl + '</KeyformGridAccessKey>' + nl
                     + '<CFormGuid xs.n="keyformGuid" xs.ref="%s" />' % form_ids[ki][0] + nl + '</KeyformOnGrid>')
    grid_xml = ('<KeyformGridSource xs.id="%s" xs.idx="%d">' % (grid_id, grid_idx) + nl
                + '<array_list xs.n="keyformsOnGrid" count="%d">' % len(KEYS) + nl + (nl + nl).join(items) + nl + '</array_list>' + nl
                + '<array_list xs.n="keyformBindings" count="1">' + nl + '<KeyformBindingSource xs.ref="%s" />' % bind_id + nl + '</array_list>' + nl
                + '</KeyformGridSource>')
    bi = blk_head.index('<KeyformGridSource xs.n="keyformGridSource">')
    bj = blk_head.index('</KeyformGridSource>', bi) + len('</KeyformGridSource>')
    blk_head = blk_head[:bi] + '<KeyformGridSource xs.n="keyformGridSource" xs.ref="%s" />' % grid_id + blk_head[bj:]
    blk_head = blk_head.replace('<b xs.n="isVisible">false</b>', '<b xs.n="isVisible">true</b>', 1)   # 非表示のままだと書き出されない
    new_blk = blk_head + kf_new + rest_txt
    d.xml = d.xml[:a] + new_blk + d.xml[b:]
    # --- 定義：CFormGuid×5、結びつけ（ParamAngleX の CParameterGuid を参照）
    px = re.search(r'<CParameterGuid uuid="[^"]*" note="ParamAngleX" xs\.id="(#\d+)"', d.xml).group(1)
    anchor = re.search(r'<CFormGuid uuid="[^"]*"[^>]*xs\.id="#554"[^>]*/>', d.xml)
    defs = nl.join('<CFormGuid uuid="%s" note="Key [  ]" xs.id="%s" xs.idx="%d" />' % (uuid.uuid4(), fid, fidx) for fid, fidx in form_ids)
    bind_xml = ('<KeyformBindingSource xs.id="%s" xs.idx="%d">' % (bind_id, bind_idx) + nl
                + '<KeyformGridSource xs.n="_gridSource" xs.ref="%s" />' % grid_id + nl
                + '<CParameterGuid xs.n="parameterGuid" xs.ref="%s" />' % px + nl
                + '<array_list xs.n="keys" count="%d">' % len(KEYS) + nl + nl.join('<f>%s</f>' % _fmt(kk) for kk in KEYS) + nl + '</array_list>' + nl
                + '<InterpolationType xs.n="interpolationType" v="LINEAR" />' + nl
                + '<ExtendedInterpolationType xs.n="extendedInterpolationType" v="LINEAR" />' + nl
                + '<i xs.n="insertPointCount">1</i>' + nl + '<f xs.n="extendedInterpolationScale">1.0</f>' + nl + '<s xs.n="description" />' + nl
                + '</KeyformBindingSource>')
    d.xml = d.xml[:anchor.end()] + nl + defs + nl + grid_xml + nl + bind_xml + d.xml[anchor.end():]
    d.save(dst)
    out = os.path.join(ROOT, 'layers', 'head', 'Face_Base.png')
    sheet.save(out)
    print('SKIN_POSE_BUILT', dst, out, 'vertices', n)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
