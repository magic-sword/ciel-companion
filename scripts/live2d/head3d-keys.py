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
CHEEK_BULGE = 0.0      # 頬の高さで、横断面を広げる量（px）。頬の輪郭がふくらむ
CHEEK_BULGE_Y = 1150.0
CHEEK_BULGE_SIG = 130.0
PROFILE_K = 0.92     # 横断面の丸さ（大きいほど丸い。小さいほど平ら）
JAW_BLEND_Y0, JAW_BLEND_Y1 = 1100.0, 1300.0   # この範囲で、顎の付近のなだらかな横断面へ移す
JAW_SOFT = 3.0       # 顎の付近の横断面の半径（顔の半幅に対する倍率。大きいほど、縁がなだらか）
EAR_BLEND_Y = 600.0
EAR_Z = 290.0        # 耳は、板と同じ向きの平らなカード（回しても、細くつぶれない）
EAR_W = 700.0
# 顔の凹凸（板の上に足す）。鼻筋の山折り、鼻頭、ふっくらした頬、口もと。板の縁では 0 になる。
NOSE_X = 0.0         # 鼻筋の x（CX からの差）
NOSE_H = 90.0        # 鼻頭の高さ
NOSE_W = 150.0       # 鼻筋の半幅（山折りの幅）
NOSE_TOP_Y = 960.0   # 鼻筋が立ち上がり始める y（目の間）
NOSE_TIP_Y = 1150.0  # 鼻頭の y
NOSE_END_Y = 1250.0  # 鼻の下で、平らに戻る y
CHEEK_DX = 215.0
CHEEK_Y = 1175.0
CHEEK_R = 165.0
CHEEK_H = 60.0       # ふっくらした頬の高さ
MOUTH_Y = 1250.0
MOUTH_RX, MOUTH_RY, MOUTH_H = 120.0, 70.0, 25.0
EDGE_FADE = 90.0
CHIN_FWD = 0.0       # 顎の先の突き出し（px）
CHIN_FWD_Y, CHIN_FWD_SX, CHIN_FWD_SY = 1420.0, 140.0, 140.0
JAW_RECEDE = 150.0     # エラ（顎の角）が奥へ下がる量（px）
JAW_KEY_RECEDE = 550.0 # 上向き 30° だけで、エラを奥へ下げる量（px）
JAW_KEY_Y0, JAW_KEY_Y1 = 1000.0, 1420.0
JAW_KEY_P0 = 22.0   # この pitch（上向き 15° のキー）までは 0
LIFT_POW = 5.0      # 持ち上げの、角度に対する曲がり（大きいほど、上向き 15° では少なく、30° で効く）
LIFT_AT_30 = 70.0  # 上向き 30° で、頭全体を上へ持ち上げる量（px）
# 目のある所は平らにする（目の中心、楕円の半径、この割合より内側は完全に平ら）
EYES = [(891.0, 1046.0), (1316.0, 1033.0)]
EYE_RX, EYE_RY = 200.0, 150.0
EYE_FLAT_CORE = 0.6
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


def smoothstep(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def relief(x, y):
    """顔の凹凸：鼻筋（山折り）と鼻頭、ふっくらした頬、口もと。"""
    dx = x - CX - NOSE_X
    r = 0.0
    # 鼻筋：横は三角形（山折り）、縦は、目の間から鼻頭へ立ち上がり、鼻の下で戻る
    lat = max(0.0, 1.0 - abs(dx) / NOSE_W)
    if y <= NOSE_TIP_Y:
        g = smoothstep((y - NOSE_TOP_Y) / (NOSE_TIP_Y - NOSE_TOP_Y))
    else:
        g = 1.0 - smoothstep((y - NOSE_TIP_Y) / (NOSE_END_Y - NOSE_TIP_Y))
    r += NOSE_H * lat * g
    # 頬（左右）
    for sx in (-1.0, 1.0):
        d2 = ((x - CX - sx * CHEEK_DX) ** 2 + (y - CHEEK_Y) ** 2) / (CHEEK_R * CHEEK_R)
        if d2 < 1.0:
            r += CHEEK_H * (1.0 - d2) ** 1.5
    # 口もと
    d2 = ((x - CX) / MOUTH_RX) ** 2 + ((y - MOUTH_Y) / MOUTH_RY) ** 2
    if d2 < 1.0:
        r += MOUTH_H * (1.0 - d2) ** 1.5
    return r


def depth(x, y):
    """顔の表面の深さ。目のある所は、目の中心の接平面へ寄せる（目が曲面に沿って曲がらず、平行移動と縮みだけになる）。"""
    z = depth_curved(x, y)
    for ex, ey in EYES:
        d2 = ((x - ex) / EYE_RX) ** 2 + ((y - ey) / EYE_RY) ** 2
        if d2 < 1.0:
            z0 = depth_curved(ex, ey)
            gx = (depth_curved(ex + 4.0, ey) - depth_curved(ex - 4.0, ey)) / 8.0
            gy = (depth_curved(ex, ey + 4.0) - depth_curved(ex, ey - 4.0)) / 8.0
            plane = z0 + gx * (x - ex) + gy * (y - ey)
            k = 1.0 - smoothstep((math.sqrt(d2) - EYE_FLAT_CORE) / (1.0 - EYE_FLAT_CORE))
            z = z + (plane - z) * k
    return z


def depth_curved(x, y):
    w = plate_half_width(y)
    ax = abs(x - CX)
    # 顔の横断面は、丸い（楕円）：中央（鼻筋）が手前で、左右へ向かって奥へ回る。逆さのホームベース形の輪郭は、
    # その高さでの顔の半幅 w に比例した半径 w / PROFILE_K で表す（顎に向かって細くなる）。
    bump = CHEEK_BULGE * math.exp(-((y - CHEEK_BULGE_Y) / CHEEK_BULGE_SIG) ** 2)
    rf = (w + bump) / PROFILE_K
    u = max(0.0, 1.0 - (ax / rf) ** 2)
    z = PLATE_Z * math.sqrt(u)
    # 顎の付近（顔が細くなる所）では、縁で深さが急に 0 へ落ちる（sqrt の傾きが無限大）と、格子のマス目ごとに折れて、
    # 上を向いたとき顎の下端がジグザグになる。頬から顎へ、縁へなだらかに落ちる形（放物線、半径は JAW_SOFT 倍）へ移す。
    jaw = smoothstep((y - JAW_BLEND_Y0) / (JAW_BLEND_Y1 - JAW_BLEND_Y0))
    if jaw > 0.0:
        z_soft = PLATE_Z * max(0.0, 1.0 - (ax / (rf * JAW_SOFT)) ** 2)
        z = z + (z_soft - z) * jaw
    if y < EAR_Y and ax <= EAR_W:
        # 頭の上（耳・頭頂の髪）は、高さによらず、ほぼ同じ深さ EAR_Z に置く（耳が、斜めにゆがまない）。
        # 額に近づくにつれて、板の深さへつなぐ（EAR_BLEND_Y から EAR_Y まで）。
        k = min(1.0, max(0.0, (y - EAR_BLEND_Y) / (EAR_Y - EAR_BLEND_Y)))
        z = EAR_Z + (z - EAR_Z) * k
    elif y < TOP_Y:
        z *= math.sqrt(max(0.0, 1.0 - ((TOP_Y - y) / TOP_R) ** 2))
    if y > CHIN_Y:
        z *= max(0.0, 1.0 - ((y - CHIN_Y) / NECK_FADE) ** 2)
    # 顎の先は手前へ突き出し、エラ（顎の角）は奥へ下がる。上を向くと、手前の顎の先ほど大きく上がり、
    # 顔の下の輪郭が V から凹（⌒）へ反転する（お手本の上向き 30°）。
    if CHIN_FWD or JAW_RECEDE:
        gy = math.exp(-((y - CHIN_FWD_Y) / CHIN_FWD_SY) ** 2)
        z += CHIN_FWD * math.exp(-((x - CX) / CHIN_FWD_SX) ** 2) * gy
        jaw2 = smoothstep((y - JAW_BLEND_Y0) / (JAW_BLEND_Y1 - JAW_BLEND_Y0))
        z -= JAW_RECEDE * jaw2 * min(1.0, ax / PLATE_W) ** 2
    # 顔の凹凸は、板の内側だけ。縁（板の半幅）に近づくと 0 になる
    env = min(1.0, max(0.0, (w - ax) / EDGE_FADE))
    if env > 0.0 and y < CHIN_Y:
        z += relief(x, y) * env
    return z


def head_lift(pitch_deg):
    """上を向くほど、頭全体を上へ持ち上げる量（px）。お手本の上向き 30° では、目・顎が回転だけの場合より約 70px 上がる。"""
    return LIFT_AT_30 * (max(0.0, pitch_deg) / 29.0) ** LIFT_POW


def jaw_key_recede(x, y, pitch_deg):
    """上向き 30° のキーだけで、エラを奥へ下げる量。お手本では、15° の顎はまだ V（下へ凸）で、30° で凹（⌒）へ反転する。
    一つの立体の形では、この反転を 30° だけに起こせないので、輪郭用の形を、上向きの角度に応じて足す（キーごとの輪郭の変形）。"""
    k = smoothstep((pitch_deg - JAW_KEY_P0) / (PITCH[30.0] - JAW_KEY_P0))
    if k <= 0.0:
        return 0.0
    # 縦の範囲を広く取る（狭いと、下げる量の差で格子が上下に折り返し、頬の横の髪がちぎれる）
    jaw = smoothstep((y - JAW_KEY_Y0) / (JAW_KEY_Y1 - JAW_KEY_Y0))
    return JAW_KEY_RECEDE * k * jaw * min(1.0, abs(x - CX) / PLATE_W) ** 2


def rotated(rest, yaw_deg, pitch_deg):
    p, q = math.radians(yaw_deg), math.radians(pitch_deg)
    out = []
    for x, y in rest:
        X, Y, Z = x - CX, y - PIVOT_Y, depth(x, y)
        X1 = X * math.cos(p) + Z * math.sin(p)
        # 上向きのキーだけの輪郭の形は、縦の動きにだけ効かせる（横を向いたときに、頬の横の髪を横へ押し出さない）
        Z1 = -X * math.sin(p) + (Z - jaw_key_recede(x, y, pitch_deg)) * math.cos(p)
        Y1 = Y * math.cos(q) - Z1 * math.sin(q) - head_lift(pitch_deg)
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
