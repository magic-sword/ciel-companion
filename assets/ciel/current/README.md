# シエル Live2D：現在の素材（シングルソース）

**現行モデルに使う素材はこのフォルダだけ。** 同じ役割の旧版を混在させない。`generated/`の候補・比較図は検証履歴であり、現行素材ではない。さらに過去の版は Git のタグ `archive/pre-current-cleanup` で参照できる。

**2026-10-14：嬉しい・にこにこ・驚き・ぷんすか・しょんぼり・困りは採用済み。** 困りはv37の下まぶた調整後を反映。他の表情は調整予定。
採用状態は[approved.json](approved.json)、最新の見た目は[にこにこの比較](../rig/proofs/relaxed-eye-corners/reference-comparison.png)。
正式なCubismモデルへ反映済み。[Unity更新用パッケージ](../runtime/README.md)を用意した。
Unityのモデル自体はまだ更新していない。素材一覧とPNG76枚に過不足・名前の重複はない。
困りの最新比較は[こちら](../rig/proofs/troubled-v37-lower-lid/reference-comparison.png)。`ParamTroubled=1`・`ParamEarFold=1`で切り替える。
驚きの最新比較は[こちら](../rig/proofs/surprised-v34/reference-comparison.png)。`ParamSurprised=1`で目と丸口を切り替える。

| 場所 | 内容 |
| --- | --- |
| `layers/*.png` | リグに使う76層（キャンバス2172×2896の透明PNG）。採用済み6表情を含み、v37の困り眉・口・汗を追加 |
| `layers.json` | 下から上の重なり順と、通常の表示（`visible: false` は差分：閉じ目・開いた口・表情素材）。PSD 作成の一覧を兼ねる |
| `proofs/` | 現在のモデルの確認画像：向き 3×3（`angles-3x3.png`）、目と口（`eyes-mouth.png`）、上下と体の傾き（`angle-y.png`）、頷き（`nod.gif`）、横向きの頬（`cheek-compare.png`・`cheek-sweep.gif`）、待機（`idle.gif`）、揺れの形（`sway-shapes.gif`・`bust-sway.gif`）、Unity の描画（`unity-check.png`） |
| `../rig/ciel.cmo3` | 現在の作業モデル（Cubism Editor 5.3、Git LFS） |
| `../master/ciel-upper-body-2x.png` | 承認済みの元の絵（見た目の基準） |
| `../reference/` | 外観の参考、口の参考、頭の向きの参考（`pose/`）、元の絵の生成元（`source/`） |

PSD の作り方：`CIEL_PSD_MANIFEST=assets/ciel/current/layers.json` で `scripts/live2d/gimp/build_layers_psd.py` を GIMP から実行（出力 `assets/ciel/psd/ciel-current.psd`、Git 管理外）。
素材を差し替えたら、このフォルダの層と `layers.json` を更新し、古い版は残さない。

## 採用までの履歴

以下は各段階の記録。現在の採用版は上記の`approved.json`と最新比較を参照。

2026-10-13：表情素材を Cubism と Unity に組み込んだ。12表情の Core 描画と見本の比較は
`../rig/proofs/expressions/`。取り込み手順と残る見た目の差は
[表情の取り込み記録](../../../docs/ciel-expression-integration-ja.md) を参照。

同日、承認されたv31のニッコリ顔をCubismへ反映した。笑い目は旧ファイルを同じ名前で置き換え、
`Mouth_Happy`・`Cheek_Happy`・`Nose_Happy`を追加。共通素材は他の表情用に保持し、
嬉しい表情中には専用素材と重ならないよう隠す。
`ParamEyeLSmile=1`・`ParamEyeRSmile=1`・`ParamHappy=1`で表示する。
今回の変更はUnityにはまだ反映していない。

続けてv32のにこにこをCubismへ反映。`ParamRelaxed=1`で専用の口・頬とまぶたの形をまとめて変更。
まばたき・目線・開口素材を維持し、0では以前の通常・嬉しいの形へ戻る。
切り替え用の3つの表情ファイルは`../rig/expressions/`。Unityへの反映は未実施。

にこにこの下まぶた中央を追加で持ち上げ、白目・肌・下まつ毛の6メッシュを調整した。
画像素材64層はそのまま。比較と動作検証は`../rig/proofs/relaxed-lower-lid/`。

続けてv33で、にこにこ中の下まぶた肌が作る白い帯を除去。
v32から分離した左右の線を、白目の実際の下端へ合わせた。共通の肌・下まつ毛は他の表情用に保持。
通常・嬉しい・完全閉眼と瞳の形・位置を維持。現行66層の比較は`../rig/proofs/relaxed-boundary-v33/`。
Unityは未更新。

にこにこの目尻も、上まつ毛の外側だけを変形して下向きの部分を短くした。
素材の変更はなく、現行66層のまま。比較・検証は`../rig/proofs/relaxed-eye-corners/`。
正式なCubismモデルへ反映済み。Unityは未更新。

2026-10-14：v35のぷんすか・折れ耳、v36のしょんぼり（見本の上瞼へ合わせた最終版）を採用。正式モデルは73層。しょんぼりはParamSad、ぷんすかはParamAngry、耳はParamEarFoldで切り替える。旧候補は `.local/sad-adoption/adopted-drafts/` に退避した。
