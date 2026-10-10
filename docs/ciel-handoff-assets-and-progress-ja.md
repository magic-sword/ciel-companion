# 引き継ぎ：現在の進捗と、使っている素材（2026-10-10 更新）

別セッションで作業を続けるための資料。詳しい経緯は `ciel-live2d-production-spec-ja.md`（12.1〜12.39）。

## 1. ひとことで言うと
- シエル（Live2D）。頭の向き（角度X×Y の 25 キー）、瞬き、半目、口パク（3 段階）が、Unity で動く。
- 頭は「丸い断面＋鼻筋・頬の凹凸」の 3D モデル（`scripts/live2d/head3d-keys.py`）で、格子の頂点を回して作る。
- 首（顎の下〜首輪）は、A2（素肌ベース）の首から作った「首の幅の柱」を Body_Base に焼き込んでいる（`bake-neck-from-a2.py`）。以前の「灰色の四角」はこれで消えた。
- 向きごとの素肌のシート（Face_Base）は非表示（書き出さない）。頬の赤み（N）・頭頂の髪（H）・耳の裏（E）は未組み込み。
- Unity の書き出しと `assets/ciel/rig/ciel-blink-test.cmo3` は一致している（コミット済み）。

## 2. 素材
### 2.1 元画像（再生成できない。内容は変えない）`assets/ciel/generated/`
| 場所 | 中身 | 使い道 |
| --- | --- | --- |
| `upper-body-1x.png`（1086×1448）、`upper-body-2x-firefly-black.jpg`（2 倍） | 上半身の基準画像 | 全レイヤーの元（`prepare-source.ps1`）。作業の座標は 2 倍（2172×2896） |
| `edits/`、`parts/mouth-*.png`、`rear-hair-layer-1536.png`、`normal/`、`expression/` | 部分編集・口・後ろ髪・古い顔パーツ | レイヤーの切り出し |
| `pose-ref/`（24 枚＋`_porcelain`） | 頭の向きの見本 | 動き量の測定と見た目の比較だけ（レイヤーにしない） |
| `parts/underlayers/` | C-0（A2 の形の元）、E-1（耳の裏）、H-2・H-3（下向きの髪と耳）、N-1（頬の赤み） | E・H・N は未組み込み。粗さは `ciel-material-review-and-chatgpt-brief-ja.md` |
| `v4/` | `A2_line_ref.png`（顔〜首の素肌ベース、輪郭線あり）、`A2_face-skin-base.png`（線なし）、A2 のマスク、`cheek-hair-cover-L/R.png`（頬を覆う横髪の範囲） | 首の焼き込みの入力。頬の横髪の作業で使う。**Codex がスクリプトで作った素材で、再生成の手順は残っていない** |

### 2.2 作ったレイヤー（Git 管理外、`scripts/live2d/build-*.py` などで再生成）`assets/ciel/layers/`
- `head/`：Face_Skin、Hair_Front、Hair_Back、Hair_Under_Ear、Ear_L・Ear_R、Mouth_*。
- `body/`：Body_Base（首の柱を焼き込み済み。入力は `.prechin.png`、さらに元は `.orig.png`）、Outer_L・Outer_R、Waist_Belt、Chest_Gem、Neck_Gear。
- `eyes/`：左右の目 4 層×（開き・半開き・閉じ）。

## 3. 作業の流れ
1. レイヤー生成：`prepare-source.ps1` → `build-eye-layers.ps1`、`build-head-layers.py`、`build-ear-layers.py`、`build-body-layers.py`、`build-mouth-and-hair-layers.py`。耳：`clean-ear-layers.py`→`fill-ear-hull.py`→`trim-hair-under-ear.py`。体の縁：`soften-body-top.py`。顔の土台：`face-skin-from-a2.py`。首と首輪：`bake-neck-from-a2.py`。
2. モデル：`.cmo3` を `cmo3_tool.py`・`mesh_ops.py` で編集。画像の差し替えは `replace-image-same-size.py`、メッシュを書き出しから外すのは `hide-mesh.py`。試作は `.local/cmo3-test/`（Git 管理外）に別名で出す。
3. 確認：Python の近似 `preview-pose.py`（数秒）→ Cubism でアトラス編集（Ctrl+T）→ OK →書き出し→ Unity の `CielRenderCheck`。
   - Python：`C:\Users\prog\anaconda3\python.exe -I`（bash の `python` は使えない）。
   - Unity：`.local/render-check/request` を置いてから `C:\app\unity\editor\6000.6.4f1\Editor\Unity.exe -projectPath unity` を起動すると、33 枚を撮って終了する。各メッシュの UV 範囲が `uvrects.txt` に出る（0〜1 に収まっているか確かめる）。
4. Cubism の注意（仕様書 12.33・12.36・12.37・12.39）：**自動レイアウトは使わない**（頭が崩れる）。画像を差し替えたら、アトラス編集で、画像が 4096 の枠からはみ出していないか見る（はみ出すと Unity で別の絵が出る）。画面は java.exe が持つ。操作の前に `focus-window.ps1`。

## 4. 未完了のこと
- 上向きの顎は、仕様書 12.40 で改善（顎の線が顔と一緒に動く）。下端に小さな波が少し残る。
- 左右 ±30° で、顔の側面が切れて見える（Face_Base を外したため、向きごとの頬の輪郭がない）。
- 犬耳（サモエドの立ち耳）が、斜めの向きで頭から離れて見える。
- 頬を覆う横髪（`cheek-hair-cover-L/R.png` の範囲）を、原画から切り出して別レイヤーにする。前髪の隙間を埋める頭頂の髪の下地。
- N・H・E の組み込み、後ろ髪が動かない問題、角度Z。

## 5. 関連資料
- `ciel-live2d-material-guidelines-research-ja.md`：素材の切り分け方の調査。
- `ciel-material-review-and-chatgpt-brief-ja.md`：素材レビューと、生成への依頼の要点（一部は A2 の方針に置き換わった）。
- `ciel-design-constraints-for-parts-ja.md`：キャラクター設計の要点（犬耳、白磁の肌、首輪は首の前など）。
