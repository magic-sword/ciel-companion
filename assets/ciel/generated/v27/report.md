# v27 承認見本から直接取り出す試行

ユーザー提案に従い、承認済みv22の「嬉しい」を直接画像編集して笑い目と口を透明素材へ取り出した。
顔を新しく描き直してから抽出するv25・v26の中間工程を省いた。

## 比較

- [承認見本・v26・今回のv27](proofs/happy-face-comparison.png)
- [全体の比較](proofs/happy-front-comparison.png)
- [見本の目・口と抽出後の素材の拡大](proofs/reference-extraction-details.png)
- [組み上げた修正案](proofs/happy-assembled.png)

比較は素材合成。CubismとUnityのモデルはまだ変更していない。

## 素材

| ファイル | 内容 |
| --- | --- |
| [Eye_R_Happy.png](layers/Eye_R_Happy.png) | 画面左の笑い目と短いまぶたの線、白い光 |
| [Eye_L_Happy.png](layers/Eye_L_Happy.png) | 同上、画面右 |
| [Mouth_Happy.png](layers/Mouth_Happy.png) | 見本から直接取り出した丸いピンクの笑い口 |
| [Cheek_Blush_Happy.png](layers/Cheek_Blush_Happy.png) | v25で使った既存の赤みを41px上へ移動。再生成・色変更・拡大縮小なし |

全て2172×2896・RGBA PNG。目と口には肌パッチを含めない。
頬の赤みはv25と同じ表示量0.45で比較した。濃いv26の頬の素材は使っていない。

## 結果と限界

合成を比較し、v26よりまぶたの線が短く、赤みが淡くなったことを確認した。
赤みの位置は以前より上で、目に近づいている。

「見本から直接」とは、見本を画像編集ツールの入力にして、その描かれた部分を透明化で取り出すこと。
厳密な画素の切り抜きではない。抽出時に線の厚み・先端・まぶたの曲線・光に微差が残る。
拡大図に見本と結果を並べ、画素一致のようには報告していない。
髪に隠れた一部は抽出の段階で補完されるが、見えている形を保つよう指示した。
最終的な顔の印象はユーザーの比較確認で判断する。

生成は1回。入力と原画を保存し、依頼全文は [generation-provenance.json](generation-provenance.json)。
後処理は矩形による部位の切り分け、アルファ範囲の切り詰め、縦横同率の拡大縮小と移動のみ。
線・肌をプログラムで描き足していない。顔の肌・髪・眉・鼻・耳・首輪は現在の既存素材を重ねた。
処理の再現は `scripts/live2d/v27/build.py`。

[verification.json](verification.json)：4素材のキャンバス・RGBA、赤みの移動後の画素保持、current変更なしを確認。
位置・倍率と素材ハッシュは [placement.json](placement.json)。
採用時にはメッシュとアトラスを更新し、元の目を非表示にする構成を維持する。
笑い口と嬉しい用の赤みは専用層として制御し、会話の口パクと頭の角度でも確認する。
