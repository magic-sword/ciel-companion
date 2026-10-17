"""くぼみの影（Cheek_Dimple_L・Cheek_Dimple_R）を、ほっぺの仕組みにつなぐ（v64、段階 2）。

段階 1（integrate-cheek.py）のモデルに、Cubism で cheek-dimple-additions.psd の 2 層を貼り付けて保存した
imported.cmo3 を使う（貼り付けると「位置調整用デフォーマ」の子になる）。
- 顔の曲面の子にする（顔の向き・ほっぺのワープと一緒に動く）。頂点の位置は、層の画像の座標（＝キャンバスの画素）から、
  顔の曲面の正面の格子の割合へ直す。
- 不透明度を、押す量（ParamCielCheekPoke{L,R}）の 0 → 1 で、0 → SHADE にする（押した一瞬だけ、淡く出る）。
- 描画順は、顔の肌の影（Face_Shadow_Hair 260）より上、ほっぺの赤み（471〜）より下。

実行  python -I scripts/live2d/v64/integrate-dimple.py imported.cmo3 出力.cmo3
"""
import importlib.util
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import cmo3_tool as t


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


import cmo3_editor as lib  # noqa: E402
cheek = module('integrate_cheek', HERE / 'integrate-cheek.py')
named, array = lib.named, lib.array

SHADE = 0.3          # 押しきったときの、くぼみの影の不透明度（ユーザーの確認：3 割が良い）
DRAW_ORDER = 262
MESHES = {'Cheek_Dimple_L': 'ParamCielCheekPokeL', 'Cheek_Dimple_R': 'ParamCielCheekPokeR'}
# 貼り付けた層は、キャンバス全体を覆う 4 頂点のメッシュ。くぼみの絵（Cheek_Dimple_*_A.png の不透明な範囲）に切り詰める
BBOX = {'Cheek_Dimple_L': (1271, 1202, 1338, 1269), 'Cheek_Dimple_R': (880, 1202, 946, 1268)}


def invert_bilinear(g, p):
    """格子 g（(n+1)×(n+1)×2、キャンバス）の中で、点 p（N×2）の割合 (u, v) を求める（ニュートン法）"""
    n = g.shape[0] - 1
    uv = np.full((len(p), 2), 0.5)
    for _ in range(30):
        q = cheek.bilinear(g, uv)
        h = 1e-4
        du = (cheek.bilinear(g, uv + [h, 0]) - q) / h
        dv = (cheek.bilinear(g, uv + [0, h]) - q) / h
        r = p - q
        det = du[:, 0] * dv[:, 1] - du[:, 1] * dv[:, 0]
        uv[:, 0] += (r[:, 0] * dv[:, 1] - r[:, 1] * dv[:, 0]) / det
        uv[:, 1] += (du[:, 0] * r[:, 1] - du[:, 1] * r[:, 0]) / det
    assert np.abs(cheek.bilinear(g, uv) - p).max() < 0.01
    return uv


def main():
    src, dst = sys.argv[1:3]
    doc = t.Cmo3(src)
    for name, bbox in BBOX.items():
        doc.crop_quad_mesh(name, bbox, margin=4)
    # 段階 1 で、顔の曲面は Cheek_Squish_R の子（格子の割合の座標）になった。正面の格子は GRID_BOX の範囲なので、そのまま画素へ直す
    face_unit = np.array(doc.warp_keyform_positions('顔の曲面')[cheek.neutral_index(doc, '顔の曲面')])
    n = int(round(np.sqrt(len(face_unit)))) - 1
    x0, y0, x1, y1 = cheek.cs.GRID_BOX
    face_canvas = (face_unit * [x1 - x0, y1 - y0] + [x0, y0]).reshape(n + 1, n + 1, 2)
    e = lib.Editor(doc)
    warps = {named(w, 's', 'localName').text: w for w in e.root.iter('CWarpDeformerSource') if w.get('xs.id')}
    face = warps['顔の曲面']
    face_guid = named(face, 'CDeformerGuid', 'guid').get('xs.ref')
    warp_coord = named(warps['左目玉の曲面'], 'CoordType', 'coordType').get('xs.ref')
    for name, pid in MESHES.items():
        mesh = e.meshes[name]
        points = np.array([float(q) for q in named(mesh, 'float-array', 'point').text.split()]).reshape(-1, 2)
        uv = invert_bilinear(face_canvas, points)
        named(mesh, 'CDeformerGuid', 'targetDeformerGuid').set('xs.ref', face_guid)
        for form in named(mesh, 'carray_list', 'keyforms'):
            pos = named(form, 'float-array', 'positions')
            pos.set('count', str(uv.size))
            pos.text = array(uv)
            named(form, 'CoordType', 'coordType').set('xs.ref', warp_coord)
            named(form, 'i', 'drawOrder').text = str(DRAW_ORDER)
        e.opacity_binding(name, pid, True, (0, 1))
        forms = list(named(mesh, 'carray_list', 'keyforms'))
        assert len(forms) == 2, (name, len(forms))
        named(forms[1], 'f', 'opacity').text = str(SHADE)
    e.flush()
    missing = {n.get('xs.ref') for n in e.root.iter() if n.get('xs.ref') and n.get('xs.ref') not in e.ids}
    assert not missing, missing
    doc.save(dst)
    print('CHEEK_DIMPLE_READY', dst)


if __name__ == '__main__':
    main()
