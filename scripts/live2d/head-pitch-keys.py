"""Head_Warp_Y（Head_Warp の親）に、角度Yの5点キー（-30・-15・0・15・30）を作る。

入力  角度Yに 3 点キー（-30・0・30）を付けた Head_Warp_Y を持つ .cmo3
      （Cubism で、Head_Warp を選び、モデリング → デフォーマ → ワープデフォーマを作成 →「選択されたオブジェクトの親に設定」→
       名前 Head_Warp_Y。角度Yの行で、キーの3点追加）
出力  引数の .cmo3

考え方：格子の頂点（6列×6行）を、縦にずらす。ParamAngleY は、＋が上向き、−が下向き。
  両目の中心の縦の動き dy：見本（assets/ciel/pose-grid-measure.json の x0_y*）。正面を基準に、上30＝−195、上15＝−158、下15＝＋141、下30＝＋191（px）。
  各頂点 (x, y) → y' = y + dy * w(行)。w(行)：頭を含む上の行は 1、首に近い行は小さく、体は 0（体は Head_Warp_Y の外）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmo3_tool as t

DY = {-30.0: 191.0, -15.0: 141.0, 0.0: 0.0, 15.0: -158.0, 30.0: -195.0}
# 格子の行ごとの重み（上から下へ 6 行）。行の y は 約 -305, 396, 1097, 1798, 2499, 3201。
WEIGHT = [1.0, 1.0, 1.0, 0.2, 0.0, 0.0]


def pitched(center, angle):
    return [(x, y + DY[angle] * WEIGHT[i // 6]) for i, (x, y) in enumerate(center)]


def main(src, dst, name='Head_Warp_Y'):
    d = t.Cmo3(src)
    kf = d.warp_keyform_positions(name)
    if len(kf) != 3:
        raise SystemExit('expected 3 keyforms, found %d' % len(kf))
    center = kf[1]
    d.set_warp_keyform_positions(name, 0, pitched(center, -30.0))
    d.set_warp_keyform_positions(name, 2, pitched(center, 30.0))
    d.insert_warp_keyform(name, 1, -15.0, pitched(center, -15.0))
    d.insert_warp_keyform(name, 3, 15.0, pitched(center, 15.0))
    d.save(dst)
    print('%s keys: -30 -15 0 15 30 -> %s' % (name, dst))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
