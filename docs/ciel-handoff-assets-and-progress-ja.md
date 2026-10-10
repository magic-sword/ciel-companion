# 引き継ぎ：現在の進捗と、使っている素材（2026-10-10 更新）

別セッションで作業を続けるための資料。詳しい経緯は `ciel-live2d-production-spec-ja.md`（12.1〜12.41）。

## 1. ひとことで言うと
- シエル（Live2D）。頭の向き（角度X×Y の 25 キー）、瞬き、半目、口パク（3 段階）が、Unity で動く。
- 髪・顔・体は、**v5 のパーツ（作り直した 18 パーツ）**。継ぎ目が上のパーツの下に隠れる分け方で、下のパーツは隠れる側まで描いてある。頭を回しても、継ぎ目や下のレイヤーが見えない。
- 頭は「丸い断面＋鼻筋・頬の凹凸」の 3D モデル（`scripts/live2d/head3d-keys.py`）で、Head_Warp の格子の頂点を回して作る。頭のパーツは Head_Warp の子。
- 目・口・犬耳は、v5 より前のメッシュをそのまま使う。
- Unity の書き出しと `assets/ciel/rig/ciel-blink-test.cmo3` は一致している。

## 2. 素材
### 2.1 元画像（再生成できない）`assets/ciel/generated/`
| 場所 | 中身 | 使い道 |
| --- | --- | --- |
| `upper-body-1x.png`（1086×1448）、`upper-body-2x-firefly-black.jpg`（2 倍） | 上半身の基準画像 | 作業の座標は 2 倍（2172×2896） |
| `v5/parts/` | 髪・顔・体の 18 パーツ（Codex が作った。`docs/ciel-codex-brief-v5-hair-parts-ja.md`） | `install-v5-parts.ps1` で `layers/` へ置く |
| `edits/`、`parts/mouth-*.png` | 目・口の部分編集 | 目・口のレイヤーの切り出し |
| `pose-ref/`（24 枚＋`_porcelain`） | 頭の向きの見本 | 動き量の測定と見た目の比較だけ |

### 2.2 レイヤー（Git 管理外。再生成する）`assets/ciel/layers/`
- `head/`・`body/`：v5 のパーツ（`install-v5-parts.ps1`）、口 3 種（`build-mouth-layers.py`）、犬耳（`build-ear-layers.py`→`clean-ear-layers.py`→`fill-ear-hull.py`）。
- `eyes/`：左右の目 4 層×（開き・半開き・閉じ）（`build-eye-layers.ps1`、`trim-half-eye-layers.py`）。

### 2.3 重なり順（下から。描画順の値は `integrate-v5.py`）
後ろ髪 → 体 → 腕の服 → 毛皮の襟 → ベルト → 宝石 → 首輪 → 顔の肌 → 頬の赤み → 鼻 → 口 → 目 → 頭頂の髪 → 犬耳 → 横髪 → 前髪 → 眉 → アホ毛

## 3. 作業の流れ
1. パーツ：`powershell -File scripts/live2d/install-v5-parts.ps1` → GIMP で `scripts/live2d/gimp/build_v5_psd.py`（`assets/ciel/psd/ciel-v5.psd`）。
2. Cubism：モデルを開き、古いメッシュを削除してから、PSD を「全てのレイヤーを新規アートメッシュとして追加」で取り込み、保存。→ `python -I scripts/live2d/integrate-v5.py 取り込み後.cmo3 出力.cmo3`（頭のパーツを Head_Warp の子にして細かく分割、体のパーツを絵の範囲に切り詰め、描画順を設定）。
3. Cubism でアトラス編集（Ctrl+T）：古い画像の削除に「はい」、未配置の画像を一覧のダブルクリックで全部配置、「自動レイアウト」→ OK。保存して書き出し（`unity/Assets/Characters/Ciel/Ciel.moc3`）。最後に `ciel-blink-test.cmo3` として保存する。
4. 確認：Python の近似 `preview-pose.py`（数秒）→ Unity の `CielRenderCheck`（`.local/render-check/request` を置いてから Unity を起動すると 33 枚を撮って終了。各メッシュの UV が `uvrects.txt` に出る）。
   - Python：`C:\Users\prog\anaconda3\python.exe -I`。Unity：`C:\app\unity\editor\6000.6.4f1\Editor\Unity.exe -projectPath unity`。
5. Cubism の画面操作の注意（仕様書 12.33・12.37・12.39）：起動時の「トライアル版」の確認がスプラッシュの裏に隠れる（ウィンドウを前に出して「使用を続ける」）。画面は java.exe。2 台目のモニター（FR2302W）に出ることがある。
6. Codex への依頼：`scripts/codex/run-codex.ps1`（`codex exec`。返答とログを `.local/codex/` に残す）。

## 4. 未完了のこと
- 上向き（角度Y＋）で、顎の下端が少し波打つ。お手本のように、顎の線を上向きで消し、顎の下を首へなめらかにつなぐ（`docs/ciel-angle-y-research-ja.md`）。
- 下向き（角度Y−）の動きを、お手本に合わせて測り直す（顔の縦の縮み、目の位置）。
- 頬の赤みが元画像より少し濃い（`Face_Blush` の不透明度で調整）。
- 後ろ髪が動かない（Head_Warp の外）。横髪の長い毛束は Head_Warp の範囲の外まで伸びている（大きく向くと確認が要る）。角度Z、髪の揺れ。

## 5. 関連資料
- `ciel-live2d-material-guidelines-research-ja.md`：素材の切り分け方の調査。
- `ciel-codex-brief-v5-hair-parts-ja.md`：v5 のパーツの方針・作り方・進捗。
- `ciel-angle-y-research-ja.md`：上向き・下向きの見え方の調査。
- `ciel-design-constraints-for-parts-ja.md`：キャラクター設計の要点（サモエドの犬耳、白磁の肌、首輪は首の前など）。
