# 身体の中央配置・衣服内の陰影 v60

首輪に対して胴体が左へ寄っていた登録を修正し、奥側の布を衣服内の暗い面として描き直した。手前の青い面に残っていた長い暗い帯も、外光を受ける表側の明るさへ修正する。

- [中心線付きの修正前・修正後](centering-and-lighting.png)
- [脇の陰影の比較](flanks-comparison.png)
- [奥側・手前側・着用の陰影の分担](lighting-layer-ownership.png)
- [マスター・v59・v60](master-before-after.png)
- [全体](neutral-full.png)、[9状態](body-controls.png)
- [版名付きCMO](../../ciel.cmo3)
- 編集用PSD/XCF: `assets/ciel/generated/v60/layers.json` からGIMPで再作成（Git対象外）。

## 身体の基準

v59では胴体を左へ動かしてはいないが、それ以前からの胴体の中心約1086.5pxと首輪側の基準軸1115pxのずれを残していた。v60では`Body48_Torso`の配置を右へ28.5px補正し、以後の衣服の調整ではこの中央配置を基準として固定する。脇の見え方へ合わせて胴体を動かす補正は加えない。頭・首輪・腕・手・上着・ファーとそれらの親変形はv59の位置を保つ。

胴体のRGB画像とネイティブUVは保持し、キーフォームの配置を移動した。アトラスでは不透明・半透明の全画素のRGBAと全アルファが一致する。SDK書き出し時の色にじみ防止処理で、完全透明な領域のRGBだけは隣の衣服の色に応じて再計算される。原寸PNGとPSDの胴体にも同じ移動を適用している。PSDのワールド座標とCMO内の原画像・UV座標は異なるため、中央への移動を二重に適用しない。

## 内側と外側の陰影

`Jacket48_Back`の青い面を、身体と手前の衣服で外光が遮られる内側の布として生成した。明るいシアンの縁や外側の強いハイライトを抑え、低い明度の青緑と控えめな折れ目で奥行きを表す。身体や前面に隠れる中央部分も含め、一続きの面を保持する。

左右の`Jacket48_SleeveUpper`は、外側を向く大きな青い面だけを描き直した。内側を示す暗い帯を取り除き、柔らかい外光が当たる面として明るさをそろえる。ファーの落ち影、立体面の通常の陰影、金具や白い布はそれぞれの役割を保つ。

生成RGBを既存の素材マスク内へ座標登録した。生成結果に含まれる余白の発光や別の素材の色は取り込まず、青い面の有効画素だけを参照する。マスク外のRGBA、上着3素材のアルファ、ファーの原寸RGBAと位置は保持した。ほかの18素材はv59と同一。[生成来歴](../../../generated/v60/generation-provenance.json)を参照。

## 検証

- [首輪・胸の飾り・胴体中心、内外の輝度](lighting-verification.json)
- [元頂点・編集頂点・全キーフォーム・UV](native-geometry-verification.json)
- [SDK頂点登録、110メッシュの保持、制御](master-runtime-verification.json)
- [着脱・手3種・既存11表情](runtime-verification.json)
- [ネイティブ構造](structural-verification.json)

中心線と輪郭だけでなく、実SDKの首輪の金具と胸の飾りの画素位置を照合する。内側の布の輝度、外側の面の輝度、旧来の暗い帯の改善、マスク外画素・アルファ・ファーの保持も別々に確認する。

大きな肘曲げの上下袖の接続、衣装の物理接続、大きな腕上げの姿勢補正は引き続き調整対象。2026-10-15に正式モデル・現行素材・SDK更新パッケージ・Unityモデルへ採用した。[採用記録](adoption.json)、[採用後の検証](adoption-verification.json)を参照。

## 制作時の検証手順（履歴）

v59のCMO・階層・SDKを`.local/master-jacket-v60/`へ保存する。`build-interior-lighting.py <内側の生成原本> <表側の生成原本>`で素材を作り、`integrate-interior-lighting.py`で候補を保存する。候補の時点で`verify-interior-lighting.py --candidate`を実行する。最終PNGからGIMPでPSD/XCFを作る。

候補CMOと階層をドラフトへコピーし、`check-master-native-geometry.py --interior-light`、`check-body-outfit.py --interior-light`で検証する。Editorでは`.local/master-jacket-v60/body-outfit-v60-candidate.cmo3`を新しく開き、タイトルと読み込み先を確認してSDKを書き出す。既に開いている同名の旧モデルへディスク変更が反映されたと仮定しない。

`package-body-outfit-runtime.py`の後、`compare-master-jacket.py --interior-light`、`verify-interior-lighting.py`、`render-body-outfit-proof.py --interior-light`を実行する。書き出し後にSDKテクスチャだけを変更せず、最終PNG・PSD/XCF・ネイティブCMO・SDKが同じ変更を持つことを照合する。

実SDKの登録誤差は最大約0.00013px。首輪の金具と胸の飾りの中心差は約0.073px。110メッシュは6姿勢でv59と一致。11表情の頭部89メッシュは頂点差分0px。最終PNGとPSD/XCFの22レイヤーの照合も通過した。

制作スクリプトと比較用の途中版は `.local/body-outfit-history/` へ退避した。以下の旧手順は制作時の記録であり、クリーンなチェックアウトからの再検証には `python -B scripts/live2d/adopt-body-outfit.py` を使う。PSD/XCFは最終22素材の `layers.json` からGIMPで再作成できる。

Unity Editorへの取り込み・表情ターゲット・ファイル整合は [unity-verification.json](unity-verification.json) を参照。

[現行111層のPSD/XCF往復検証](current-psd-verification.json)も完了。全レイヤー名・順序・座標オフセットと入力PNGのハッシュが一致する。
