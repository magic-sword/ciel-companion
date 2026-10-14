# 採用済み：わくわく v43

- [見本・調整前・候補](reference-comparison.png)
- [候補モデルの描画](excited.png)
- [目元と口の拡大](excited-face.png)
- [まばたき・発話](blink-and-mouth.png)
- [顔の向き](head-angles.png)
- [検証記録](verification.json)

87層の正式モデルへ採用済み。以前の10ポーズの全パーツの形と表示、左右別のまばたき、虹彩の目線追従と白目のクリッピング、旧キラキラの非表示、発話の口、81通りの組み合わせを検証した。[採用記録](adoption.json)。

編集対象は `../../ciel.cmo3`、素材は `../../../current/`、通常を含む10表情・SDK16ファイルの更新パッケージは `../../../runtime/`。旧候補は `.local/excited-adoption/adopted-draft/` へ退避。Unityのモデル本体にはまだ適用していない。
