# シエル Live2D：現在の素材（シングルソース）

**現行モデルに使う素材はこのフォルダだけ。** 同じ役割の旧版を混在させない。`generated/`の候補・比較図は検証履歴であり、現行素材ではない。さらに過去の版は Git のタグ `archive/pre-current-cleanup` で参照できる。

| 場所 | 内容 |
| --- | --- |
| `layers/*.png` | リグに使う 62 層（キャンバス 2172×2896 の透明 PNG。レイヤー名＝ファイル名）。v23・v24に加え、v31の採用済み笑い目・専用口・頬・鼻を反映 |
| `layers.json` | 下から上の重なり順と、通常の表示（`visible: false` は差分：閉じ目・開いた口・表情素材）。PSD 作成の一覧を兼ねる |
| `proofs/` | 現在のモデルの確認画像：向き 3×3（`angles-3x3.png`）、目と口（`eyes-mouth.png`）、上下と体の傾き（`angle-y.png`）、頷き（`nod.gif`）、横向きの頬（`cheek-compare.png`・`cheek-sweep.gif`）、待機（`idle.gif`）、揺れの形（`sway-shapes.gif`・`bust-sway.gif`）、Unity の描画（`unity-check.png`） |
| `../rig/ciel.cmo3` | 現在の作業モデル（Cubism Editor 5.3、Git LFS） |
| `../master/ciel-upper-body-2x.png` | 承認済みの元の絵（見た目の基準） |
| `../reference/` | 外観の参考、口の参考、頭の向きの参考（`pose/`）、元の絵の生成元（`source/`） |

PSD の作り方：`CIEL_PSD_MANIFEST=assets/ciel/current/layers.json` で `scripts/live2d/gimp/build_layers_psd.py` を GIMP から実行（出力 `assets/ciel/psd/ciel-current.psd`、Git 管理外）。
素材を差し替えたら、このフォルダの層と `layers.json` を更新し、古い版は残さない。

2026-10-13：表情素材を Cubism と Unity に組み込んだ。12表情の Core 描画と見本の比較は
`../rig/proofs/expressions/`。取り込み手順と残る見た目の差は
[表情の取り込み記録](../../../docs/ciel-expression-integration-ja.md) を参照。

同日、承認されたv31のニッコリ顔をCubismへ反映した。笑い目は旧ファイルを同じ名前で置き換え、
`Mouth_Happy`・`Cheek_Happy`・`Nose_Happy`を追加。共通素材は他の表情用に保持し、
嬉しい表情中には専用素材と重ならないよう隠す。
`ParamEyeLSmile=1`・`ParamEyeRSmile=1`・`ParamHappy=1`で表示する。
今回の変更はUnityにはまだ反映していない。
