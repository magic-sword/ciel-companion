# 正式なCubismモデル

頭頂部と後ろ髪の共通修正v47が最新。正式モデル92層で既存2素材を差し替え、補完範囲まで頭頂部を再メッシュした。[最新の全表情](proofs/crown-v47/all-expressions.png)、[頭の傾きの比較](proofs/crown-v47/native-head-roll.png)。肌色v46と採用済み表情の設定を含む。

肌色の共通修正v46も反映済み。顔土台・まぶた・口元の7素材を差し替え、既存の表情と動作を維持した。[肌色採用時の全表情](proofs/skin-v46/all-expressions.png)。

ジト目v44と頭頂部の共通修正v45を正式採用。[全表情の描画](proofs/crown-v45/all-expressions.png)。`Hair_Crown`は全表情で使い、頭に追従する前髪側のデフォーマに接続した。ジト目は`ParamJitome=1`・`ParamEar=-0.35`・`ParamCheek=0.15`で表示する。

わくわくv43を正式採用。[最新比較](proofs/excited-v43/reference-comparison.png)。`ParamExcited=1`・`ParamEar=1`で表示し、旧キラキラ・口・赤みの値は重ねない。旧候補は `.local/excited-adoption/adopted-draft/` へ退避した。

半泣きv40とサモエド折れ耳v42を正式採用。[半泣きの実モデル比較](proofs/teary-v42/reference-comparison.png)。`ParamTeary=1`・`ParamEarFold=1`で切り替える。折れ耳はぷんすか・しょんぼり・困り・照れ・半泣きで共用。旧候補は `.local/teary-adoption/adopted-draft/` へ退避した。

現在の編集対象は **ciel.cmo3**、素材は92層。嬉しい・にこにこ・驚き・ぷんすか・しょんぼり・困り・照れ・半泣き・わくわく・ジト目を採用済み。
しょんぼりは `ParamSad=1`、ぷんすかは `ParamAngry=1`。どちらも `ParamEarFold=1`、`ParamEar=0` を基本とし、他の専用キーは0に戻す。まばたき・目線・口パクは固定しない。

最新の困りは[下まぶた調整後の比較](proofs/troubled-v37-lower-lid/reference-comparison.png)。`ParamTroubled=1`・`ParamEarFold=1`で表示し、他の専用表情キーは0へ戻す。採用状態は [approved.json](../current/approved.json)、Unityへの更新は [runtime/README.md](../runtime/README.md)。expressions/に通常を含む11表情の切り替えファイルを保存した。

旧候補モデル・書き出しは `.local/sad-adoption/adopted-drafts/` に退避し、正式モデルと重複させない。その他の表情は引き続き調整予定。

困り顔（v37、下まぶた調整済み）は正式採用済み。候補一式は `.local/troubled-adoption/adopted-draft/` へ退避。[全表情の下まぶたの見直し](proofs/lower-lid-review/README.md)は確認履歴として保持する。

照れ（v39、目尻・赤みの最終調整）は正式採用済み。`ParamEmbarrassed=1`・`ParamEarFold=1`で表示し、旧赤み・旧目線を重ねない。[最新比較](proofs/embarrassed-v39/reference-comparison.png)。候補一式は `.local/embarrassed-adoption/adopted-draft/` へ退避。

半泣き（v40）の眉・口・左右の涙と、折れ耳v42は正式モデルへ反映済み。[採用記録](proofs/teary-v42/adoption.json)を参照。通常を含む10表情の切り替えファイルを用意した。

## 過去の記録

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

次の調整中の表情はぷんすか（v35）。正式モデルとは別に [drafts/angry/](drafts/angry/README.md) へ候補を保存した。顔と折れ耳を独立したキーで切り替える。見本との比較は [proofs/angry-v35/](proofs/angry-v35/reference-comparison.png)。

しょんぼり（v36）の候補は [drafts/sad/](drafts/sad/README.md)。v35のぷんすかを含むモデルに、しょんぼり用の眉・口・伏せ目のキーを追加した。折れ耳を共用し、正式モデルとは別に保存する。[比較画像](proofs/sad-v36/reference-comparison.png)で確認できる。
