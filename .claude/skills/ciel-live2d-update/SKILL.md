---
name: ciel-live2d-update
description: シエルの Live2D モデルに部品・表情・動き（パラメーター、ワープ、物理演算）を足す、直す、採用して Unity へ反映するときの手順。最新の正式モデルから始め、Git には現行だけを置く。Cubism の .cmo3 や SDK 書き出し、assets/ciel/ を触る作業では必ず使う。
---

# シエルの Live2D を更新する

## 最初に確かめること（毎回）

1. 正式モデルは `assets/ciel/rig/ciel.cmo3` だけ。ハッシュは `assets/ciel/current/approved.json` の `rig_sha256`。今の状態は `assets/ciel/README.md`・`rig/README.md`・`current/README.md` を読む。
2. 作業を始める前に確認する：`python -I scripts/live2d/official.py assets/ciel/rig/ciel.cmo3 assets/ciel/runtime/Ciel.model3.json`
   - 正式モデルのファイルが approved.json と食い違うと止まる。採用が途中で止まっているので、先に直す。
3. `.local/` の古い作業モデル（`*-integration/`・`history/` など）や Git の履歴から始めない。必ず正式モデルのコピーから始める。
4. cmo3 は Git LFS。古い版を履歴から取り出すときは `git show <rev>:<path> | git lfs smudge > 出力`。

## 役割と合否

- 素材（絵）は Codex に頼む（`scripts/codex/run-codex.ps1`、`docs/ciel-codex-request-guide-ja.md`）。白紙から部品を描かせず、承認済みの絵の編集か、丸ごと描かせて切り分ける。プログラムで絵を描き足さない。
- リグ・書き出し・Unity・確認の道具は Claude が担当する。
- 合否は「自然でかわいいか」。画素一致や数値だけで良いと言わない。確認図・GIF をユーザーに見せ、判断を仰ぐ。

## 手順

作業ファイルはすべて `.local/<作業名>/` に置く（Git 外）。版ごとのフォルダを Git に作らない。

1. **組み込み（スクリプト）**：正式モデルを入力に、部品・パラメーター・ワープを足すスクリプトを `scripts/live2d/vNN/` に書く。
   - 最初の入力は `official.require_official_rig(src)` で確かめる。Cubism で保存し直した途中のモデルは `official.require_current_lineage(src)`。
   - .cmo3 の編集は `cmo3_tool.Cmo3`（文字列）と `cmo3_editor.Editor`（ElementTree：define・add_param・opacity_binding・replace_image・flush）。手本は `scripts/live2d/v64/`。
   - 複数のパラメーターのキーフォームは、**最初のパラメーターが一番速く変わる順**に並べる（Cubism の書き出しは並び順でキーを引く。逆にすると別のキーの形が出る）。
   - `forms.clear()` は属性も消すので `xs.n`・`count` を付け直す。
   - ワープの子の座標は割合（0〜1）、回転の子は回転の中の画素。親を変えるときはキーフォームを変換する。
2. **新しい絵の取り込み（Cubism）**：PSD を作り、ユーザーに Cubism で取り込んでもらうか、computer-use で操作する（java.exe の許可が要る）。取り込んだ層は「位置調整用デフォーマ」の下に入る。4頂点のメッシュは `crop_quad_mesh` で絵の範囲に切り詰めてから、スクリプトで親・座標・キーを付ける。
3. **Cubism で開いて確かめ、書き出す**：エラーはログ `%APPDATA%\Live2D\Cubism5.3_Editor\logs\log.txt` で見る。
   - 新しいメッシュは「テクスチャアトラスに配置されていない」と出る。既存のアトラスで自動レイアウトすると大きな部品が押し出されるので、**小さい新しいテクスチャを追加**して、そこへ「選択要素をテクスチャアトラスに配置」し、座標（X・Y）か自動レイアウトで並べる。
   - 保存は数分かかる。書き出しは「ファイル > 組み込み用ファイル書き出し > moc3 ファイル書き出し」。
4. **SDK をまとめる**：表情・モーション・物理演算を今の `assets/ciel/runtime` から写し、新しい物理演算のグループを足す（手本 `scripts/live2d/v64/package-runtime.py`）。物理演算の値は、Unity の `CubismPhysicsSubRig` と同じ式で試算して決める（手本 `v64/preview_physics.py`）。
5. **確認**：`scripts/live2d/render-moc.py`（Core で描く）で、新しい動きと、既存の姿勢（尻尾・上着の着脱・手・表情）を今の SDK と並べる。既存の部品の並びが同じで、関係ない姿勢の画素が変わらないこと（手本 `v64/adopt-cheek.py --check`）。動きは GIF にしてユーザーに見せる。
6. **採用**（ユーザーの了承のあと）：
   - 新しい素材 PNG を `assets/ciel/current/layers/` へ入れ、`layers.json` に足す。
   - 正式モデル `rig/ciel.cmo3` を置き換え、`approved.json`（rig_sha256・material_count・export_files・approved_date）を更新する。
   - 確認図と検証結果は `assets/ciel/rig/proofs/current/` を**置き換える**（版ごとのフォルダを足さない）。`all-expressions.png` も作り直す。
   - `python -I scripts/live2d/prepare-current-runtime.py <書き出し> [--use-source-physics]` で `assets/ciel/runtime` を作る（古いモデルからの書き出しなら止まる）。
7. **Unity へ反映**：ユーザーの Unity が閉じていれば `Unity.exe -batchmode -quit -projectPath unity -executeMethod Ciel.EditorTools.CielModelUpdate.ApplyCurrent`。開いていればメニュー `CIEL > Model > Apply Current Package` を頼む。同じプロジェクトで Unity を二つ開かない。
8. **記録とコミット**：`assets/ciel/README.md`・`current/README.md`・`rig/README.md`・`runtime/README.md` を今の状態だけの説明に直す。Codex の生成原本や候補は `.local/` に置き、Git に入れない。コミット・会話サーバーへの反映はユーザーに頼まれてから。

## Git には現行だけ

- Git に置くのは `assets/ciel/{current,rig,runtime,master,reference}` と `rig/proofs/current`、共通の道具（`scripts/live2d/` の cmo3_tool・cmo3_editor・cubism_core・render-moc・official・prepare-current-runtime など）と最新の版のスクリプトだけ。
- 古い版は Git の履歴（タグ `archive/pre-history-cleanup` など）とローカルの `.local/history/` にある。Git から外すときは、先にタグを付け、`.local/history/` へ写してから消す。
- ローカルのファイルは、ユーザーが頼まない限り消さない。
