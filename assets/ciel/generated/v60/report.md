# 身体の中央配置と内外の陰影 v60

身体の基準を首輪へ合わせ、衣服の奥側と手前側の明暗を分担し直した。

- [暗い内側の生成原本](inputs/interior-generated.png)
- [明るい表側の生成原本](inputs/exterior-generated.png)
- [生成と登録の記録](generation-provenance.json)
- 編集用PSD/XCFは `layers.json` からGIMPで再作成する（Git対象外、`assets/ciel/psd/ciel-body-outfit-v60.*`）。
- [着用比較と検証](../../rig/proofs/body-outfit-v60/README.md)

奥側には、衣服内の遮蔽を受けた暗い青緑の布を生成した。表側には、長い内側の暗い帯を持たない、柔らかい外光を受ける青い面を生成した。生成RGBを既存の青い領域へ登録し、輪郭、アルファ、白い布、金具、ファーを保つ。余白の発光や別の素材を含む画素は登録から除外する。

胴体PNGは右へ28.5px移動して首輪の軸へ合わせた。CMOでは元の胴体画像・UVを保持し、描画配置へ同じ移動を適用するため、原寸PNGの移動と二重に適用しない。変更素材は胴体、背面、左右の上袖の4枚で、残る18素材はv59と同一。
