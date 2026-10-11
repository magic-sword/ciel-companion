# -*- coding: utf-8 -*-
"""Generate Japanese handoff notes from verified layer metadata."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'assets/ciel/layers/v10'; GEN=ROOT/'assets/ciel/generated/v10'
state=json.loads((OUT/'layer-state.json').read_text(encoding='utf-8'))
rows=state['layers']
head='''# v10 層の担当と受け渡し

2172×2896、RGBA、全層キャンバス原点 (0,0)。L/R はキャラクター視点、R＝画面左。通常合成。v9 の確認 A はユーザー承認済みとして扱う。差分の新しい表情は今回の制作案。

## PSD を作る前に

`psd-manifest.json` は全層の**下→上**の一覧。形式は既存ビルダー互換。ただし `scripts/live2d/gimp/build_layers_psd.py` は表示状態を読まず、全層を表示して読み込む。**そのままでは閉じ目と複数の口が同時表示される。**

Claude Code は既存ビルダーの代わりに `scripts/live2d/v10/build_psd_with_state.py` を同じ GIMP 3 バッチ環境で実行する。このラッパーは既存スクリプトをメモリ上で読み、挿入時の表示設定と保存後の表示状態照合を加える。既存ファイルは変更しない。環境変数 `CIEL_PROJECT_ROOT` はプロジェクトルート、`CIEL_PSD_MANIFEST` は `assets/ciel/layers/v10/psd-manifest.json`。

出力先の宣言は `assets/ciel/psd/ciel-v10`。今回の許可された書き込み先の外なので、PSD/XCF 自体は今回作成しない。PSD の保存・再読込、Cubism の取り込みは**未確認**。ラッパーも GIMP 上での実行は**未確認**。既存ビルダーを直接使う場合は、保存前に下表の OFF を非表示にし、保存後に再読込して確認すること。

## 表示・動きの契約

- 通常顔：下表 ON のみ。閉じた微笑み＋開眼。
- 閉眼図：左右の `Eye_*_Closed` のみ ON、他の `Eye_*` はすべて OFF。顔肌が下にあるため眼球は残らない。
- 小口：`Mouth_Line_Upper/Lower` OFF、`Mouth_Small_*` の5枚 ON、Large OFF。大口は Small と Large を逆にする。`Mouth_Skin_Upper/Lower` は各状態で ON。
- 差分完成形は形状確認用の終端素材。通常まばたきは白目・まぶた・まつげの連続変形で作る。差分のクロスフェードだけで通常まばたきを完成扱いにしない。
- 丸い虹彩と点光は Cubism で同側の白目へクリッピングする。PNG の通常合成ではまぶた肌が余分な上端を隠す。PSD 自体に Cubism のクリッピング設定は含められない。視線移動と閉眼直前の漏れはリグで確認する。
- 髪は3前髪束＋左右の頬髪＋左右の長髪。頭頂は各束が分担。独立した冠を水平に切る案は移動時に境界が目立ったため不採用。`Hair_Crown` は納品しない。
- 髪の32pxの下塗りは、元の不透明な上位束の下へ追加したもの。輪郭線を複製せず、生成した白銀の下塗りを隣接する既存髪の色へ合わせている。外周の透明域を一律膨張していない。根元は共通親で固定し、毛先へ向けて変形量を増やす。
- 耳の付け根毛は頭側に固定、耳の外側・内毛は耳親へ。強く倒した裏面は今回の対象に含めていない。耳の強い倒れの必要量は未確認。
- 顔・首の陰影、前髪より上の眉、首輪と胸飾りの間隔は v9 を継承。頬の弱い立体陰は Face_Skin 内に保持し、新しい頬染めは加えない。

## 全層

|下→上|名前|通常|描いた内容・由来|下に隠れる相手|動き／クリップ|
|---:|---|---|---|---|---|
'''
lines=[]
for i,r in enumerate(rows,1):
    lines.append(f"|{i}|`{r['name']}`|{'ON' if r['visible'] else '**OFF**'}|{r['description']}|{r['hidden_by']}|{r['motion']}"+(f"／クリップ：{r['clip']}" if r['clip'] else '')+'|')
(OUT/'layers.md').write_text(head+'\n'.join(lines)+'\n',encoding='utf-8')
calls=[dict(id=1,original='parts/Features_01.png',references=['assets/ciel/layers/v9/compose.png','assets/ciel/layers/v9/Hair_FrontAssembly.png'],
    purpose='左右の丸い虹彩上端、閉じ目、会話用の小口・大口。見える通常虹彩はv9から保持。',
    prompt='Create a production Live2D separated parts texture sheet for the exact silver-haired cyan-eyed anime dog-girl in reference. Transparent background. Do NOT draw a whole character. Arrange clearly separated with generous empty transparent gaps, NO labels/text: TOP LEFT a full round cyan iris with dark blue upper gradient, black vertical pupil, matching reference eyes, but NO white specular highlights; TOP RIGHT a second matching full round cyan iris. MIDDLE LEFT tiny gently open smiling anime mouth, dark muted mauve oral cavity, one subtle small white canine on upper edge and pink tongue along bottom, thin soft muted mauve lip outline; MIDDLE RIGHT same mouth opened wider for talking but still small and cute. BOTTOM LEFT isolated gently closed right eyelid eyelash curve, chocolate mauve thick tapered anime lashes, exact reference style; BOTTOM RIGHT matching opposite closed eyelid. All elements alone with no facial skin surrounding them. Retain delicate reference style. Output save if possible under D:/CIEL/apps/ciel-companion/assets/ciel/generated/v10/parts/Features_01.png.'),
 dict(id=2,original='parts/Hair_Underpaint_01.png',references=['assets/ciel/generated/v10/references/Hair_FrontAssembly.png'],
    purpose='後ろ髪の丸い上端と、髪の分割境界の下塗り。原本外周のハローは採用せず内側の塗りだけ使用。',
    prompt='Production Live2D hidden underpainting texture based on attached silver hair. One single broad smooth egg-shaped mass of white silver hair, rounded dome at top and rounded at bottom, tall oval aspect ratio 3:4. Entire interior filled with continuous opaque pale cool white/silver/lavender hair shading, very soft flowing vertical broad strand shading, NO dark internal outlines, NO parting line, NO fringe gaps, NO face opening, NO holes, NO wispy fringes. This is the hidden backing under separate hair locks and the round back of the head, NOT a hairstyle redesign. Same pure white and pale bluish lavender palette as attached. Subtle soft hair texture, no hard lines inside. Transparent outside oval, no shadow outside silhouette.')]
for c in calls:
    c.update(sha256=hashlib.sha256((GEN/c['original']).read_bytes()).hexdigest(),transparent_background=True,status='adopted_in_part')
(GEN/'generation-log.json').write_text(json.dumps(dict(limit=40,attempted_calls=2,successful_calls=2,calls=calls,
    notes='生成ツールの自動キャッシュはツール管理。制作側の書き込みは指定の3つのv10ディレクトリ内。'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Wrote layer documentation and generation log')

v=json.loads((OUT/'validation.json').read_text(encoding='utf-8'))
gapcases=[c for c in v['hair_interior_coverage'] if c['interior_pixels_below_alpha_240']]
metrics=v['comparison']
metricrows='\n'.join(f"|{n}|{m['mean_absolute_rgb']:.6f}|{m['rms']:.6f}|{m['pixels_over_10']}|{m['maximum']:g}|" for n,m in metrics.items())
report=f'''# シエル v10：段階3・動かす層への分割とPSD受け渡し

2026-10-11。確認Aはユーザー承認済み（「v9 の品質は素晴らしい。見違えるほど改善された」）。v9 の古い報告の承認待ち表記は変更せず、今回の指示を基準として扱った。

構成の基準は[相談回答2章](../../../../docs/ciel-codex-consult-parts-ja.md)、[v9のレイヤー契約](../../generated/v9/layer-contract.md)、[計画書8.3](../../../../docs/ciel-live2d-rebuild-analysis-plan-ja.md)。

**2172×2896の透明RGBA PNGを{v['layer_count']}層、通常表示{v['normal_visible']}層・差分非表示{v['layer_count']-v['normal_visible']}層として出力した。** 画像生成は **2回／上限40回**。通常正面はv9の配置・輪郭・見える原画を保持し、分割後に重ね直して比較した。PSDを作るための全層一覧と表示設定も用意した。

## 成果物と最初に見る図

- [v9／v10 顔の比較](proofs/compare-face.png)：共通座標・0.7倍。
- [v9／v10 上半身](proofs/compare-upper.png)：全キャンバス・0.30倍。
- [目の開閉・口3段階](proofs/expressions.png)：同じ顔範囲・0.85倍。
- [目と口の差分・正面全体](proofs/expressions-front.png)：共通座標・0.45倍。
- [髪を外した顔](proofs/face-without-hair.png)：0.85倍。耳と髪の落ち影も外した点検用。完成顔の印象判定は髪を戻した比較図で行う。
- [分解図1](proofs/exploded-01.png)・[2](proofs/exploded-02.png)・[3](proofs/exploded-03.png)・[4](proofs/exploded-04.png)：全層。各セルに名前、倍率、通常ON/OFF、元キャンバス上の外接範囲。
- [目の内部](proofs/eyes-detail.png)・[口の内部](proofs/mouth-detail.png)・[髪の下地](proofs/hidden-hair.png)。
- [通常顔の原寸PNG](proofs/compose.png)、[画素差5倍強調](proofs/difference-5x.png)。

[PSD用全層一覧](psd-manifest.json) ／ [全層の説明・表示とクリッピングの契約](layers.md) ／ [機械可読の層状態](layer-state.json) ／ [検査結果](validation.json)

## 分割と補完

|部位|今回の担当|
|---|---|
|前面髪|前髪3束、頬を包む内側の横髪L/R、胸へ下る長髪L/Rの7層。元の毛先と外形を保持。上位の束の下に32pxの下塗り。頭頂は各束が分担し、独立したHair_Crownは不採用。|
|後ろ髪|v9の髪を保持し、y365の切断幅全体に丸い頭部の上端を補完。上端の新しい塗りを既存の切断位置の色へつないだ。|
|目L/R|白目、丸い虹彩＋瞳孔、4つの白い点光、上下のまぶた肌、上下まつげ、二重、閉じ目。見える虹彩はv9、隠れる上端を新素材で補完。青い面反射は虹彩の彩色に保持。|
|口|v9の微笑みを上下線へ分割。周りの肌を別層にし、小口・大口はそれぞれ口腔、舌、小さな八重歯、上下線へ分離。口腔には歯・舌・線を重複して焼き込まない。|
|耳L/R|外側、内毛、付け根毛。内毛の下の連続面と、根元の重なりを補完。通常の耳親を共有する構成。|
|首輪|前帯から金具を独立させ、金具の下の帯を補完。後帯・内側・丸飾りはv9を流用。|
|顔・眉・鼻・影|配置を保持。眉は前髪より上。髪の落ち影とNeck_Shadow_Chinを独立保持。頬の弱い立体陰はFace_Skin内、頬染めの追加なし。|
|体・上着・ファー|v9をそのまま流用。胸の菱形もBody内に保持。|

通常正面では、目の位置と大きさ、前髪の目へのかかり方、頬の囲み、閉じた微笑み、首の暗さ、首輪と胸飾りの間隔を比較した。開口は元の小さな口幅を基準に、閉口88px相当、小口88px・大口96pxの配置枠に収めた。閉眼図では白目・虹彩・二重を残さず、閉じ目の線へ差し替えた。新しい口と閉じ目に対するユーザー評価は**未確認**。

## 小さな移動と限界

各部位に (-20,0)、(+20,0)、(0,-20)、(0,+20)、(-20,-20)、(+20,+20) px を与えた**{v['translation_cases']}ケース**を作成した。PNGをそのまま動かす検査であり、Cubismのメッシュ・デフォーマ・物理は使っていない。固定された根元を持つ実際の髪揺れとは異なる、接続の余裕を見る強めの試験。

- 前髪：[左束](proofs/move-Hair_Front_1.png)・[中央束](proofs/move-Hair_Front_2.png)・[右束](proofs/move-Hair_Front_3.png)
- 頬髪：[R](proofs/move-Hair_Side_R_Inner.png)・[L](proofs/move-Hair_Side_L_Inner.png)
- 長い髪：[R](proofs/move-Hair_Side_R_LongFront.png)・[L](proofs/move-Hair_Side_L_LongFront.png)
- 耳：[R](proofs/move-Ear_R.png)・[L](proofs/move-Ear_L.png)、[首輪金具](proofs/move-Choker_Buckle.png)
- 別途、[虹彩と点光の±20px移動](proofs/move-iris-clipped.png)を4方向作成。白目へのクリッピングをPNG合成で模擬したもの。Cubismでのクリッピング動作の確認ではない。

髪の検査では、元の不透明領域（alpha>250）の外縁から32px以上内側を対象に、移動後の髪7層だけを合成した。alpha<240となる透明抜けがあるケースは **{len(gapcases)}／42**。この検査は顔や後ろ髪で穴を隠して数えていない。外形が動いて肌が現れる部分、線の見え方、下塗りの色差は別途図で確認する必要がある。

**根元を含めた剛体移動では、分け目・束の切り替わりで線や塗りの連続性がずれる。** 根元固定の変形を前提とした素材であり、任意の±20px独立平行移動をそのまま完成した揺れとして使える、という判定ではない。髪の落ち影も移動図ではv9位置のまま。対応する髪との追従・顔へのクリッピングは段階4で調整する。耳の内毛単独変形、口の舌・歯の独立変形、まばたきの中間形は**未確認**。

Ear_Rはv9の通常配置からキャンバス上端に接しているため、上へ20px動かす固定キャンバスの図では耳先が画面外へ切れる。これは根元の下塗りの穴とは別の表示範囲の問題。実際のモデル表示範囲は段階4で確認する。虹彩の透明縁では、白目と混ざった色を透明度へ分離しているため、全画素の完全一致を主張しない。

## 補助数値とファイル検査

比較は共通の灰色背景でRGBを測定。数値の小ささだけで動作品質を合格にしない。

|範囲|RGB平均絶対差|RMS|最大チャンネル差>10の画素|最大差|
|---|---:|---:|---:|---:|
{metricrows}

- 全{v['layer_count']}層の寸法、RGBA、透明画素、非空、英数字と_の名前、重複なしを確認。
- v10スクリプトの構文とmanifest／表示状態の層順一致を確認。GIMP実行の代わりにはしていない。
- manifestの下→上順と通常表示から確認図を生成。差分は通常非表示。
- 入力v9のファイルSHA256不変：**確認済み**。同一流用素材は元PNGをバイト単位でコピー。
- [入力のSHA256](../../generated/v10/input-sha256.json)、[画像生成2回の原本・指示・参照・SHA256](../../generated/v10/generation-log.json)、[髪の担当マスク](../../generated/v10/ownership-masks.npz)を保存。
- 制作側の書き込みは `assets/ciel/generated/v10/`、`assets/ciel/layers/v10/`、`scripts/live2d/v10/` のみ。生成ツール自身の自動キャッシュはツール管理の保存先。

## Claude Code へのPSD引き渡し

`psd-manifest.json` の出力指定は依頼どおり `assets/ciel/psd/ciel-v10`。全{v['layer_count']}層を含む。

**既存の `build_layers_psd.py` は全層を表示するため、そのままでは差分が重なる。** 同じGIMP 3バッチ環境で [表示状態対応ラッパー](../../../../scripts/live2d/v10/build_psd_with_state.py) を実行する。既存ビルダーを変更せず読み込み、`layer-state.json` に従ってOFFを設定し、PSD/XCFの再読込時に名前・順序に加えて表示状態を照合する。[詳しい手順](layers.md#psd-を作る前に)。

PNG素材とmanifestまでが今回の受け渡し。PSD/XCF出力先は指定された書き込み範囲外のため作成していない。**GIMPラッパー実行、PSD/XCF保存と再読込、Cubismインポート、クリッピング設定、頭XY・連続まばたき・口パク・物理、Unity表示はすべて未確認。** 段階4の仮リグとユーザー確認Bへ進むための素材であり、動いた顔の承認を意味しない。

再現用：`python -B scripts/live2d/v10/build.py` → `python -B scripts/live2d/v10/verify.py` → `python -B scripts/live2d/v10/document.py`。生成原本を使い、画像生成APIを再度呼ばずに組み立てと確認図を再作成する。
'''
(OUT/'report.md').write_text(report,encoding='utf-8')
print('Wrote Japanese report; remaining transparent-gap cases:',len(gapcases))
