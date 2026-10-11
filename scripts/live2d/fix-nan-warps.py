# -*- coding: utf-8 -*-
"""デフォーマの自動生成で、格子が NaN になったワープデフォーマを直す。

Cubism の「デフォーマの自動生成」で、中身が空（[生成されない]）の部位にあとからメッシュを足すと、そのワープの格子の
座標が NaN になり、中のメッシュが描かれなくなった（2026-10-11）。このスクリプトは、NaN のワープを、
指定した親のワープ（例：呼吸）の直下へ付け替え、格子を、子のメッシュの範囲（元の画像座標 point）から計算し直す。
入れ子のワープ（眉の位置・角度、目玉など）は、親のワープの正規化座標で作り直す。中のメッシュの座標も、正規化し直す。

実行  python -I scripts/live2d/fix-nan-warps.py 入力.cmo3 出力.cmo3 新しい親のワープ名 [余白の割合=0.12] [--force 名前,名前]
      --force：NaN でなくても、作り直すワープ（メッシュを作り直したあと、格子を合わせ直すときに使う）
"""
import re
import sys

import numpy as np

import os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t


def fmt(v):
    return ('%.6f' % v).rstrip('0').rstrip('.') if abs(v) < 1e6 else '%.1f' % v


def deformers(x):
    out = {}
    for tag in ['CWarpDeformerSource', 'CRotationDeformerSource']:
        for m in re.finditer(r'<%s xs\.id="(#\d+)"[^>]*>' % tag, x):
            e = x.index('</%s>' % tag, m.start())
            blk = x[m.start():e]
            name = re.search(r'<s xs\.n="localName">([^<]*)</s>', blk).group(1)
            guid = re.search(r'<CDeformerGuid xs\.n="guid" xs\.ref="(#\d+)"', blk).group(1)
            pm = re.search(r'<CDeformerGuid xs\.n="targetDeformerGuid" xs\.ref="(#\d+)"', blk)
            out[guid] = dict(kind=tag, name=name, guid=guid, parent=pm.group(1) if pm else None, start=m.start(), end=e)
    return out


def meshes(x):
    out = []
    for m in re.finditer(r'<CArtMeshSource xs\.id="(#\d+)"[^>]*>', x):
        e = x.index('</CArtMeshSource>', m.start())
        blk = x[m.start():e]
        name = re.search(r'<s xs\.n="localName">([^<]*)</s>', blk).group(1)
        pm = re.search(r'<CDeformerGuid xs\.n="targetDeformerGuid" xs\.ref="(#\d+)"', blk)
        pts = np.array(re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)<', blk).group(1).split(), float).reshape(-1, 2)
        out.append(dict(name=name, parent=pm.group(1) if pm else None, point=pts))
    return out


def warp_rest_grid(x, d):
    """ワープの最初のキーフォームの格子（親の座標）と、分割数。"""
    blk = x[d['start']:d['end']]
    col = int(re.search(r'<i xs\.n="col">(\d+)</i>', blk).group(1))
    row = int(re.search(r'<i xs\.n="row">(\d+)</i>', blk).group(1))
    p = re.search(r'<float-array xs\.n="positions" count="\d+">([^<]*)<', blk)
    g = np.array(p.group(1).split(), float).reshape(-1, 2) if p else None
    return g, col, row


def main():
    args = sys.argv[1:]
    force = set()
    if '--force' in args:
        i = args.index('--force')
        force = set(args[i + 1].split(','))
        args = args[:i] + args[i + 2:]
    src, dst, new_parent_name = args[:3]
    margin = float(args[3]) if len(args) > 3 else 0.12
    doc = t.Cmo3(src)
    x = doc.xml
    defs = deformers(x)
    byname = {d['name']: d for d in defs.values()}
    np_def = byname[new_parent_name]

    # 親のワープ（呼吸）の正規化座標 ←→ キャンバス：根から順に、格子の範囲（長方形と見なす）で合成する
    chain = []
    d = np_def
    while d is not None:
        chain.append(d)
        d = defs.get(d['parent'])
    chain.reverse()          # 根（キャンバス座標の格子）から呼吸まで
    lo, hi = np.array([0.0, 0.0]), np.array([1.0, 1.0])   # 呼吸の正規化 (0,0)-(1,1) を、上から順に写す
    # キャンバス座標での、呼吸の格子の範囲を求める
    box0 = None
    for d in chain:
        g, _, _ = warp_rest_grid(x, d)
        if d['kind'] != 'CWarpDeformerSource' or g is None or np.isnan(g).any():
            raise SystemExit('親の連鎖に使えないデフォーマ: %s' % d['name'])
        gmin, gmax = g.min(0), g.max(0)
        if box0 is None:
            box0 = (gmin, gmax)               # 根：キャンバス座標
        else:
            o, s = box0[0], box0[1] - box0[0]
            box0 = (o + gmin * s, o + gmax * s)
    p0, p1 = box0
    print('親 %s のキャンバス上の範囲: x %.1f..%.1f  y %.1f..%.1f' % (new_parent_name, p0[0], p1[0], p0[1], p1[1]))

    def to_parent_norm(c):
        return (c - p0) / (p1 - p0)

    # 直す対象：格子が NaN のワープ
    bad = []
    for d in defs.values():
        if d['kind'] != 'CWarpDeformerSource':
            continue
        g, _, _ = warp_rest_grid(x, d)
        if (g is not None and np.isnan(g).any()) or d['name'] in force:
            bad.append(d)
    badg = {d['guid'] for d in bad}
    ms = meshes(x)

    def desc_points(guid):
        pts = [m['point'] for m in ms if m['parent'] == guid]
        for d in defs.values():
            if d['parent'] == guid:
                pts += desc_points(d['guid'])
        return pts

    # キャンバス上の範囲（余白つき）
    canvas_box = {}
    for d in bad:
        pts = desc_points(d['guid'])
        if not pts:
            print('子のない NaN ワープ（そのまま）:', d['name'])
            continue
        a = np.vstack(pts)
        mn, mx = a.min(0), a.max(0)
        pad = (mx - mn) * margin + 4
        canvas_box[d['guid']] = (mn - pad, mx + pad)

    # 親を決める：親が NaN ワープなら、その中の正規化座標。そうでなければ（回転デフォーマなど）、新しい親（呼吸）へ付け替え
    edits = []
    for d in bad:
        if d['guid'] not in canvas_box:
            continue
        cb0, cb1 = canvas_box[d['guid']]
        if d['parent'] in badg and d['parent'] in canvas_box:
            q0, q1 = canvas_box[d['parent']]
            n0, n1 = (cb0 - q0) / (q1 - q0), (cb1 - q0) / (q1 - q0)
            parent = d['parent']
        else:
            n0, n1 = to_parent_norm(cb0), to_parent_norm(cb1)
            parent = np_def['guid']
        _, col, row = warp_rest_grid(x, d)
        xs = np.linspace(n0[0], n1[0], col + 1)
        ys = np.linspace(n0[1], n1[1], row + 1)
        grid = [(gx, gy) for gy in ys for gx in xs]
        edits.append((d, parent, grid))

    # 文字列を後ろから書き換える（位置がずれないように）
    for d, parent, grid in sorted(edits, key=lambda e: -e[0]['start']):
        blk = x[d['start']:d['end']]
        text = ' '.join(fmt(v) for p in grid for v in p)
        blk = re.sub(r'(<float-array xs\.n="positions" count=")\d+(">)[^<]*(<)', lambda m: m.group(1) + str(len(grid) * 2) + m.group(2) + text + m.group(3), blk)
        blk = re.sub(r'(<CDeformerGuid xs\.n="targetDeformerGuid" xs\.ref=")#\d+(")', lambda m: m.group(1) + parent + m.group(2), blk)
        orig = re.search(r'<float-array xs\.n="positions" xs\.ref="(#\d+)"', blk)
        x = x[:d['start']] + blk + x[d['end']:]
        if orig:   # 元の形（拡張）の格子も、同じにする
            om = re.search(r'(<float-array count=")\d+(" xs\.id="%s"[^>]*>)[^<]*(<)' % re.escape(orig.group(1)), x)
            if om:
                x = x[:om.start()] + om.group(1) + str(len(grid) * 2) + om.group(2) + text + om.group(3) + x[om.end():]
        print('直した: %s  親=%s' % (d['name'], defs[parent]['name']))

    # 子のメッシュの座標を、ワープの範囲の正規化座標へ
    doc.xml = x
    for m in ms:
        if m['parent'] not in canvas_box:
            continue
        cb0, cb1 = canvas_box[m['parent']]
        a, b = doc.mesh_block(m['name'])
        blk = doc.xml[a:b]
        k = blk.index('<carray_list xs.n="keyforms"')
        k2 = blk.index('</carray_list>', k)
        n = (m['point'] - cb0) / (cb1 - cb0)
        text = ' '.join(fmt(v) for v in n.ravel())
        kf = re.sub(r'(<float-array xs\.n="positions" count="\d+">)[^<]*(<)', lambda mm: mm.group(1) + text + mm.group(2), blk[k:k2])
        doc.xml = doc.xml[:a] + blk[:k] + kf + blk[k2:] + doc.xml[b:]
    doc.save(dst)
    print('FIX_NAN_WARPS_DONE', len(edits), 'warps')


if __name__ == '__main__':
    main()
