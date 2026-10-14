# 肌色の共通修正 v46（採用済み）

肌色v46は正式モデルへ採用済み。最新のモデル描画は[全表情](all-expressions.png)と[通常の拡大](native-neutral.png)。[採用記録](adoption.json)・[SDK検証](verification.json)。

以下は採用前の素材プレビュー。

- [マスター・現状・調整案](master-comparison.png)
- [通常の拡大比較](neutral-comparison.png)
- [顔とお腹の比較](face-and-body-comparison.png)
- [嬉しい](happy-comparison.png)
- [照れ](embarrassed-comparison.png)
- [半泣き](teary-comparison.png)
- [プレビューの確認範囲](material-preview-verification.json)

各比較の右側が調整案。顔の黄み・赤みを減らし、お腹に近い白い肌へ合わせた。まぶたと口元の肌色も同じ補正を使い、顔土台との境目を防ぐ。頬の赤み・輪郭・首・お腹は元の素材を使う。

正式モデルの7素材を差し替え、アトラスを再構築した。全12表情と81組み合わせの動作について、既存の頂点・三角形・不透明度・描画順が維持されることを確認した。測定記録は [v46](../../../generated/v46/report.md)。現行素材は`../../../current/`、Unity更新用パッケージは`../../../runtime/`。Unity本体への適用はまだ行っていない。
