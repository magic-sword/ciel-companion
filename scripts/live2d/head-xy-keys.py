# -*- coding: utf-8 -*-
"""頭の部位ごとのワープに、角度X・Y（3×3 キー）の形を設定する（段階 4 の仮リグ）。

前提：Cubism で、各ワープに角度X・角度Y の「キーの3点追加」をしてある（9 キーフォーム。中身はすべて正面と同じ）。
各キーの格子を、正面の格子に対して「横の拡大縮小（中心まわり）＋平行移動」で作る。動きの量は、公式サンプル
（ひより）の実測（docs/ciel-live2d-reference-rig-analysis-ja.md 4 章）を初期値にした PARTS の表。値は顔の横幅に対する比。
斜めのキー（X と Y が両方 ±30）は、X と Y の動きの足し算。

キャンバス（px）とワープの親の座標（回転デフォーマの局所座標）の換算は、子のメッシュを持つワープで、
メッシュの画像座標（point）と正規化座標（positions）から求める（同じ親の兄弟は同じ換算）。

実行  python -I scripts/live2d/head-xy-keys.py 入力.cmo3 出力.cmo3 [顔の横幅px] [全体の倍率=1.0]
"""
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmo3_tool as t

# 名前: (X+30 の横の動き, Y+30 の縦の動き（上が＋）, 向いた側に近いときの横幅, 遠いときの横幅, 近い側)
#   近い側：X+30（画面の右を向く）で手前に来るのは、画面の左側の部位（キャラクターの右 = R）
PARTS = {
    '鼻の曲面': (0.110, 0.067, 1.00, 1.00, None),
    '口の曲面': (0.080, 0.057, 1.02, 0.98, None),
    '右まゆ毛の曲面': (0.075, 0.050, 1.06, 0.90, 'R'),
    '左まゆ毛の曲面': (0.075, 0.050, 1.06, 0.90, 'L'),
    '右目の曲面': (0.060, 0.050, 1.08, 0.86, 'R'),
    '左目の曲面': (0.060, 0.050, 1.08, 0.86, 'L'),
    '顔の曲面': (0.045, 0.030, 0.96, 0.96, None),
    '前髪の曲面': (0.045, 0.040, 1.00, 1.00, None),
    '右横髪の曲面': (0.030, 0.030, 1.05, 0.95, 'R'),
    '左横髪の曲面': (0.030, 0.030, 1.05, 0.95, 'L'),
    '右耳の曲面': (0.025, 0.030, 1.00, 0.90, 'R'),
    '左耳の曲面': (0.025, 0.030, 1.00, 0.90, 'L'),
    'アホ毛の曲面': (0.030, 0.030, 1.00, 1.00, None),
}
DOWN = 0.9      # 下向きの縦の動きは、上向きの 9 割（ひよりも下向きの方が小さい）


PARAMS = {}


def load_params(x):
    for m in re.finditer(r'<CParameterSource>(.*?)</CParameterSource>', x, re.S):
        g = re.search(r'<CParameterGuid xs\.n="guid" xs\.(?:ref|id)="(#\d+)"', m.group(1))
        i = re.search(r'idstr="([^"]*)"', m.group(1))
        if not i:   # ID が参照（xs.ref）のときは、定義を探す
            r = re.search(r'<CParameterId xs\.n="id" xs\.ref="(#\d+)"', m.group(1))
            if r:
                i = re.search(r'<CParameterId [^>]*idstr="([^"]*)"[^>]*xs\.id="%s"|<CParameterId [^>]*xs\.id="%s"[^>]*idstr="([^"]*)"' % (r.group(1), r.group(1)), x)
        if g and i:
            PARAMS[g.group(1)] = i.group(1) or i.group(2)


def grid_keys(x, warp_blk):
    """ワープの keyforms の順に、(X のキーの番号, Y のキーの番号) を返す。番号は 0,1,2（-30,0,+30）。"""
    gref = re.search(r'<KeyformGridSource xs\.n="keyformGridSource" xs\.ref="(#\d+)"', warp_blk).group(1)
    ga = x.index('<KeyformGridSource xs.id="%s"' % gref)
    gb = x.index('</KeyformGridSource>', ga)
    g = x[ga:gb]
    bind_param = {}
    for b in set(re.findall(r'<KeyformBindingSource xs\.n="binding" xs\.ref="(#\d+)"', g)):
        ba = x.index('<KeyformBindingSource xs.id="%s"' % b)
        bb = x.index('</KeyformBindingSource>', ba)
        pg = re.search(r'<CParameterGuid xs\.n="parameterGuid" xs\.ref="(#\d+)"', x[ba:bb]).group(1)
        bind_param[b] = PARAMS.get(pg, pg)
    by_form = {}
    for it in re.findall(r'<KeyformOnGrid>(.*?)</KeyformOnGrid>', g, re.S):
        form = re.search(r'<CFormGuid xs\.n="keyformGuid" xs\.ref="(#\d+)"', it).group(1)
        idx = {}
        for b, k in re.findall(r'<KeyformBindingSource xs\.n="binding" xs\.ref="(#\d+)" />\s*<i xs\.n="keyIndex">(\d+)</i>', it):
            idx[bind_param[b]] = int(k)
        by_form[form] = (idx.get('ParamAngleX', 1), idx.get('ParamAngleY', 1))
    order = re.findall(r'<CWarpDeformerForm>.*?<CFormGuid xs\.n="guid" xs\.ref="(#\d+)"', warp_blk, re.S)
    return [by_form[f] for f in order]


def main():
    src, dst = sys.argv[1:3]
    face_w = float(sys.argv[3]) if len(sys.argv) > 3 else 700.0
    gain = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    doc = t.Cmo3(src)
    x = doc.xml
    load_params(x)

    # 換算：顔の曲面と、その子の Face_Skin から（局所座標の 1 単位 = 何 px か、向きを含む）
    a, b = doc.warp_block('顔の曲面')
    rest = np.array(doc.warp_keyform_positions('顔の曲面')[0])
    L0, L1 = rest.min(0), rest.max(0)
    ma, mb = doc.mesh_block('Face_Skin')
    mblk = doc.xml[ma:mb]
    pts = np.array(re.search(r'<float-array xs\.n="point" count="\d+">([^<]*)<', mblk).group(1).split(), float).reshape(-1, 2)
    k = mblk.index('<carray_list xs.n="keyforms"')
    nrm = np.array(re.search(r'<float-array xs\.n="positions" count="\d+">([^<]*)<', mblk[k:]).group(1).split(), float).reshape(-1, 2)
    px_per_norm = np.array([np.polyfit(nrm[:, i], pts[:, i], 1)[0] for i in range(2)])   # 正規化 1 = 何 px
    local_per_px = (L1 - L0) / px_per_norm
    print('換算: 局所座標/px = %.4f, %.4f' % tuple(local_per_px))

    for name, (rx, ry, near, far, side) in PARTS.items():
        try:
            a, b = doc.warp_block(name)
        except ValueError:
            print('なし:', name)
            continue
        blk = doc.xml[a:b]
        keys = grid_keys(doc.xml, blk)
        forms = doc.warp_keyform_positions(name)
        if len(forms) != 9:
            print('キーが 9 でない（%d）: %s' % (len(forms), name))
            continue
        base = np.array(forms[keys.index((1, 1))])
        c = (base.min(0) + base.max(0)) / 2
        for i, (kx, ky) in enumerate(keys):
            sx = kx - 1          # -1, 0, 1（角度X -30, 0, +30）
            sy = ky - 1          # -1, 0, 1（角度Y -30, 0, +30、+ が上向き）
            g = base.copy()
            if sx != 0:
                if side is None:
                    s = near if sx > 0 else far
                    s = (near + far) / 2 if near != far else near
                else:
                    toward = (side == 'R' and sx > 0) or (side == 'L' and sx < 0)
                    s = near if toward else far
                g[:, 0] = c[0] + (g[:, 0] - c[0]) * (1 + (s - 1) * gain)
            dx_px = rx * face_w * sx * gain
            dy_px = -ry * face_w * sy * gain * (DOWN if sy < 0 else 1.0)    # 上向き（sy>0）は画面の上（y 減少）
            g[:, 0] += dx_px * local_per_px[0]
            g[:, 1] += dy_px * local_per_px[1]
            doc.set_warp_keyform_positions(name, i, [tuple(p) for p in g])
        print('設定: %s' % name)
    doc.save(dst)
    print('HEAD_XY_KEYS_DONE')


if __name__ == '__main__':
    main()
