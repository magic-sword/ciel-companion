"""ほっぺの「ぷにっと押す」「つまんで引っ張る」「離したときの揺れ」を、正式モデルへ組み込む（v64、段階 1）。

1. ほっぺの赤み（Cheek_Blush と表情用の Cheek_Happy・Relaxed・Embarrassed・Excited）の描画順を、
   目の下まぶたの肌（Eye_L_LidSkin_Lower 470）より上、まつ毛（480）より下へ上げる（まぶたの肌が赤みの上に浮いて見えた）。
2. パラメーターを足す：ParamCielCheekPoke{L,R}（0〜1）、ParamCielCheekPullX{L,R}・PullY{L,R}（−1〜1）、
   ParamCielCheekJiggle{L,R}（−1〜1。物理演算の出力。離したときの揺れ）。
3. 顔の回転の下に、ほっぺのワープ Cheek_Squish_L（顔の回転の子）→ Cheek_Squish_R（L の子）を挟み、
   顔の曲面・口の曲面・鼻の曲面を Cheek_Squish_R の子にする。ワープの形は cheek_squish.py。
   - 顔の回転の下の座標（回転の中の座標）とキャンバスの対応は、書き出したモデルを Core で計算して求める
     （顔の曲面の下でキーが 1 つの Face_Shadow_Hair の頂点から、一次式で）。
   - 子にするワープのキーフォームは、回転の中の座標 → キャンバス → Cheek_Squish の格子の割合（0〜1）へ直し、
     座標の種類を、ワープの子のもの（呼吸などと同じ）にする。
くぼみの影の層（Cheek_Dimple_*）は、Cubism で取り込んだあと、段階 2（integrate-dimple.py）で付ける。

実行  python -I scripts/live2d/v64/integrate-cheek.py 入力.cmo3 書き出したモデル.model3.json 出力.cmo3
"""
import copy
import importlib.util
import itertools
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import cmo3_tool as t
import cubism_core as cc
import cheek_squish as cs


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


lib = module('integration', HERE.parent / 'integrate-expressions.py')
named, array = lib.named, lib.array

BLUSH = {'Cheek_Blush': 471, 'Cheek_Happy': 471, 'Cheek_Relaxed': 472, 'Cheek_Embarrassed': 473, 'Cheek_Excited': 474}
CHILDREN = ('顔の曲面', '口の曲面', '鼻の曲面')
PARAMS = []   # （ID、表示名、最小、最大）
for side, label in (('L', '左'), ('R', '右')):
    PARAMS += [(f'ParamCielCheekPoke{side}', f'{label}ほっぺ 押す', 0.0, 1.0),
               (f'ParamCielCheekPullX{side}', f'{label}ほっぺ 引く 横', -1.0, 1.0),
               (f'ParamCielCheekPullY{side}', f'{label}ほっぺ 引く 縦', -1.0, 1.0),
               (f'ParamCielCheekJiggle{side}', f'{label}ほっぺ 揺れ', -1.0, 1.0)]
JIGGLE = 0.6   # 揺れ 1 のときの、押す変形に対する大きさ


def neutral_index(cmo3, warp_name):
    """ワープのキーフォームのうち、すべてのパラメーターが 0 のもの（正面）の番号。
    顔の向きのキーは正面を拡大・移動しただけの形なので、当てはまりの良さでは見分けられない。キーの表から決める"""
    x = cmo3.xml
    a, b = cmo3.warp_block(warp_name)
    seg = x[a:b]
    forms = re.findall(r'<CWarpDeformerForm>.*?<CFormGuid xs\.n="guid" xs\.ref="(#\d+)"', seg, re.S)
    gid = re.search(r'<KeyformGridSource xs\.n="keyformGridSource" xs\.ref="(#\d+)"', seg).group(1)
    i = x.index('<KeyformGridSource xs.id="%s"' % gid)
    grid = x[i:x.index('</KeyformGridSource>', i)]
    keys = {}
    for bid in set(re.findall(r'<KeyformBindingSource xs\.n="binding" xs\.ref="(#\d+)"', grid)):
        j = x.index('<KeyformBindingSource xs.id="%s"' % bid)
        blk = x[j:x.index('</KeyformBindingSource>', j)]
        k = blk.index('<array_list xs.n="keys"')
        keys[bid] = [float(v) for v in re.findall(r'<f>([^<]*)</f>', blk[k:blk.index('</array_list>', k)])]
    for item in re.findall(r'<KeyformOnGrid>(.*?)</KeyformOnGrid>', grid, re.S):
        pairs = re.findall(r'xs\.ref="(#\d+)" />\s*<i xs\.n="keyIndex">(\d+)</i>', item)
        if all(keys[bid][int(k)] == 0.0 for bid, k in pairs):
            return forms.index(re.search(r'<CFormGuid xs\.n="keyformGuid" xs\.ref="(#\d+)"', item).group(1))
    raise ValueError(warp_name + ': 正面のキーがない')


def local_to_canvas(cmo3, model_path):
    """顔の回転の下の座標 → キャンバスの一次式（3×2。[x, y, 1] @ A）"""
    x = cmo3.xml
    face = np.array(cmo3.warp_keyform_positions('顔の曲面')[neutral_index(cmo3, '顔の曲面')])
    blk = x[slice(*cmo3.mesh_keyforms('Face_Shadow_Hair'))]
    forms = re.findall(r'<float-array xs\.n="positions" count="\d+">([^<]*)', blk)
    assert len(forms) == 1, 'Face_Shadow_Hair のキーが 1 つでない'
    uv = np.array([float(q) for q in forms[0].split()]).reshape(-1, 2)
    m = cc.Model(model_path)
    m.reset()
    m.update()
    core = next(d for d in m.drawables() if d['id'] == 'Face_Shadow_Hair')['pos']
    n = int(round(np.sqrt(len(face)))) - 1
    local = bilinear(face.reshape(n + 1, n + 1, 2), uv)
    A, *_ = np.linalg.lstsq(np.c_[local, np.ones(len(local))], core, rcond=None)
    err = np.abs(np.c_[local, np.ones(len(local))] @ A - core).max()
    assert err < 0.05, '回転の中の座標とキャンバスの対応が求まらない（誤差 %.3f）' % err
    return A


def bilinear(g, uv):
    n = g.shape[0] - 1
    u = np.clip(uv[:, 0] * n, 0, n - 1e-9)
    v = np.clip(uv[:, 1] * n, 0, n - 1e-9)
    i, j = u.astype(int), v.astype(int)
    fu, fv = (u - i)[:, None], (v - j)[:, None]
    return (1 - fu) * (1 - fv) * g[j, i] + fu * (1 - fv) * g[j, i + 1] + (1 - fu) * fv * g[j + 1, i] + fu * fv * g[j + 1, i + 1]


def main():
    src, model_path, dst = sys.argv[1:4]
    doc = t.Cmo3(src)
    A = local_to_canvas(doc, model_path)
    to_canvas = lambda p: np.c_[p, np.ones(len(p))] @ A
    Ainv = np.linalg.inv(np.r_[A.T, [[0, 0, 1]]])[:2]
    to_local = lambda p: (Ainv @ np.c_[p, np.ones(len(p))].T).T
    x0, y0, x1, y1 = cs.GRID_BOX
    to_unit = lambda p: np.c_[(p[:, 0] - x0) / (x1 - x0), (p[:, 1] - y0) / (y1 - y0)]

    # 1. 赤みの描画順
    for mesh, order in BLUSH.items():
        doc.set_draw_order(mesh, order)

    e = lib.Editor(doc)
    # 2. パラメーター
    for pid, label, lo, hi in PARAMS:
        e.add_param(pid, label)
        for p in e.root.iter('CParameterSource'):
            if named(p, 'CParameterGuid', 'guid').get('xs.ref') == e.params[pid]:
                for key, value in (('minValue', lo), ('maxValue', hi), ('defaultValue', 0.0)):
                    named(p, 'f', key).text = str(float(value))

    warps = {named(w, 's', 'localName').text: w for w in e.root.iter('CWarpDeformerSource') if w.get('xs.id')}
    rots = {named(r, 's', 'localName').text: r for r in e.root.iter('CRotationDeformerSource') if r.get('xs.id')}
    face = warps['顔の曲面']
    rot_guid = named(rots['顔の回転'], 'CDeformerGuid', 'guid').get('xs.ref')
    assert named(face, 'CDeformerGuid', 'targetDeformerGuid').get('xs.ref') == rot_guid
    local_coord = named(face, 'CoordType', 'coordType').get('xs.ref')           # 回転の子の座標
    warp_coord = named(warps['左目玉の曲面'], 'CoordType', 'coordType').get('xs.ref')   # ワープの子の座標（割合）
    part_guid = named(face, 'CPartGuid', 'parentGuid').get('xs.ref')

    def clone(old):
        new = e.define(old.tag)
        ident = {k: new.get(k) for k in ('xs.id', 'xs.idx')}
        new.attrib.update(old.attrib)
        new.attrib.update(ident)
        new.extend(copy.deepcopy(list(old)))
        new.text = old.text
        for node in new.iter():
            if node.get('xs.ref') == old.get('xs.id'):
                node.set('xs.ref', new.get('xs.id'))
            if node.get('uuid'):
                node.set('uuid', str(uuid.uuid4()))
        return new

    grid = cs.grid()
    cols, rows = cs.GRID_COLS, cs.GRID_ROWS

    def add_warp(side, parent_guid, coord, convert):
        name = 'Cheek_Squish_' + side
        warp = clone(face)
        named(warp, 's', 'localName').text = name
        ident = named(warp, 'CDeformerId', 'id')
        ident.attrib.clear()
        ident.attrib.update({'xs.n': 'id', 'idstr': name})
        guid = e.define('CDeformerGuid', uuid=str(uuid.uuid4()), note=name)
        named(warp, 'CDeformerGuid', 'guid').set('xs.ref', guid.get('xs.id'))
        named(warp, 'CDeformerGuid', 'targetDeformerGuid').set('xs.ref', parent_guid)
        ext = named(warp, 'carray_list', '_extensions')
        ext.clear()
        ext.attrib.update({'xs.n': '_extensions', 'count': '0'})
        warp.find('i[@xs.n="col"]').text = str(cols)
        warp.find('i[@xs.n="row"]').text = str(rows)
        # キー：押す（0, 1）× 引く 横（−1, 0, 1）× 引く 縦（−1, 0, 1）× 揺れ（−1, 0, 1）
        pids = [f'ParamCielCheekPoke{side}', f'ParamCielCheekPullX{side}', f'ParamCielCheekPullY{side}',
                f'ParamCielCheekJiggle{side}']
        keysets = [(0.0, 1.0), (-1.0, 0.0, 1.0), (-1.0, 0.0, 1.0), (-1.0, 0.0, 1.0)]
        forms = named(warp, 'carray_list', 'keyforms')
        template = copy.deepcopy(forms[0])
        forms.clear()   # clear は属性も消すので、一覧の名前を付け直す（無いと Cubism がキーを見つけられない）
        forms.attrib.update({'xs.n': 'keyforms', 'count': '0'})
        kgrid = e.define('KeyformGridSource')
        named(warp, 'KeyformGridSource', 'keyformGridSource').set('xs.ref', kgrid.get('xs.id'))
        ongrid = ET.SubElement(kgrid, 'array_list', {'xs.n': 'keyformsOnGrid', 'count': '0'})
        binds = ET.SubElement(kgrid, 'array_list', {'xs.n': 'keyformBindings', 'count': str(len(pids))})
        bindings = []
        for pid, keys in zip(pids, keysets):
            b = e.define('KeyformBindingSource')
            ET.SubElement(b, 'KeyformGridSource', {'xs.n': '_gridSource', 'xs.ref': kgrid.get('xs.id')})
            ET.SubElement(b, 'CParameterGuid', {'xs.n': 'parameterGuid', 'xs.ref': e.params[pid]})
            vals = ET.SubElement(b, 'array_list', {'xs.n': 'keys', 'count': str(len(keys))})
            for v in keys:
                ET.SubElement(vals, 'f').text = str(float(v))
            for tag in ('InterpolationType', 'ExtendedInterpolationType'):
                ET.SubElement(b, tag, {'xs.n': tag[0].lower() + tag[1:], 'v': 'LINEAR'})
            for tag, key, value in (('i', 'insertPointCount', '1'), ('f', 'extendedInterpolationScale', '1.0'),
                                    ('s', 'description', '')):
                ET.SubElement(b, tag, {'xs.n': key}).text = value
            ET.SubElement(binds, 'KeyformBindingSource', {'xs.ref': b.get('xs.id')})
            bindings.append(b)
        # Cubism の決まりで、最初のパラメーター（押す）が一番速く変わる順に並べる（書き出しは並び順でキーを引く）
        for rev in itertools.product(*(range(len(k)) for k in reversed(keysets))):
            idx = rev[::-1]
            poke, px, py, jig = (keysets[i][j] for i, j in enumerate(idx))
            moved = grid + cs.displacement(grid, side, poke + JIGGLE * jig, px, py)
            form = copy.deepcopy(template)
            fg = e.define('CFormGuid', uuid=str(uuid.uuid4()), note=name)
            named(form, 'CFormGuid', 'guid').set('xs.ref', fg.get('xs.id'))
            named(form, 'CWarpDeformerSource', '_source').set('xs.ref', warp.get('xs.id'))
            named(form, 'CoordType', 'coordType').set('xs.ref', coord)
            pos = named(form, 'float-array', 'positions')
            values = convert(moved)
            pos.set('count', str(values.size))
            pos.text = array(values)
            forms.append(form)
            item = ET.SubElement(ongrid, 'KeyformOnGrid')
            access = ET.SubElement(item, 'KeyformGridAccessKey', {'xs.n': 'accessKey'})
            keys = ET.SubElement(access, 'array_list', {'xs.n': '_keyOnParameterList', 'count': str(len(pids))})
            for b, j in zip(bindings, idx):
                k = ET.SubElement(keys, 'KeyOnParameter')
                ET.SubElement(k, 'KeyformBindingSource', {'xs.n': 'binding', 'xs.ref': b.get('xs.id')})
                ET.SubElement(k, 'i', {'xs.n': 'keyIndex'}).text = str(j)
            ET.SubElement(item, 'CFormGuid', {'xs.n': 'keyformGuid', 'xs.ref': fg.get('xs.id')})
        forms.set('count', str(len(forms)))
        ongrid.set('count', str(len(ongrid)))
        members = e.root.find('.//CDeformerSourceSet/carray_list[@xs.n="_sources"]')
        ET.SubElement(members, warp.tag, {'xs.ref': warp.get('xs.id')})
        members.set('count', str(len(members)))
        part = next(n for n in e.root.iter('CPartSource')
                    if n.get('xs.id') and named(n, 'CPartGuid', 'guid').get('xs.ref') == part_guid)
        kids = named(part, 'carray_list', '_childGuids')
        ET.SubElement(kids, 'CDeformerGuid', {'xs.ref': guid.get('xs.id')})
        kids.set('count', str(len(kids)))
        return guid.get('xs.id')

    # 3. ほっぺのワープ。L は回転の子（回転の中の座標）、R は L の子（L の格子の割合）
    guid_l = add_warp('L', rot_guid, local_coord, lambda p: to_local(p))
    guid_r = add_warp('R', guid_l, warp_coord, lambda p: to_unit(p))
    for name in CHILDREN:
        w = warps[name]
        assert named(w, 'CDeformerGuid', 'targetDeformerGuid').get('xs.ref') == rot_guid, name
        named(w, 'CDeformerGuid', 'targetDeformerGuid').set('xs.ref', guid_r)
        for form in named(w, 'carray_list', 'keyforms'):
            pos = named(form, 'float-array', 'positions')
            local = np.array([float(q) for q in pos.text.split()]).reshape(-1, 2)
            pos.text = array(to_unit(to_canvas(local)))
            named(form, 'CoordType', 'coordType').set('xs.ref', warp_coord)

    e.flush()
    missing = {n.get('xs.ref') for n in e.root.iter() if n.get('xs.ref') and n.get('xs.ref') not in e.ids}
    assert not missing, missing
    doc.save(dst)
    print('CHEEK_RIG_READY', dst, 'local->canvas', np.round(A, 5).tolist())


if __name__ == '__main__':
    main()
