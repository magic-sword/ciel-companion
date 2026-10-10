# -*- coding: utf-8 -*-
"""モデルの構造（.cmo3）と動きの量（書き出した .moc3）を調べて、Markdown の表にする。

手本のモデル（公式サンプル）と、シエルのモデルを、同じ物差しで比べるための道具。

実行  python -I scripts/live2d/analyze-rig.py モデル.cmo3 モデル.model3.json 出力.md [頭の幅の基準にするメッシュID]
出すもの
  1. デフォーマの木（親子、種類、格子の分割数、キーを持つパラメーター）と、その下のメッシュの数
  2. メッシュごとの、角度X=±30・角度Y=±30 での動き（中心の移動と横幅の変化。頭の幅で割った比）と、描画順の変化
"""
import os
import re
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t
import cubism_core as cc


def blocks(x, tag):
    for m in re.finditer(r'<%s xs\.id="(#\d+)"' % tag, x):
        e = x.index('</%s>' % tag, m.start())
        yield m.group(1), x[m.start():e]


def first(pat, s, default=None):
    m = re.search(pat, s)
    return m.group(1) if m else default


def structure(x):
    params = {}
    for m in re.finditer(r'<CParameterSource>(.*?)</CParameterSource>', x, re.S):
        b = m.group(1)
        params[first(r'<CParameterGuid xs\.n="guid" xs\.(?:ref|id)="(#\d+)"', b)] = first(r'idstr="([^"]*)"', b)
    bindings = {}
    for bid, b in blocks(x, 'KeyformBindingSource'):
        keys = re.findall(r'<f>([^<]*)</f>', b.split('<array_list xs.n="keys"')[1].split('</array_list>')[0]) if 'xs.n="keys"' in b else []
        bindings[bid] = (params.get(first(r'parameterGuid" xs\.ref="(#\d+)"', b), '?'), [float(k) for k in keys])
    grids = {}
    for gid, b in blocks(x, 'KeyformGridSource'):
        bl = b.split('xs.n="keyformBindings"')[-1]
        grids[gid] = [bindings[r] for r in re.findall(r'<KeyformBindingSource xs\.ref="(#\d+)"', bl) if r in bindings]
    nodes = {}
    guid2node = {}
    for kind, tag in [('warp', 'CWarpDeformerSource'), ('rot', 'CRotationDeformerSource'), ('mesh', 'CArtMeshSource')]:
        for _, b in blocks(x, tag):
            name = first(r'<s xs\.n="localName">([^<]*)</s>', b)
            gtag = 'CDeformerGuid' if kind != 'mesh' else 'CDrawableGuid'
            guid = first(r'<%s xs\.n="guid" (?:uuid="[^"]*" )?xs\.(?:ref|id)="(#\d+)"' % gtag, b)
            ident = first(r'<C(?:Deformer|Drawable|ArtMesh)Id xs\.n="id" idstr="([^"]*)"', b)
            target = first(r'<CDeformerGuid xs\.n="targetDeformerGuid" (?:uuid="[^"]*" )?(?:note="[^"]*" )?xs\.(?:ref|id)="(#\d+)"', b)
            grid = grids.get(first(r'<KeyformGridSource xs\.n="keyformGridSource" xs\.ref="(#\d+)"', b), [])
            n = dict(kind=kind, name=name, id=ident, guid=guid, target=target,
                     params=[(p, len(k)) for p, k in grid],
                     col=first(r'<i xs\.n="col">(\d+)</i>', b), row=first(r'<i xs\.n="row">(\d+)</i>', b))
            nodes[(kind, name, ident)] = n
            if guid:
                guid2node[guid] = n
    children = defaultdict(list)
    roots = []
    for n in nodes.values():
        p = guid2node.get(n['target'])
        if p is None or p is n:
            roots.append(n)
        else:
            children[id(p)].append(n)
    return roots, children


def tree_md(roots, children):
    lines = []

    def walk(n, depth):
        kids = children[id(n)]
        if n['kind'] == 'mesh':
            return
        meshes = [k for k in kids if k['kind'] == 'mesh']
        ps = ', '.join('%s×%d' % p for p in n['params']) or '—'
        grid = ' %s×%s' % (n['col'], n['row']) if n['kind'] == 'warp' else ''
        lines.append('%s- **%s** `%s` [%s%s] キー: %s / メッシュ %d: %s' % (
            '  ' * depth, n['name'], n['id'], n['kind'], grid, ps, len(meshes),
            ', '.join(m['name'] for m in meshes[:12]) + (' …' if len(meshes) > 12 else '')))
        for k in kids:
            walk(k, depth + 1)
    for r in roots:
        if r['kind'] != 'mesh':
            walk(r, 0)
    loose = [r['name'] for r in roots if r['kind'] == 'mesh']
    if loose:
        lines.append('- （親なしのメッシュ %d）: %s' % (len(loose), ', '.join(loose)))
    return '\n'.join(lines)


def motion(model, head_id, names):
    def snap(vals):
        model.reset()
        model.set(vals)
        model.update()
        return {d['id']: d for d in model.drawables()}
    base = snap({})
    hb = base[head_id]['pos']
    head_w = hb[:, 0].max() - hb[:, 0].min()
    hc = hb.mean(0)
    poses = [('X+30', {'ParamAngleX': 30}), ('X-30', {'ParamAngleX': -30}), ('Y+30', {'ParamAngleY': 30}), ('Y-30', {'ParamAngleY': -30})]
    snaps = {k: snap(v) for k, v in poses}
    rows = []
    for did, d in base.items():
        p0 = d['pos']
        if len(p0) == 0 or d['opacity'] < 0.01:
            continue
        w0 = p0[:, 0].max() - p0[:, 0].min()
        r = [names.get(did, did), '%.2f' % ((p0[:, 0].mean() - hc[0]) / head_w), '%.2f' % ((p0[:, 1].mean() - hc[1]) / head_w)]
        moved = False
        for k, _ in poses:
            p = snaps[k][did]['pos']
            dx = (p[:, 0].mean() - p0[:, 0].mean()) / head_w
            dy = (p[:, 1].mean() - p0[:, 1].mean()) / head_w
            ws = (p[:, 0].max() - p[:, 0].min()) / w0 if w0 > 0 else 1
            moved |= abs(dx) > 0.003 or abs(dy) > 0.003
            r.append('%+.3f, %+.3f, ×%.2f' % (dx, dy, ws))
        orders = {snaps[k][did]['draw_order'] for k, _ in poses} | {d['draw_order']}
        r.append(str(d['draw_order']) + ('→' + '/'.join(str(o) for o in sorted(orders - {d['draw_order']})) if len(orders) > 1 else ''))
        if moved:
            rows.append((d['render_order'], r))
    rows.sort(key=lambda r: -r[0])
    head = '| メッシュ | 位置x | 位置y | X+30（dx, dy, 幅） | X−30 | Y+30 | Y−30 | 描画順 |\n|' + '---|' * 8
    return head_w, head + '\n' + '\n'.join('| ' + ' | '.join(r) + ' |' for _, r in rows)


def main():
    cmo3, model3, out = sys.argv[1:4]
    head_id = sys.argv[4] if len(sys.argv) > 4 else None
    doc = t.Cmo3(cmo3)
    roots, children = structure(doc.xml)
    names = {}
    for m in re.finditer(r'<CArtMeshSource xs\.id.*?<s xs\.n="localName">([^<]*)</s>.*?<CDrawableId xs\.n="id" idstr="([^"]*)"', doc.xml, re.S):
        names[m.group(2)] = m.group(1)
    x = doc.xml
    counts = {k: len(re.findall(r'<%s xs\.id' % k, x)) for k in ['CArtMeshSource', 'CWarpDeformerSource', 'CRotationDeformerSource', 'CGlueSource', 'CPartSource']}
    model = cc.Model(model3)
    md = ['# リグの解析：%s' % os.path.basename(cmo3), '',
          '数：' + '、'.join('%s %d' % kv for kv in counts.items()) + '、パラメーター %d' % len(model.param_ids), '',
          '## 1. デフォーマの木', '', tree_md(roots, children), '']
    if head_id:
        hw, tbl = motion(model, head_id, names)
        md += ['## 2. 角度X・Y ±30 での動き', '',
               '基準：`%s` の横幅 %.0f px を 1 とした比。位置は、その中心からの位置。dx は右、dy は下が＋。幅は横幅の倍率。描画順の → は、向きで変わる値。' % (head_id, hw), '',
               tbl, '']
    open(out, 'w', encoding='utf-8').write('\n'.join(md))
    print('ANALYZE_RIG_DONE', out)


if __name__ == '__main__':
    main()
