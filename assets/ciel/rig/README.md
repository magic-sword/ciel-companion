# 正式なCubismモデル

編集対象は**`ciel.cmo3`のみ**。2026-10-14に、嬉しい・にこにこに加えてv34の驚きを反映した。
にこにこは`ParamRelaxed=1`、嬉しいは`ParamHappy=1`と左右の`ParamEye*Smile=1`。
驚きは`ParamSurprised=1`。切り替えには`expressions/`の4ファイルが使える。
通常・嬉しい・にこにこでは驚きのキーも0へ戻す。目線・まばたき・口パクを固定しない。

採用状態は[../current/approved.json](../current/approved.json)。
最新のにこにこ確認画像は[proofs/relaxed-eye-corners/](proofs/relaxed-eye-corners/)。
`relaxed-v32`・`relaxed-lower-lid`・`relaxed-boundary-v33`は途中段階の検証記録。
`happy-v31`は採用済みの嬉しいの記録。`expressions`の12表情一覧は初期取り込み時の記録で、最新の見た目ではない。

Unityへ更新するときは[../runtime/README.md](../runtime/README.md)に従う。

採用した驚きは[比較画像](proofs/surprised-v34/reference-comparison.png)で確認できる。
採用前の試作一式は`.local/surprised-adoption/adopted-draft/`へ退避し、編集対象の重複をなくした。
