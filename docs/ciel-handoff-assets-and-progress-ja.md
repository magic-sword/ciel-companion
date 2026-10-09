# 引き継ぎ：現在の進捗と、使っている素材（2026-10-10 時点）

別セッションで、素材のレビューと整理をするための資料。詳しい経緯は `ciel-live2d-production-spec-ja.md`（12.1〜12.38）。

## 1. ひとことで言うと
- シエル（Live2D）。頭の向き（角度X×Y の 25 キー）、瞬き、半目、口パク（3 段階）が、Unity で動く。
- 頭は「丸い断面＋鼻筋・頬の凹凸」の 3D モデル（`scripts/live2d/head3d-keys.py`）で、格子の頂点を回して作る。
- 向きごとの素肌（C）・顎の裏（K）は組み込み途中。頬の赤み（N）・頭頂の髪（H）・耳の裏（E）は未組み込み。
- Unity の書き出しは、コミット `5e041c8` の状態。直した `skin7`（灰色の四角の修正）は、Python のプレビューでだけ確認済みで、Cubism の書き出しが未完了。

## 2. 使っている素材と、その状態

### 2.1 元画像（再生成できない。内容は変えない）`assets/ciel/generated/`
| 場所 | 中身 | 使い道 | 課題 |
| --- | --- | --- | --- |
| `upper-body-1x.png`、`upper-body-2x-firefly-black.jpg` | 上半身の基準画像 | 全レイヤーの元（`prepare-source.ps1`） | 解像度が粗く、拡大して使っている |
| `edits/edit-a`〜`f`、`ciel-face-half-blink` | 部分編集（目・髪・耳・体・半目） | 目・髪・耳・体のレイヤーの切り出し | **画像全体が描き直されているものがある**（d）。位置は倍率・オフセットで合わせている。`_porcelain` 版（陶器の肌）が並んである |
| `parts/mouth-*.png`、`rear-hair-layer-1536.png` | 口 3 種、後ろ髪 | 口パク、後ろ髪 | — |
| `normal/`、`expression/` | 別キャンバスの顔パーツ | 眉・口などの位置合わせ用 | 古い。使い方は `prepare-source.ps1` |
| `pose-ref/pose_x{L30,L15,0,R15,R30}_y{U30,U15,0,D15,D30}.png`（24 枚）と `_porcelain` 版 | 頭の向きの見本（1536×1536） | **動き量の測定と、見た目の比較にだけ使う（レイヤーにはしない）** | 絵全体が向きごとに描き直されていて、細部が違う。肌色は `_porcelain` が陶器の白 |
| `parts/underlayers/` 9 枚 | C-0・C-L30・C-R30（素肌）、K-2・K-3（顎の裏）、N-1（頬の赤み）、H-2・H-3（下向きの髪と耳）、E-1（耳の裏） | 向きで新しく見える面の補完 | **粗い**。下記 3 章 |

### 2.2 作ったレイヤー（Git 管理外、`scripts/live2d/build-*.py` で再生成）`assets/ciel/layers/`
- `head/`：Face_Skin、Hair_Front、Hair_Back、Hair_Under_Ear、Ear_L・Ear_R、Mouth_Closed/Small/Large、Face_Base（向きごとの素肌のシート。`build-skin-pose.py` が作る）。
- `body/`：Body_Base（顎の裏を焼き込み済み。元は `.prechin.png`）、Outer_L・Outer_R、Waist_Belt、Chest_Gem、Neck_Gear。
- `eyes/`：左右の目 4 層×（開き・半開き・閉じ）。
- 注意：`clean-ear-layers.py` 等の後処理を、レイヤーの PNG に直接かけているので、元の PNG は `*.orig.png`（耳・耳の下の髪・Body_Base の上の縁）や `.prechin.png` にある。
- モデルへの取り込み：`assets/ciel/rig/ciel-blink-test.cmo3`（Git LFS）。

## 3. 素材の問題点（レビューしてほしい所）
1. **粗さ**：基準画像が低解像度で、拡大して使うため、耳・髪の縁がぎざぎざ（耳の周りの白い切れ端、毛先の欠け）。`assets/ciel/generated/edits/edit-e` の耳は特に粗い。
2. **underlayers（C・K・N・H・E）**：
   - 生成画像は、見本と輪郭が画素単位では一致しない。位置・大きさは補正済み（v2 以降）だが、輪郭は目視で合わせている。
   - C の肌には、輪郭に茶色の細い線があり、コードで消している（`build-skin-pose.py` の `clean_edge`）。
   - K は、体の肌より、ピンク寄りの灰色。コードで色を寄せている（`bake-chin-into-body.py`）。
   - H・E は、髪の周りの残留ピクセルが残る。
3. **肌の色**：陶器のような白い肌が正。古い版（edits・pose-ref の `_porcelain` でない版）は、肌色が人間寄り。どちらを正にするか未決（`_porcelain` が正で、古い版を消す案）。消すなら、体・耳・髪のレイヤーの作り直しが要る。
4. **画像全体が描き直された見本**：レイヤーには使えない。動き量の測定用。

## 4. 作業の流れ（再現手順）
1. レイヤー生成：`scripts/live2d/build-*.py`（`prepare-source.ps1` → `build-eye-layers.ps1`、`build-head-layers.py`、`build-ear-layers.py`、`build-body-layers.py`、`build-mouth-and-hair-layers.py`）。耳の仕上げ：`clean-ear-layers.py`→`fill-ear-hull.py`→`trim-hair-under-ear.py`。体の縁：`soften-body-top.py`。顎：`bake-chin-into-body.py`。
2. モデル：`.cmo3` を `scripts/live2d/cmo3_tool.py`・`mesh_ops.py` で編集（頭のメッシュ細分化 `build-head3d-base.py`、25 キー `head3d-keys.py`、向きごとの素肌 `build-skin-pose.py`、画像差し替え `replace-image-same-size.py`）。
3. 確認：Python の近似 `preview-pose.py`・`preview-vs-ref.py`（数秒）。最終は、Cubism で、アトラス編集→書き出し→Unity の `CielRenderCheck`（`compare-pose.py`・`eval-pose-grid.py`）。
4. Cubism の操作の注意：仕様書 12.33・12.36・12.37。メモリ不足、フォーカスの奪われ方、2 台目のモニター、書き出しの失敗に注意。

## 5. 未完了のこと
- 直した skin7（灰色の四角の修正、素肌の位置の誤差ゼロ）の書き出し→Unity 確認。
- N（頬の赤み）、H（頭頂の髪）、E（耳の裏）の組み込み。後ろ髪が動かない問題。角度Z。
- 素肌 C の左右 15° の扱い（今は不透明度 0.3 の重ね）。
- 見本との差：両目の中心で、斜めの隅（±30°×±30°）が 50〜90 px ずれる。

## 6. 次のセッションでやるとよいこと（素材側）
- 粗い素材（耳・髪の縁、K・H・E の輪郭）を、高解像度で作り直すか、手で整えるかの判断。
- 肌色の統一（`_porcelain` を正にして、古い版を整理）。
- `parts/underlayers` の輪郭を、見本と重ねて検証し、必要なら、ChatGPT への再依頼（`ciel-reference-requests-underlayers-ja.md`）。
