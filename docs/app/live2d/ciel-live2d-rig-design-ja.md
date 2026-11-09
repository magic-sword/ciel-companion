# 現行Live2Dリグと更新手順

> 責務：現行リグの制御パラメーター、変形・物理・書き出し・採用操作。

この資料は正式モデルのパラメーター、変形・物理演算の分担、SDK書き出し・採用操作を説明する。外観と合格条件は[制作仕様](ciel-live2d-production-spec-ja.md)、ファイルの現状は[編集モデル](../../../assets/ciel/rig/README.md)と[配布パッケージ](../../../assets/ciel/runtime/README.md)が正本。

## 正式な開始点

`assets/ciel/current/approved.json`の`rig_sha256`と一致する`assets/ciel/rig/ciel.cmo3`から始める。現行モデルを旧試作から作り直さず、候補を`.local/`で編集する。照合には次を使う。

```sh
python -I scripts/live2d/official.py assets/ciel/rig/ciel.cmo3
```

素材・配置の基準は`current/layers.json`。モデルキャンバスと素材キャンバス、UV、オフセット、CMO内の拡大や反転を区別し、倍率・移動を二重に適用しない。PSDはmanifestから再生成する。身体や手を頭のキャンバスへ無理に縮小しない。

## アプリとの制御契約

| 対象 | 制御 |
|---|---|
| 向き・視線・瞬き・口 | 標準パラメーターを維持し、表情の固定値で動作を潰さない |
| 表情 | 通常を含む11表情。専用キーの解除、耳・頬の復帰を確認する。対応表はrig READMEとUnityの表情実装 |
| 上着 | `ParamCielJacketVisible` 0=脱衣、1=着用 |
| 左右の手 | `ParamCielHandPoseL/R` 0=自然手、1=開き手、2=握り手 |
| 尻尾 | `ParamCielTailWag` −1=画面左、0=体の後ろ、1=画面右。Follow/Tipは物理出力 |
| ほっぺ | `ParamCielCheekPoke/PullX/PullY/Jiggle{L,R}`。Lはモデルの左＝画面の右。Jiggleは物理出力 |

名前・範囲・物理入力と出力を変えるときはモデル、physics、Unityの制御を同時に変更する。アプリから物理出力を直接上書きしたり、表情・口パク・接触を互いに消したりしない。接触の通知と反応は[タッチ](../ciel-touch-interaction-ja.md)と[共通反応契約](../../conversation/service-events-and-reactions-ja.md)を参照。

## 変形と見た目の確認

向きと部位別の変形、物理演算、接触を親子の責務として分ける。部位別の視差を作り、前髪・目・鼻・口を一枚の大きなワープだけで動かして不自然さを補正し続けない。首と顔、服と手、髪と耳の境界は複合角度で確認する。

目は閉眼時に瞳・白目・ハイライトが漏れず、中間で線が二重にならないこと。口は閉じた状態で歯が浮かず、表情と口パクを同時に動かせること。必要な隠れ領域を素材へ描き足し、メッシュの伸長だけで埋めない。

長い髪や尻尾の物理出力は、向きの変形の下へ配置する。親子関係・描画順・クリッピング・物理グループは正式モデルと同梱physicsを照合する。参考モデルの数値をシエルの強制目標にしない。[参考解析](ciel-live2d-reference-rig-analysis-ja.md)を参照する。

## 書き出しと採用

候補からSDK一式を書き出し、manifestへモデル・素材・SDK全ファイルのSHA-256を記録する。採用時にcurrent/rig/runtimeと現行確認図を一式で更新する。正式なSDK一覧・アトラスと表情数はruntime manifestを正本とする。

Unityでは`CIEL > Model > Validate Current Package`で検証し、`CIEL > Model > Apply Current Package`で更新する。既存.metaとシーン参照を引き継ぎ、退避先は`.local/unity-model-update/`。手順の細部は[更新スキル](../../../.claude/skills/ciel-live2d-update/SKILL.md)に従う。

```sh
python -I scripts/live2d/render-moc.py <model3.json> <出力.png> --scale 0.5 "ParamAngleX=30;ParamAngleY=30"
```

Coreでの静止画とUnity描画にはクリッピング境界等の差があり得る。端点・表情の画像確認、アプリでの会話・停止、実機負荷を別々に記録する。[検証方法](../../testing/regression-tests-ja.md)と[確認状況](../../testing/verification-status-ja.md)を参照する。
