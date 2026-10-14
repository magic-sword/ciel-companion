# 頭頂部の素材修正案 v45

マスターから毛流れと陰影を取り出して、頭頂部の専用素材を補修し、ジト目v44と合わせて正式モデルへ採用した。

- [全11表情の実モデル描画](all-expressions.png)
- [ジト目の見本と実モデル](reference-comparison.png)
- [まばたき・発話](blink-and-mouth.png)
- [頭の向き・髪の揺れ](crown-head-and-hair.png)
- [SDKの検証記録](verification.json)
- [採用記録](adoption.json)

以下は採用前に確認した静止画の素材プレビュー。最終モデルの描画は上のリンクを使う。

- [マスター・現状・素材修正案の拡大比較](master-crown-comparison.png)
- [通常：現状／素材修正案](neutral-comparison.png)
- [ジト目：現状／素材修正案](jitome-comparison.png)
- [わくわく：現状／素材修正案](excited-comparison.png)
- [半泣き：現状／素材修正案](teary-comparison.png)
- [分離素材](crown-part.png)
- [素材プレビューの確認範囲](material-preview-verification.json)

頭頂部は共通パーツ`Hair_Crown`として頭に追従する前髪側のデフォーマへ接続した。下側の後ろ髪が揺れても頭頂部の付け根は固定する。正式モデルは92層。既存の11姿勢の頂点・不透明度を保ち、全11表情で共通素材が表示されることを検証した。

素材と補修記録は [v45](../../../generated/v45/report.md)。現行素材は`../../../current/`、正式CMOは`../../ciel.cmo3`、Unity更新用SDKは`../../../runtime/`。Unity本体への適用はまだ行っていない。旧候補モデル・PSDは`.local/crown-adoption/`に退避した。
