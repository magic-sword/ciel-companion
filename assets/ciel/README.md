# シエルの素材とモデル

Git には**今使っている素材とモデルだけ**を置く。2026-10-17 時点で115層（頭部・11表情、身体と上着v60、尻尾v63、ほっぺv64）。

| 用途 | 正式な場所 |
| --- | --- |
| 現行の素材115層 | [current/layers.json](current/layers.json)・`current/layers/`（説明は [current/README.md](current/README.md)） |
| 採用状態・正式モデルのハッシュ | [current/approved.json](current/approved.json) |
| Cubism編集（正式モデル） | [rig/ciel.cmo3](rig/ciel.cmo3)（説明は [rig/README.md](rig/README.md)） |
| 現行モデルの確認図・検証 | [rig/proofs/current/](rig/proofs/current/) |
| Unity更新用の書き出し一式 | [runtime/README.md](runtime/README.md) |
| 承認済みの元の絵 | `master/ciel-upper-body-2x.png` |
| 表情・姿勢の見本（ユーザー提供） | `reference/` |

新しい部品や表情を作るときは、必ず `rig/ciel.cmo3`（`approved.json` の `rig_sha256` と一致するもの）から始め（`python -I scripts/live2d/official.py <モデル>` で確かめられる。手順はスキル `.claude/skills/ciel-live2d-update/`）、採用したら `current/`・`rig/`・`runtime/`・`rig/proofs/current/` を置き換える。版ごとのフォルダは Git に増やさない。

過去の版（生成原本 `generated/vNN`、版ごとの確認図、候補モデル、版ごとの作業スクリプト）は Git に残さない。必要なら Git の履歴（タグ `archive/pre-history-cleanup` 以前）か、ローカルの `.local/history/` を見る。作業中のモデル・PSD・書き出しは `.local/` に置く。
PSD・XCFは`current/layers.json`から再構築でき、`psd/`に置く（Git管理外）。
