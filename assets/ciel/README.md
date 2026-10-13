# シエルの素材とモデル

2026-10-13：**にこにこは目尻調整後を確定版として採用**。嬉しいも採用済み。他の表情は今後調整する。

| 用途 | 正式な場所 |
| --- | --- |
| 最新の素材66層 | [current/layers.json](current/layers.json)・`current/layers/` |
| 採用状態・正式モデルのハッシュ | [current/approved.json](current/approved.json) |
| Cubism編集 | [rig/ciel.cmo3](rig/ciel.cmo3) |
| 最新のにこにこ比較 | [見本との比較](rig/proofs/relaxed-eye-corners/reference-comparison.png) |
| Unity更新用の書き出し一式 | [runtime/README.md](runtime/README.md) |
| 生成原本・旧候補の記録 | [generated/README.md](generated/README.md) |
| 承認済みの元の絵 | `master/ciel-upper-body-2x.png` |

現行素材には旧候補を混在させない。共通の目・口・頬などは、通常や他の表情で使うため保持している。
`generated/`や過去の`rig/proofs/`は経緯の記録。そこから直接Unityへ入れず、`runtime/`の一式を使う。
PSD・XCFは`current/layers.json`から再構築でき、`psd/`に置く（Git管理外）。
