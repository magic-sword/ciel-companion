# 正式なCubismモデル

現在の編集対象は **ciel.cmo3**、素材は79層。嬉しい・にこにこ・驚き・ぷんすか・しょんぼり・困り・照れを採用済み。
しょんぼりは `ParamSad=1`、ぷんすかは `ParamAngry=1`。どちらも `ParamEarFold=1`、`ParamEar=0` を基本とし、他の専用キーは0に戻す。まばたき・目線・口パクは固定しない。

最新の困りは[下まぶた調整後の比較](proofs/troubled-v37-lower-lid/reference-comparison.png)。`ParamTroubled=1`・`ParamEarFold=1`で表示し、他の専用表情キーは0へ戻す。採用状態は [approved.json](../current/approved.json)、Unityへの更新は [runtime/README.md](../runtime/README.md)。expressions/に通常を含む8表情の切り替えファイルを保存した。

旧候補モデル・書き出しは `.local/sad-adoption/adopted-drafts/` に退避し、正式モデルと重複させない。その他の表情は引き続き調整予定。

困り顔（v37、下まぶた調整済み）は正式採用済み。候補一式は `.local/troubled-adoption/adopted-draft/` へ退避。[全表情の下まぶたの見直し](proofs/lower-lid-review/README.md)は確認履歴として保持する。

照れ（v39、目尻・赤みの最終調整）は正式採用済み。`ParamEmbarrassed=1`・`ParamEarFold=1`で表示し、旧赤み・旧目線を重ねない。[最新比較](proofs/embarrassed-v39/reference-comparison.png)。候補一式は `.local/embarrassed-adoption/adopted-draft/` へ退避。

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
