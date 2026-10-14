# 耳に隠れていた頭頂部の補完 v47

現行v45の`Hair_Crown`は、立ち耳で見えている範囲を抽出したため、左右の上端が斜めに切れていた。折れ耳では切り口と元の耳の境界線が露出して、頭頂部が欠けたように見えた。

今回は画像生成を使わず、既存の頭頂部から髪の色・薄い陰影をクローンし、左右の隠れていた範囲を補完した。輪郭を丸くつなぎ、元画像に残っていた耳の斜めの境界線を除いた。中央の毛流れはフェザー付きで保つ。前髪・アホ毛・耳・顔の素材は変更しない。

頭を大きく傾けると、後ろ髪本体`Hair_Back`の旧上端も前髪の上に露出していた。パーツを個別に非表示にして原因を特定した。専用の頭頂部に上部を任せ、後ろ髪本体はy=500まで上端を透明にし、y=500〜600でなじませた。y=600以降のRGB・透明度・下側の髪の動きは維持する。

承認素材は`layers/Hair_Crown.png`と`layers/Hair_Back.png`。現行素材では同名の2層を差し替え、旧版は混在させない。原本のハッシュ・補修範囲・輪郭点は`generation-provenance.json`。[承認時の頭頂部比較](../../rig/proofs/crown-v47/crown-detail-comparison.png)。

承認時のプレビューは旧SDKの頂点を基準に補間・外挿したもの。正式版は既存の頭頂部メッシュを561頂点へ広げ、CubismでアトラスとSDKを作り直した。確認結果は[正式モデルの検証](../../rig/proofs/crown-v47/verification.json)、見た目は[全表情](../../rig/proofs/crown-v47/all-expressions.png)と[頭の傾き](../../rig/proofs/crown-v47/native-head-roll.png)。この共通修正は通常と全表情で使われる。Unity本体への適用は未実施。

再現用スクリプト：`scripts/live2d/prepare-crown-completion.py`。承認済み原本への上書きを防止する。採用前素材とSDKのローカル保管先を指定し、別の出力先で再確認できる。

```powershell
python scripts/live2d/prepare-crown-completion.py --source-layers .local/crown-completion-adoption/current-before/layers --source-runtime .local/crown-completion-adoption/runtime-before --output .local/crown-completion-reproduction/materials --proof-output .local/crown-completion-reproduction/proofs
```

正式モデルの処理は`integrate-crown-completion.py`、SDK検証は`check-crown-completion.py`、採用処理は`adopt-crown-completion.py`。Gitには承認素材・比較・検証結果と正式モデル／SDKを残し、旧素材と作業コピーは`.local/crown-completion-adoption/`へ整理する。
