# -*- coding: utf-8 -*-
"""Write v11 layer handoff and final report after visual review."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'assets/ciel/layers/v11';GEN=ROOT/'assets/ciel/generated/v11'
state=json.loads((OUT/'layer-state.json').read_text(encoding='utf-8'))
validation=json.loads((OUT/'validation.json').read_text(encoding='utf-8'))
lines=['# v11 層の担当と受け渡し','',
    '2172×2896、RGBA、62層。全層キャンバス原点 (0,0)。下→上順、名前、通常表示50層／差分非表示12層はv10と同一。L/Rはキャラクター視点（R＝画面左）。','',
    '## PSD を作る前に','',
    '`psd-manifest.json` の out は `assets/ciel/psd/ciel-v11`。PSD/XCF自体は今回の書き込み範囲外なので作成していない。','',
    '既存の `scripts/live2d/gimp/build_layers_psd.py` は表示状態を読まない。全層表示すると閉じ目や口差分が重なるため、[表示状態対応ラッパー](../../../../scripts/live2d/v11/build_psd_with_state.py)を同じGIMP 3バッチ環境で使用する。`CIEL_PROJECT_ROOT` をプロジェクトルート、`CIEL_PSD_MANIFEST` を `assets/ciel/layers/v11/psd-manifest.json` に設定する。ラッパーは既存ビルダーをメモリ上で読み、挿入時と保存後の再読込で表示状態を照合する。今回GIMP実行・PSD保存・Cubism取り込みは未確認。','',
    '## 表示とクリッピング','',
    '- 通常：ONの50層。開眼＋閉口。',
    '- 閉眼：左右の `Eye_*_Closed` のみON、他の全 `Eye_*` はOFF。',
    '- 小口：`Mouth_Line_Upper/Lower` と `Mouth_Large_*` はOFF、5枚の `Mouth_Small_*` はON。大口はSmallとLargeを入れ替える。',
    '- `Mouth_Skin_Upper/Lower` は全口状態でON。顔を変えたため、まぶた肌と口周囲肌も新しい顔色で更新済み。',
    '- 虹彩・点光は同側の白目へ、歯・舌は同サイズの口腔へ、髪影はFace_Skinへ、顎影はNeckへクリップ。PNG確認図は静止画合成。Cubismのクリッピング設定は別途必要。',
    '- 閉眼／開口差分は終端形。まばたき・口パクの連続変形や中間形はこの納品で確認していない。',
    '- 髪7層の32px下塗り、耳・首輪の分割契約はv10を継承。髪の根元を固定し毛先へ変形量を増やす。',
    '- 顔輪郭と頬の陰はFace_Skin内で一緒に補正。髪影は髪の位置から再計算。首の横移動は首輪に向かって0pxへ戻す。','',
    '## 全層','',
    '|下→上|名前|通常|内容|下に隠れる相手|動き／クリップ|',
    '|---:|---|---|---|---|---|']
for i,r in enumerate(state['layers'],1):
    motion=r['motion']+('／クリップ：'+r['clip'] if r.get('clip') else '')
    lines.append(f"|{i}|`{r['name']}`|{'ON' if r['visible'] else '**OFF**'}|{r['description']}|{r['hidden_by']}|{motion}|")
(OUT/'layers.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
wrapper=(ROOT/'scripts/live2d/v10/build_psd_with_state.py').read_text(encoding='utf-8').replace('v10','v11')
(ROOT/'scripts/live2d/v11/build_psd_with_state.py').write_text(wrapper,encoding='utf-8')
report='''# シエル v11：閉じ目・顔の土台・開いた口の修正

2026-10-11。v10を基に3点を修正し、62層を組み上げて静止画で確認した。**画像生成1回／上限20回。** 新素材の初回合成を見た後、分離した口腔の下塗りと輪郭マスクを再調整し、再合成を確認して採用した。ユーザーによるv11の承認は未取得。

## 最初に見る確認図

- [お手本／v10／v11の顔](proofs/compare-face.png)：同じ切り出し・0.55倍。
- [開眼と閉眼の幅・高さ対応](proofs/eyes-width-height.png)：同じ座標・等倍。縦の青緑線＝開眼の目頭／目尻、橙線＝開眼の中ほど、下の青線＝下縁の目安。
- [v10／v11の閉じ目・顔全体](proofs/compare-closed-face.png)：0.8倍。
- [口3段階：お手本／v10／v11](proofs/mouth-three-stages-reference.png)：同じ座標・2倍。[顔での比較](proofs/mouth-faces-reference.png)も併記。
- [お手本／v10／v11の上半身全体](proofs/compare-upper.png)：0.27倍。[v11の4表情・上半身](proofs/expressions-upper.png)。
- [v11の4表情](proofs/expressions.png)／[通常の原寸透過合成](proofs/compose.png)／[閉眼の原寸透過合成](proofs/blink.png)。

![v11の4表情](proofs/expressions.png)

## 1. 閉じ目の幅と存在感

[承認済みの目のデザイン](../../reference/ciel-eye-appearance-study-v1.png)を参照して左右の閉じ目を生成し直した。下向きの緩い弧、太さのある濃い青紫のまつげ、外側のはね、細くなる目頭を採用。v10では線が顔の内側に寄っていたため、拡大だけでなく、開眼の目頭・目尻へ位置を合わせた。

以下は透明度128超の画素の外接幅。薄いアンチエイリアスや髪に隠れる部分もあるため、見た目は上の同座標比較図で確認した。

|キャラクター側|開眼の上まつげ幅|v10閉眼幅|v11閉眼幅|v11／開眼|
|---|---:|---:|---:|---:|
|R（画面左）|263px|198px|258px|98.1%|
|L（画面右）|256px|209px|252px|98.4%|

配置枠はR `(748,1036)–(1012,1098)`、L `(1199,1026)–(1457,1088)`。線の主要部は開眼の中ほど〜下寄りで、元の下縁より上に収めた。左右の高さの違いは開眼に合わせて維持。閉眼合成では他の目層を全て消し、虹彩・白目・二重線の残留がないこと、横髪と外側まつげが自然に重なることを確認した。

## 2. 顔土台と顎・首の接続

目、眉、鼻、閉じた口の座標を保持。`Face_Skin` 内の輪郭線・頬の弱い陰影を一緒に変形した。上部〜頬上側は右18px、下部は[お手本原画](../../master/ciel-upper-body-2x.png)の見えている左右の頬線を各高さで拾い、中心と幅を補正した。一律の18px移動では下の頬線が合わないため、下部には形の補正を含む。

|測定位置|v10中心x|v11中心x|
|---|---:|---:|
|y900|1094|1112|
|y1000|1094|1112|
|y1100|1093.5|1111.5|
|y1200|1092.5|1110.5|
|y1250|1092|1104.5|
|y1300|1091|1100|
|y1350|1094|1107|
|y1380|1094.5|1113.5|
|顎先（alpha>128の最下行）|1095|1113|

顎先の実測は `(1113,1387)`。提示されたお手本の記録 `(1113,1385)` に対し横位置を一致させ、縦位置は元のまま（2px差）。輪郭の中心を全高で同じxへ機械的に揃えず、原画の左右の頬線に合わせている。

[原画への輪郭重ね図](proofs/jaw-reference-overlay.png)：桃＝v10、青緑＝v11、縦橙線＝x1113。[髪を外した顔土台と首](proofs/face-base-neck.png)、[頬髪・顎・首輪の等倍比較](proofs/cheeks-hair-neck.png)でも確認。

- `Neck` と `Neck_Shadow_Chin`：上側を右8px、y1430で4px、y1510で0pxへ減衰。首輪の接続位置を固定。
- `Face_Shadow_Hair`：髪は動かさず、髪アルファから右5px・下12px、ぼかし3px、不透明度0.25で再計算し、補正顔へクリップ。
- 上下まぶた肌4枚と口周囲肌2枚：位置とマスクを保ち、新しい顔の画素から肌色を再採取。

前髪の目へのかかり方、頬髪が輪郭を覆う箇所、顎下の首と首輪の接続を合成で確認した。全髪層・開眼の線と虹彩・服はv10の同一ファイルをコピーしている。

## 3. 開いた口の大きさ・八重歯・色

[小口参考](../../reference/mouth/mouth-small-open.png)・[大口参考](../../reference/mouth/mouth-large-open.png)・[透明口参考](../../reference/mouth/mouth_open.png)を確認。新たに小口と大口を生成し、左右の小さな八重歯、ローズモーブの口内、淡いピンクの舌、細い輪郭にした。参考の1536×1536画像は、指定どおり元キャンバスの `(318,236)` に等倍で置いて比較した。参考ごとに口を別倍率で拡大して揃える処理はしていない。

|状態|v10実画素幅×高さ|v11実画素幅×高さ|v11配置枠|
|---|---:|---:|---|
|小口|74×24px|122×36px|`(1045,1228)–(1168,1264)`|
|大口|92×60px|183×131px|`(1014,1191)–(1199,1324)`|

実画素は5層を合成したalpha>128の外接枠。v10報告の88／96pxは配置枠なので区別した。小口は幅約1.65倍・高さ1.50倍、大口は幅約1.99倍・高さ約2.18倍。閉口の線はv10をそのままコピーした。小口・大口の配置枠の横中心はともにx1106.5。参考と同様に開くほど口角が左右へ広がり上へ持ち上がる配置で、閉口→小口→大口の位置関係を同座標の比較図で確認した。連続した口パクの変形検証ではない。

口腔・舌・歯・上線・下線の5枚ずつに分割。[口の分解図](proofs/mouth-parts.png)。最初の分割では近傍画素による口腔の補完に放射状のむらが出たため不採用。見えている口腔色から滑らかな色面を推定し、歯・舌・輪郭を焼き込まない下塗りに修正。輪郭は薄い透明端ではなくalpha>128の境界から幅2.5pxを担当させ、上下線の連続性も調整した。

## 生成・補正・採用記録

[生成ログ](../../generated/v11/generation-log.json)に指示全文、参照、原本SHA256、採否を保存。[生成原本](../../generated/v11/parts/Expressions_01.png)は未加工で保存。[補正定義](../../generated/v11/corrections.json)には生成シート切り出し、トリム範囲、配置枠、縦横倍率、アルファ処理、顔と首の変形を記録した。RGBは乗算済みアルファで補間し、透明端の黒白にじみを抑えた。

[初回合成](../../generated/v11/candidates/01-expressions.png)・[初回の口腔分割](../../generated/v11/candidates/01-mouth-parts.png)・[補正後の口腔／輪郭／再合成](../../generated/v11/candidates/02-mouth-separation.png)を保存。閉じ目・口の形とサイズは初回合成で確認し、口の分割を補正した最終合成・分解図を再確認して生成1を採用した。小口・大口とも左右2本の歯が独立画素として残ることを[分割検査](../../generated/v11/mouth-separation-checks.json)でも確認。追加生成なし。

## ファイル検査と受け渡し

- **62層、2172×2896、RGBA、全層非空・透明域あり。通常50層ON／差分12層OFF。** 名前・下→上順・表示状態・排他グループ・プリセットはv10を継承。
- 22層を更新、40層はv10とバイト単位で同一。目鼻口の固定対象と髪のコピーをSHA256で確認。
- 元のv10素材・確認図・参考画像・原画、計99ファイルのSHA256不変を確認。[入力記録](../../generated/v11/input-sha256.json)。
- 通常・閉眼・小口・大口の顔内領域 `(800,950)–(1400,1350)` でalpha<250の透明抜けは全状態0画素。輪郭・髪・首は別途比較図を目視した。
- [検査結果](validation.json)／[PSD用manifest](psd-manifest.json)／[表示状態](layer-state.json)／[全層の説明](layers.md)。
- `psd-manifest.json` の out は **`assets/ciel/psd/ciel-v11`**。PSD/XCF自体は指定された書き込み範囲外なので作成していない。GIMPラッパー実行、PSD再読込、Cubism取り込み・連続まばたき・口パク・頭XY・Unity表示は未確認。

制作側の書き込みは `assets/ciel/generated/v11/`、`assets/ciel/layers/v11/`、`scripts/live2d/v11/` のみ。画像生成ツールの自動キャッシュはツール管理の保存先で、そこから原本をv11へコピーした。

再現：`python -B scripts/live2d/v11/build.py` → `python -B scripts/live2d/v11/verify.py` → `python -B scripts/live2d/v11/document.py`。保存済み原本で再構築し、画像生成は再実行しない。
'''
(OUT/'report.md').write_text(report,encoding='utf-8')
print('Wrote layers.md, report.md and PSD handoff wrapper')
