# シエルの現行素材・正式モデル

2026-10-15、身体・上着v60を採用。旧Body/Jacket_Front/Jacket_Backを22素材へ置き換え、現行は111層。胴体を首輪の中央へ合わせ、上着の奥側を暗い内布、手前側を外光を受ける面へ修正した。既存の頭部・11表情を維持する。

- [現行素材一覧](layers.json) と `layers/*.png` が採用素材の単一の参照先。
- [正式Cubismモデル](../rig/ciel.cmo3)、[制御と階層](../rig/body-outfit/README.md)。
- [着用比較・検証](../rig/proofs/body-outfit-v60/README.md)、[Unity更新用SDK](../runtime/README.md)。
- [生成原本と最終22素材](../generated/v60/report.md)、[制作方針](../../../docs/ciel-live2d-body-outfit-design-ja.md)。

素材キャンバスは3000×3800、モデル原点は(414,0)、モデルキャンバスは2172×2896。頭部89素材は元のPNGを保持し、一覧の `canvas` / `offset` で配置する。腕や手をモデルキャンバス内へ縮小しない。CMOのUVと原寸PNGのワールド座標の差に注意し、身体や関節の倍率・移動を二重適用しない。

全素材のPSD/XCFは `CIEL_PSD_MANIFEST=assets/ciel/current/layers.json` として `scripts/live2d/gimp/build_layers_psd.py` で再作成できる（出力はGit対象外）。

再検証: `python -B scripts/live2d/adopt-body-outfit.py`。過去のモデルはGit履歴、作業途中の試作は `.local/body-outfit-history/` に保持する。

頭部・表情v47までの採用履歴はGit履歴と各版の検証フォルダを参照。Unityモデルへの反映も完了し、既存の.meta・髪の物理・うなずき設定を維持した。
