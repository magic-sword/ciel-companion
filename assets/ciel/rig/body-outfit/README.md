# 採用済みの身体・上着 v60

編集するモデルは [ciel.cmo3](../ciel.cmo3)、素材は [current/layers.json](../../current/layers.json)。身体・衣服の座標はこの中央配置を固定基準とする。

`controls.json` に15パラメータの範囲・初期値、`hierarchy.json` に肩・肘・手首・服の親子関係を記録する。`ParamCielJacketVisible` は0=脱衣、1=着用。左右の `ParamCielHandPoseL/R` は0=自然手、1=開き手、2=握り手の整数で指定する。衣服の揺れキーはあるが物理出力の接続・調整は未実施。大きな肘曲げ・腕上げの補正は今後の作業。

現行モデルの確認図は [proofs/current](../proofs/current/)。
