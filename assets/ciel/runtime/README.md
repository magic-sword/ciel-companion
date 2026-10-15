# シエルの確定版SDKパッケージ

2026-10-15に身体・上着v60を採用し、Unityモデルへ反映済み。現行111素材、SDK18ファイル、通常を含む11表情、4096pxアトラス2枚。正式編集モデルは `../rig/ciel.cmo3`、現行素材は `../current/layers.json`。

身体を首輪の中央へ合わせ、上着の内側と表側で明るさを分担した。着脱と手3種の切り替えを確認し、既存の頭部・表情・髪の物理・うなずきを維持した。[採用・検証](../rig/proofs/body-outfit-v60/README.md)。

`manifest.json` に正式モデル・全素材・SDK全ファイルのSHA-256を記録する。Unityの `Assets/Characters/Ciel/runtime-manifest.json` と一致する。`CIEL > Model > Validate Current Package` で検証し、次回更新時は `CIEL > Model > Apply Current Package` を使う。既存の.metaとシーン参照を引き継ぎ、更新前は `.local/unity-model-update/` に退避する。

着脱は `ParamCielJacketVisible` の0/1、左右の手は `ParamCielHandPoseL/R` の0=自然手・1=開き手・2=握り手。既存11表情は `Expressions/`。新しい衣服の物理出力接続と大きな肘曲げ・腕上げの補正は今後の作業。

再検証: `python -B scripts/live2d/adopt-body-outfit.py`。
再書き出し時はCubismで正式モデルを保存し、SDKを検証・採用してから `prepare-current-runtime.py <書き出しフォルダ>` を使う。モデルや素材のハッシュが異なる場合は更新を止める。
