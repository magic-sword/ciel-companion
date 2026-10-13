# 驚きの調整案 v34

目の開き値を増やすだけでは上限で止まるため、`ParamSurprised`でまぶた・白目を丸く開く専用キーを追加した。
瞳の幅は元の70%、高さは74.2%、白目の縦幅は115%。瞳とハイライトを下へ20px補正し、
中央の下側の白目の余白は左右で10〜11pxになった。目線・まばたきは既存のパラメーターを使う。

丸口はv22の見本から領域・色マスクで抽出。新規生成や描き直しはしていない。
鼻と顎を基準に共通の倍率と位置で配置し、驚き専用の`Mouth_Surprised`として追加した。
発話で口を大きく開くと既存の開口へ切り替わる。丸口のまま発話する形は必要なら別途調整できる。

[見本・調整前・調整後](../../rig/proofs/surprised-v34/reference-comparison.png)・
[まばたきと開口](../../rig/proofs/surprised-v34/blink-and-mouth.png)。
通常・嬉しい・にこにこの全既存メッシュの位置と不透明度は一致。
驚き・目線・角度・まばたき・開口の81組み合わせの有限頂点と通常復帰を検証した。

2026-10-14に採用済み。[正式なCubismモデル](../../rig/README.md)・現行素材67層・Unity更新パッケージへ反映した。
Unityのモデル自体はまだ差し替えていない。

再現：`prepare-surprised.py`で丸口を抽出してPSDを新規メッシュとして取り込み、
`integrate-surprised.py`でキーを設定。Cubismでアトラスを配置して保存・書き出し、`check-surprised.py`で確認する。
採用後の回帰確認では、`check-surprised.py`の第3引数に変更前のmodel3.jsonを指定する。
`integrate-surprised.py`には20pxの位置補正も含む。
`adjust-surprised-iris-position.py`は位置補正前の試作にだけ1回適用する追加処理。
