"""Head_Warp に、角度Xの5点キー（-30・-15・0・15・30）を作る。

入力  assets/ciel/rig/ciel-blink-test.cmo3（目・口は move_mesh_into_warp で Head_Warp の子にしてあること）
      assets/ciel/head-turn-measure.json（顔の向きの見本から測った、虹彩の位置）
出力  引数の .cmo3

考え方：格子の頂点（6列×6行）を、横にずらす。
  顔の中心の動き dx(角度)：測定値（第12.21節）。−30＝−178、−15＝−73、0、+15＝+87、+30＝+238（px、基準画像の座標）。
  横幅の縮み s(角度)：目の間隔の比（370を1とする）。−30＝0.876、−15＝0.986、0、+15＝0.951、+30＝0.795。
  各頂点 (x, y) → x' = cx + (x − cx) * s + dx * w(列)。cx＝顔の中心の x（基準画像で 約 1104）。
  w(列)：顔の中央に近い列は 1、外側の列は小さい（髪・耳は顔より少なく動く）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmo3_tool as t

ANGLES = [-30.0, -15.0, 0.0, 15.0, 30.0]
DX = {-30.0: -178.0, -15.0: -73.0, 0.0: 0.0, 15.0: 87.0, 30.0: 238.0}
SCALE = {-30.0: 0.876, -15.0: 0.986, 0.0: 1.0, 15.0: 0.951, 30.0: 0.795}
CX = 1104.0   # 顔の中心の x（基準画像の座標）
# 格子の列ごとの重み（左から右へ 6 列）。顔の中央（列2・3）が 1、外側へ向かって小さくする。
WEIGHT = [0.35, 0.7, 1.0, 1.0, 0.7, 0.35]


def turned(center, angle):
    out = []
    for i, (x, y) in enumerate(center):
        col = i % 6
        nx = CX + (x - CX) * SCALE[angle] + DX[angle] * WEIGHT[col]
        out.append((nx, y))
    return out


def main(src, dst):
    d = t.Cmo3(src)
    kf = d.warp_keyform_positions('Head_Warp')
    if len(kf) != 3:
        raise SystemExit('expected 3 keyforms, found %d' % len(kf))
    center = kf[1]
    # 既存の3キー（-30, 0, 30）の位置を設定し直し、-15 と 15 を挿入する。
    d.set_warp_keyform_positions('Head_Warp', 0, turned(center, -30.0))
    d.set_warp_keyform_positions('Head_Warp', 2, turned(center, 30.0))
    d.insert_warp_keyform('Head_Warp', 1, -15.0, turned(center, -15.0))
    d.insert_warp_keyform('Head_Warp', 3, 15.0, turned(center, 15.0))
    d.save(dst)
    print('Head_Warp keys:', ANGLES, '->', dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
