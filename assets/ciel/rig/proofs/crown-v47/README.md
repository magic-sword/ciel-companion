# 頭頂部の左右補完 v47

承認済みの2素材を正式モデルへ組み込む記録。最新の確認画像はCubismから書き出したSDKの描画。

- [正式モデルの全表情](all-expressions.png)
- [正式モデルの頭頂部：修正前／修正後](native-crown-comparison.png)
- [正式モデルの頭の傾き：修正前／修正後](native-head-roll.png)
- [正式取り込みの検証](verification.json)
- [採用記録](adoption.json)

以下は承認時の素材プレビューとして保持する。

- [頭頂部の拡大比較](crown-detail-comparison.png)
- [困り顔：現状／補完案](troubled-comparison.png)
- [半泣き：現状／補完案](teary-comparison.png)
- [通常：現状／補完案](neutral-comparison.png)
- [考え中：現状／補完案](thinking-comparison.png)
- [頭の上下左右](head-angles.png)
- [頭の傾き](head-roll.png)
- [頭の傾き・修正前](head-roll-before.png)
- [分離した頭頂部素材](crown-part.png)
- [素材プレビューの確認範囲](material-preview-verification.json)

右側が補完案。耳に隠れていた左右の髪を補い、斜めの切り口を丸い輪郭へ修正した。頭を傾けたときに露出する後ろ髪本体の旧上端も整理し、頭頂部パーツと役割を分けた。顔・前髪・アホ毛・耳は現行モデルのものを使用する。後ろ髪本体のy=600以降は元の素材を維持する。

素材プレビューは旧SDKの頂点を利用し、拡張した部分を補間・外挿して配置したもの。正式版では既存`Hair_Crown`と`Hair_Back`を差し替え、頭頂部を561頂点へ再メッシュしてCubismでアトラス・SDKを再作成した。2素材は全表情で共用する。現行素材の入口は`../../../current/`、Unity更新用は`../../../runtime/`。Unity本体への適用は別途行う。補修方法は[v47の記録](../../../generated/v47/report.md)。
