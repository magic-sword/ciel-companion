# ぷんすかの確認用モデル

`angry.cmo3` が今回のCubism候補。`runtime/` は同じモデルからのSDK書き出し。`layers.json` は素材71層の入口で、正式素材67層と v35 の追加4層を参照する。

Gitに保存するのは、この最新の候補一式と素材の原本・比較・検証記録。旧候補・取り込み途中のモデル・PSD・XCFは `.local/angry-integration/` に残す。保存時点のモデルのハッシュは `status.json`、書き出し各ファイルのハッシュは `runtime/manifest.json` で確認できる。

Cubismで `ぷんすか` (`ParamAngry`) と `折れ耳` (`ParamEarFold`) をともに1にすると候補の顔になる。`耳 感情` (`ParamEar`) は0、`頬` (`ParamCheek`) は0.2を基準にする。両方0で従来の顔・耳へ戻る。折れ耳だけを独立して使える。

通常の目・まばたき・目線をそのまま利用する。口は発話時に既存の開口パーツへ切り替わる。折れ耳は既存の耳デフォーマーに所属し、顔の向きに追従する。切り替え途中は立ち耳と折れ耳を透過でつなぐ。

眉は形を保って上へ32px移動し、瞼の線との間隔を調整済み。[眉位置の変更前後](../../proofs/angry-v35/brow-position-comparison.png)で確認できる。素材画像は同じで、Cubismのメッシュ位置だけを補正した。

比較は [見本・調整前・候補](../../proofs/angry-v35/reference-comparison.png)、[まばたき・発話](../../proofs/angry-v35/blink-and-mouth.png)、[顔の向き](../../proofs/angry-v35/head-angles.png)。検証結果は [verification.json](../../proofs/angry-v35/verification.json)。

正式採用前の候補のため、`assets/ciel/rig/ciel.cmo3`、`assets/ciel/current/`、正式な `assets/ciel/runtime/` は今回の候補へ更新していない。Unityの更新メニューが参照する正式パッケージとは別に保存する。
