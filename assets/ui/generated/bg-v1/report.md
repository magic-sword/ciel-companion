# 会話背景の納品物

この資料は、このフォルダにある背景画像の用途・寸法・生成元への参照を示す。生成の逐次記録や削除済みの比較画像の索引は維持せず、以前の内容はGit履歴から参照する。

| 背景 | 用途 |
|---|---|
| [salon_day.png](salon_day.png) | 自然光の昼のサロン |
| [salon_dusk.png](salon_dusk.png) | 夕映えと暖色照明 |
| [salon_night.png](salon_night.png) | 夜景とシアンのサーバー光 |

納品画像は1080×1920・9:16のRGB PNG。人物・文字・ロゴ・UIを含まず、画像自体にはぼかしを加えていない。生成原画から拡大したもので、ネイティブ1080×1920の生成品質を保証しない。生成元と寸法処理は[generation_log.json](generation_log.json)と[image_metadata.json](image_metadata.json)を参照する。

アプリの画角・背景処理・UIとの重なりは、採用中の画像とモデルを使って確認する。ここにないpreviewsを確認済みの根拠へ使わず、実機の結果は[確認状況](../../../../docs/testing/verification-status-ja.md)へ記録する。元の参照素材の利用条件を引き継ぎ、コードのライセンスを自動適用しない。
