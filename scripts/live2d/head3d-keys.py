"""頭を立体（楕円体）として回し、Head_Warp の格子（X×Y の 25 キー）の位置を計算して設定する。

入力  Head_Warp が、角度X（5キー）と角度Y（5キー）の格子を持つ .cmo3（build-head3d-base.py のあと、Cubism で角度Yにキーを付け、
      mesh_ops.insert_second_key で ±15 のキーを足したもの）
出力  引数の .cmo3

モデル（画像座標 px）
  顔の中心の軸 x = CX、縦の回転の軸 y = PIVOT_Y（目の高さ）。
  頭の形：円柱（頭蓋）の前面を、平らな板で切り落とした形。板の輪郭は、逆さのホームベース（五角形）：
        額・頬は幅 ±PLATE_W、頬の下から顎の先（幅 ±CHIN_W、y = CHIN_Y）へ、まっすぐ細くなる。
        板（z = PLATE_Z）の内側は平ら、外側は、円柱の側面（半径 √(w(y)² + PLATE_Z²)、w は、その高さの板の半幅）に沿って奥へ回る。
        顎は細くなっても、先は手前（PLATE_Z）にある。顎の下（y > CHIN_Y）は、首へ向かって奥へ消える。額より上は、頭頂へ丸く奥へ消える。
  格子の各頂点（基準の位置 (x, y)）は、この表面の点 (x − CX, y − PIVOT_Y, z0) とみなす。
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
PIVOT_Y = 1042.0
PLATE_Z = 410.0      # 顔の板の手前の位置（目の高さの奥行き）
PLATE_W = 372.0      # 額・頬の半幅
CHEEK_Y = 1130.0     # ここから下で、板が細くなり始める
CHIN_Y = 1395.0      # 顎の先
CHIN_W = 75.0        # 顎の先の半幅
TOP_Y = 500.0        # ここより上は、頭頂へ丸く奥へ消える
TOP_R = 650.0
NECK_FADE = 200.0
EAR_Y = 800.0        # これより上の、板の外側（耳・頭の上の横の髪）は、奥へ回らず、板に近い深さに置く
EAR_BLEND_Y = 600.0
EAR_Z = 290.0        # 耳は、板と同じ向きの平らなカード（回しても、細くつぶれない）
EAR_W = 700.0
KEYS = [-30.0, -15.0, 0.0, 15.0, 30.0]
# 角度X（＋が画面の右を向く）→ yaw（度）。目の間隔の縮み（0.876・0.986・0.951・0.795）と、目の中心の動きから。
YAW = {-30.0: -26.5, -15.0: -10.5, 0.0: 0.0, 15.0: 13.0, 30.0: 36.0}
# 見本では、上下を向いた斜めの向きの方が、X だけの向きより、横の回りが強い（同じ「15°」「30°」でも 5〜17° 多い）。
# 上下に動かしても顔が横にずれないよう、差の 6 割だけ、足す。{X のキー: {|Y のキー|: 足す角度（度）}}
YAW_EXTRA = {
    -30.0: {15.0: -9.0, 30.0: -15.0},
    -15.0: {15.0: -11.0, 30.0: -9.0},
    15.0: {15.0: 17.0, 30.0: 12.0},
    30.0: {15.0: 7.0, 30.0: 1.0},
}
EXTRA_RATE = 0.6
# 角度Y（＋が上向き）→ pitch（度）。目の中心の縦の動き（−195・−158・＋141・＋191）から。
PITCH = {-30.0: -28.5, -15.0: -21.0, 0.0: 0.0, 15.0: 22.0, 30.0: 29.0}


def plate_half_width(y):
    if y <= CHEEK_Y:
        return PLATE_W
    if y >= CHIN_Y:
        return CHIN_W
    return PLATE_W + (CHIN_W - PLATE_W) * (y - CHEEK_Y) / (CHIN_Y - CHEEK_Y)


def depth(x, y):
    w = plate_half_width(y)
    ax = abs(x - CX)
    if ax <= w:
        z = PLATE_Z
    else:
        r2 = w * w + PLATE_Z * PLATE_Z          # 円柱の半径の二乗
        z = math.sqrt(max(0.0, r2 - ax * ax))
    if y < EAR_Y and ax <= EAR_W:
        # 頭の上（耳・頭頂の髪）は、高さによらず、ほぼ同じ深さ EAR_Z に置く（耳が、斜めにゆがまない）。
        # 額に近づくにつれて、板の深さへつなぐ（EAR_BLEND_Y から EAR_Y まで）。
        k = min(1.0, max(0.0, (y - EAR_BLEND_Y) / (EAR_Y - EAR_BLEND_Y)))
        z = EAR_Z + (z - EAR_Z) * k
    elif y < TOP_Y:
        z *= math.sqrt(max(0.0, 1.0 - ((TOP_Y - y) / TOP_R) ** 2))
    if y > CHIN_Y:
        z *= max(0.0, 1.0 - ((y - CHIN_Y) / NECK_FADE) ** 2)
    return z


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
            yaw = YAW[kx] + EXTRA_RATE * YAW_EXTRA.get(kx, {}).get(abs(ky), 0.0)
            d.set_warp_keyform_positions(name, yi * 5 + xi, rotated(rest, yaw, PITCH[ky]))
    d.save(dst)
    print('Head_Warp 25 keys ->', dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
