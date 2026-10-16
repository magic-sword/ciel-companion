# シエルの現行素材・正式モデル

2026-10-16、身体・上着v60にサモエドの尻尾v63を追加し、現行は113層。通常は体の後ろに隠れ、左右に振ると見える。中央で左右の表示を切り替え、中ほど・毛先の遅れは共通の物理演算で扱う。既存の頭部・身体・11表情を維持する。

- [現行素材一覧](layers.json) と `layers/*.png` が採用素材の単一の参照先。
- [正式Cubismモデル](../rig/ciel.cmo3)、[制御と階層](../rig/body-outfit/README.md)。
- [着用比較・検証](../rig/proofs/body-outfit-v60/README.md)、[Unity更新用SDK](../runtime/README.md)。
- [生成原本と最終22素材](../generated/v60/report.md)、[制作方針](../../../docs/ciel-live2d-body-outfit-design-ja.md)。
- 尻尾の[左右・中央の確認図](../rig/proofs/tail-v63/sdk-poses.png)、[動きの確認図](../rig/proofs/tail-v63/sdk-wag.gif)、[SDK検証結果](../rig/proofs/tail-v63/runtime-verification.json)、[制御](../rig/tail/controls.json)。GIFはパラメーターを動かした見本で、物理演算そのものの録画ではない。
- [採用中の会話画面](../rig/proofs/tail-v63/unity-neutral.png) と [再生検証結果](../rig/proofs/tail-v63/unity-play-verification.json)。画角は尻尾追加前の顔中心のサイズ・位置（orthographic size=0.7003115）。下半身の切れ目を画面へ出さず、尻尾を表示するための画角変更は行わない。通常・停止後の非表示と、追従出力が上限に張り付かないことも確認する。

| 用途 | 採用中の参照先 |
| --- | --- |
| 編集・PSD用の素材113層 | `layers.json` と `layers/`（頭部89・身体と上着22・尻尾2） |
| 尻尾の採用生成原本・由来 | [生成原本](../generated/tail/source.png) と [採用記録](../generated/tail/provenance.json) |
| 編集用モデル | `../rig/ciel.cmo3` |
| 尻尾の制御・物理設定 | `../rig/tail/` |
| 配布用SDK | `../runtime/`（`manifest.json` で照合） |
| Unityで使用するモデル | `unity/Assets/Characters/Ciel/`（リポジトリのルートから） |

尻尾の旧案v61、不採用の下げ尾、v62の比較用素材、v63の重複素材・作業モデルは削除した。制作スクリプトの中間出力はGit対象外の `.local/tail-integration/` へ置く。公式参考モデル本体も `.local/reference-rigs/` にのみ保持する。

素材キャンバスは3000×3800、モデル原点は(414,0)、モデルキャンバスは2172×2896。頭部89素材は元のPNGを保持し、一覧の `canvas` / `offset` で配置する。腕や手をモデルキャンバス内へ縮小しない。CMOのUVと原寸PNGのワールド座標の差に注意し、身体や関節の倍率・移動を二重適用しない。

全素材のPSD/XCFは `CIEL_PSD_MANIFEST=assets/ciel/current/layers.json` として `scripts/live2d/gimp/build_layers_psd.py` で再作成できる（出力はGit対象外）。尻尾2層は1254×1254の素材座標のPNGを保持し、配置・拡大・左向きへの反転はCMO内で行う（`placement: native-rig`）。PSDの初期表示では非表示にする。PNGをそのまま胴体の絵へ重ねない。

再検証: `python -B scripts/live2d/v63/adopt-tail.py`。過去のモデルはGit履歴、尻尾追加前の退避は `.local/tail-adoption/before/` に保持する。

尻尾のパラメーターはすべて範囲−1〜1、初期値0。`ParamCielTailWag` は画面左=−1・非表示=0・画面右=1。`ParamCielTailFollow` と `ParamCielTailTip` は物理演算の出力先で、意図した左右の動きとは分ける。Unityでは `CielTail` が「嬉しい」「わくわく」に合わせて振る。任意のタイミングでは `Wag(strength, seconds, cyclesPerSecond)` を呼べる。再生中のコンポーネントメニュー `Wag tail (Play mode)` でも確認できる。

頭部・表情v47までの採用履歴はGit履歴と各版の検証フォルダを参照。Unityモデルへの反映も完了し、既存の.meta・髪の物理・うなずき設定を維持した。
