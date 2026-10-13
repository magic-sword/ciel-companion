# v23 表情用の追加素材

指定の透明PNG 8枚を [layers/](layers/) に保存した。全て **2172×2896・RGBA**、既存の組み上げ座標に配置済み。`assets/ciel/current/` は変更していない。

**残る見た目の注意:** `Eye_L_Happy` / `Eye_R_Happy` の肌パッチは、拡大すると周囲の肌との薄い色差と明るい縁が見える。単色背景への切り出しは4回まで実施し、4回目を採用した。塗り直しや色合わせの描き足しはしていないため、この継ぎ目は残して報告する。見た目の承認済み素材とは扱わない。

## 最初に見る確認図

- [5表情：元の組み上げ／v23／承認済みv22見本](expressions-comparison.png)
- [全身の正面比較](front-comparison.png)
- [8素材を暗い背景で確認](layers-dark-sheet.png)
- [閉じ目：開眼層OFF／あえてONの比較](qa/occlusion/happy-open-eye-coverage.png)
- [閉じ目Rの拡大](proofs/details/Eye_R_Happy.png)、[閉じ目Lの拡大](proofs/details/Eye_L_Happy.png)

各表情の元サイズ合成は [assembled/](assembled/)、層ごとの「重ねる前／後」は [proofs/layers/](proofs/layers/)、拡大は [proofs/details/](proofs/details/) にある。合成PNGは全キャンバス2172×2896。

## 納品した8層

左右名は既存レイヤーに合わせた。**L＝向かって右、R＝向かって左**。

| ファイル | 内容・重ね方 | 重ねる前／後 |
| --- | --- | --- |
| [Cheek_Blush.png](layers/Cheek_Blush.png) | 左右の半透明の赤みと細い斜線。顔の肌・髪影の上、目・口より下 | [確認](proofs/layers/Cheek_Blush.png) |
| [Eye_L_Happy.png](layers/Eye_L_Happy.png) | 上向きの弧のまつげ、薄い陰、開眼範囲を覆う不透明な肌 | [確認](proofs/layers/Eye_L_Happy.png) |
| [Eye_R_Happy.png](layers/Eye_R_Happy.png) | 同上。使用時はその側の既存Eye_*層を非表示 | [確認](proofs/layers/Eye_R_Happy.png) |
| [Tear_L.png](layers/Tear_L.png) | 下まぶたに沿う浅い水色の涙と小さな光。開いた目の上 | [確認](proofs/layers/Tear_L.png) |
| [Tear_R.png](layers/Tear_R.png) | 同上。落下する涙や頬の筋は含めない | [確認](proofs/layers/Tear_R.png) |
| [Sweat.png](layers/Sweat.png) | 向かって右のこめかみの小さなしずく1つ。前髪の上 | [確認](proofs/layers/Sweat.png) |
| [Eye_L_Sparkle.png](layers/Eye_L_Sparkle.png) | 白い四芒星と小さな光。瞳の色は含めず、既存の瞳・ハイライトの上 | [確認](proofs/layers/Eye_L_Sparkle.png) |
| [Eye_R_Sparkle.png](layers/Eye_R_Sparkle.png) | 同上 | [確認](proofs/layers/Eye_R_Sparkle.png) |

## 作り方と記録

1. [指定の組み上げ](inputs/assembled-current.png) から、`(550,650)-(1600,1700)` の1050×1050をそのまま切り出した。承認済みv22見本は見た目の参照として使用。
2. この顔画像を素材ごとに編集した。頬2回、閉じ目2回、涙・汗・星は各1回。頬の初回は顔の比率が変わり不採用。閉じ目の初回は肌に不要な透過が入り不採用。原画像は [edits/](edits/) に保存。
3. 元／編集／50%重ね合わせを [qa/](qa/) に保存。**生成画像全体は画素一致していない**。髪・輪郭・首輪などに微差や不要な透過があり、[数値記録](qa/edit-metrics.json) にも不一致を残した。生成した顔全体を既存モデルの差し替えには使っていない。
4. 編集画像を参照し、追加部分だけを単色背景へ取り出した。[keyed/](keyed/) に全試作を保存。頬・星は黒、涙・汗は緑。閉じ目は緑背景で肌の範囲過大・縁の色残りが出たため黒背景も試し、4回目の黒背景を採用。
5. 単色背景との色差からアルファを決定し、背景との混色を逆算。黒いまつげを透明化しないよう、肌に囲まれた領域は不透明なマットに含めた。境界のマット処理以外で、線や肌のRGBを描き足す・塗る処理はしていない。
6. 左右を空白部分で分割し、**縦横同じ倍率の拡縮と移動だけ**でキャンバスへ配置した。回転・ワープ・縦横別の拡縮はしていない。

全プロンプト・ツール出力元・採用判断は [generation-complete.json](generation-complete.json)。`generation-log.json` と `generation-provenance.json` は途中段階の記録。

### 配置

単色背景画像は1254×1254。通常の部品は1050×1050へ等倍率縮小し、`(550,650)` に配置した。

閉じ目は開眼範囲を覆えるよう、左右それぞれ1176×1176へ等倍率縮小して、R=`(513,573)`、L=`(430,564)` に配置。汗は788×788へ等倍率縮小して、`(767,708)` に配置した。キャンバスと部品の形に非等方変形はない。

正確な倍率・移動・非透明範囲・SHA-256は [placement.json](placement.json)。処理は [build.py](../../../../scripts/live2d/v23/build.py)、再実行方法は [README](../../../../scripts/live2d/v23/README.md)。

## 合成・Live2Dでの表示

現在の `layers.json` の下から上の順序を使用し、`visible:false` の部品は通常非表示とした。[v23用layers.json](layers.json) は既存51層＋新規8層の59層。新規層は初期状態では全て非表示。既存のマニフェストは変更していない。

| 表情 | 表示する追加層・口 |
| --- | --- |
| 嬉しい | Eye_L_Happy ＋ Eye_R_Happy ＋ Cheek_Blush ＋ 既存Mouth_Large |
| 照れ | Cheek_Blush |
| 半泣き | Tear_L ＋ Tear_R |
| 困り | Sweat |
| わくわく | Eye_L_Sparkle ＋ Eye_R_Sparkle ＋ 既存Mouth_Large |

Happy使用時は既存の左右のEye_*を全て非表示にする。Mouth_Large使用時は既存の他のMouth_*を非表示にする。[expression-presets.json](expression-presets.json) に具体的な表示／非表示リストを保存した。表情を切り替える前に通常表示へ戻し、新規8層の不透明度を0に戻す。

眉・口の変形・目線・耳の倒し方はこの確認図では実施していない。このため見本との表情全体の違いは残る。今回の図は指定の追加素材と既存Mouth_Largeの組み合わせを確認するもの。Live2Dのパラメーターやメッシュは未編集。

## 検証

- 保存した8ファイルを読み戻し、全てRGBA・2172×2896・空ではないことを確認。
- 既存レイヤーからの再合成は、指定された `assembled-current.png` とRGBA全画素一致。
- current配下の全ファイルを作業前後のSHA-256で比較し、一致。
- 各層の合成で、顔の作業領域 `(700,800)-(1500,1350)` の外に変更は0画素。
- Happyを表示したまま開眼層をON／OFFして比較。最大差は8bit値で5、差8を超える画素は0。開眼時の絵が目視で透けないことを確認した。ただし輪郭付近に微小な合成差があるため、運用は指定どおり開眼層をOFFにする。
- 閉じ目の肌の縁は、冒頭に記したとおり要目視確認。生成画像との完全な画素一致や、肌の継ぎ目が完全に消えたという判定はしていない。

詳細は [verification.json](verification.json)。今回の保存・編集先は `assets/ciel/generated/v23/` と `scripts/live2d/v23/`。currentへの反映、PSD作成、リグ変更は実施していない。
