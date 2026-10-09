"""頭を立体（楕円体）として回し、Head_Warp の格子（X×Y の 25 キー）の位置を計算して設定する。

入力  Head_Warp が、角度X（5キー）と角度Y（5キー）の格子を持つ .cmo3（build-head3d-base.py のあと、Cubism で角度Yにキーを付け、
      mesh_ops.insert_second_key で ±15 のキーを足したもの）
出力  引数の .cmo3

モデル（画像座標 px）
  顔の中心の軸 x = CX、縦の回転の軸 y = PIVOT_Y（目の高さ）。頭の表面は、中心 (CX, EY)・半径 (RX, RY, RZ) の楕円体の前面。
  格子の各頂点（基準の位置 (x, y)）は、表面の点 (x − CX, y − PIVOT_Y, z0) とみなす。z0 は楕円体の外では 0。
  回転：先に横（yaw φ）、次に縦（pitch θ）。Y 軸は下向きが＋なので、上を向く（θ＞0）と目が上へ動く。
        X' = X cosφ + Z sinφ,   Z1 = −X sinφ + Z cosφ
        Y' = Y cosθ − Z1 sinθ
  投影は正射影（遠近の縮みは、いまは使わない）。
  角度のパラメータ値 → 実際の回転角は、見本の測定（assets/ciel/pose-grid-measure.json、12.21・12.29）に合わせた表。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmo3_tool as t

CX = 1104.0
EY = 840.0       # 楕円体の中心の y
PIVOT_Y = 1042.0
RX, RY, RZ = 520.0, 560.0, 460.0
KEYS = [-30.0, -15.0, 0.0, 15.0, 30.0]
# 角度X（＋が画面の右を向く）→ yaw（度）。目の間隔の縮み（0.876・0.986・0.951・0.795）と、目の中心の動きから。
YAW = {-30.0: -29.0, -15.0: -10.0, 0.0: 0.0, 15.0: 15.0, 30.0: 37.0}
# 角度Y（＋が上向き）→ pitch（度）。目の中心の縦の動き（−195・−158・＋141・＋191）から。
PITCH = {-30.0: -28.5, -15.0: -21.0, 0.0: 0.0, 15.0: 22.0, 30.0: 29.0}


def depth(x, y):
    u = (x - CX) / RX
    v = (y - EY) / RY
    return RZ * math.sqrt(max(0.0, 1.0 - u * u - v * v))


def rotated(rest, yaw_deg, pitch_deg):
    p, q = math.radians(yaw_deg), math.radians(pitch_deg)
    out = []
    for x, y in rest:
        X, Y, Z = x - CX, y - PIVOT_Y, depth(x, y)
        X1 = X * math.cos(p) + Z * math.sin(p)
        Z1 = -X * math.sin(p) + Z * math.cos(p)
        Y1 = Y * math.cos(q) - Z1 * math.sin(q)
        out.append((CX + X1, PIVOT_Y + Y1))
    return out


def main(src, dst, name='Head_Warp'):
    d = t.Cmo3(src)
    forms = d.warp_keyform_positions(name)
    if len(forms) != 25:
        raise SystemExit('expected 25 keyforms, found %d' % len(forms))
    rest = forms[2 * 5 + 2]            # X=0・Y=0 の形（基準の格子）
    for yi, ky in enumerate(KEYS):
        for xi, kx in enumerate(KEYS):
            d.set_warp_keyform_positions(name, yi * 5 + xi, rotated(rest, YAW[kx], PITCH[ky]))
    d.save(dst)
    print('Head_Warp 25 keys ->', dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
