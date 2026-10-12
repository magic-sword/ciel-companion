# シエル Live2D：現在の素材（シングルソース）

**最新の素材はこのフォルダだけ。** ほかの場所に古い版は置かない（過去の版は Git のタグ `archive/pre-current-cleanup` で参照できる）。

| 場所 | 内容 |
| --- | --- |
| `layers/*.png` | リグに使う 51 層（キャンバス 2172×2896 の透明 PNG。レイヤー名＝ファイル名） |
| `layers.json` | 下から上の重なり順と、通常の表示（`visible: false` は差分：閉じ目・開いた口）。PSD 作成の一覧を兼ねる |
| `proofs/` | 現在のモデルの確認画像：向き 3×3（`angles-3x3.png`）、目と口（`eyes-mouth.png`）、上下と体の傾き（`angle-y.png`）、頷き（`nod.gif`）、横向きの頬（`cheek-compare.png`・`cheek-sweep.gif`）、待機（`idle.gif`）、揺れの形（`sway-shapes.gif`・`bust-sway.gif`）、Unity の描画（`unity-check.png`） |
| `../rig/ciel.cmo3` | 現在の作業モデル（Cubism Editor 5.3、Git LFS） |
| `../master/ciel-upper-body-2x.png` | 承認済みの元の絵（見た目の基準） |
| `../reference/` | 外観の参考、口の参考、頭の向きの参考（`pose/`）、元の絵の生成元（`source/`） |

PSD の作り方：`CIEL_PSD_MANIFEST=assets/ciel/current/layers.json` で `scripts/live2d/gimp/build_layers_psd.py` を GIMP から実行（出力 `assets/ciel/psd/ciel-current.psd`、Git 管理外）。
素材を差し替えたら、このフォルダの層と `layers.json` を更新し、古い版は残さない。
