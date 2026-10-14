# 表情素材の取り込み記録（2026-10-13）

Claude Code の中断後、保存済みの v23・v24 を Cubism と Unity に組み込んだ。
見た目の仕上がりをユーザーが承認したという意味ではなく、表情を動かして比較できる状態にした記録。

## 現在の成果物

- 素材：`assets/ciel/current/layers/`、59層。v23 の追加8層、v24 の耳・白目・瞳の差し替え10層を反映。
- 作業モデル：`assets/ciel/rig/ciel.cmo3`。Cubism 5.3.04 で開き、アトラスを更新して保存した。
- Unity：`unity/Assets/Characters/Ciel/` の moc3・アトラス・表示情報・モデルアセット・プレハブを更新。既存の物理演算、頷き、目パチ・口パクの参照は維持。
- Core の12表情：[一覧](../assets/ciel/rig/proofs/expressions/expressions-12.png)、[v22見本との比較](../assets/ciel/rig/proofs/expressions/reference-comparison.png)。
- 機械検証：`assets/ciel/rig/proofs/expressions/verification.json`。

引き継ぎ時、正式な `ciel.cmo3` は表情キーの追加前だった。最新のキーと `ParamEar` は
`.local/work/expr2.cmo3` に残っていたため、そのコピーを取り込みの基準にした。
中断時に開いていた Cubism の `expr2` タブは変更せず残した。

## パラメーターと変形

| パラメーター | 用途 |
| --- | --- |
| `ParamEyeLSmile` / `ParamEyeRSmile` | 笑い目。0で通常、1で笑い目。元の側の目の9層を同時に消す |
| `ParamCheek` | 頬の赤み |
| `ParamTear` | 下まぶたの涙、左右共通 |
| `ParamSweat` | こめかみの汗 |
| `ParamSparkle` | 左右の瞳のキラキラ |
| `ParamEar` | 耳。正値は立つ、負値は外へ倒す |

笑い目と涙は各側の目のワープへ、キラキラは瞳のワープへ入れ、
キラキラには既存の瞳と同じ白目クリッピングを使った。頬と汗は顔の動きに追従する。
耳と瞳のメッシュは、v24 で補った範囲まで広げた。
耳の倒し方は下側25%を固定し、先端ほど曲がるようにした。

Unity の表情は素材のパラメーターを追加し、値をそのままの単位で加算するよう修正した。
以前の「範囲の半分を掛ける」方式では、0〜1の笑い目や頬に1を指定しても0.5までしか出なかった。
「にこにこ」は通常の目を少し細め、「嬉しい」の閉じ笑い目と区別する。

## 再現用の道具

1. `scripts/live2d/gimp/build_layers_psd.py` で v23 の追加8層だけの PSD を作り、Cubism の最新リグのコピーへ「全てのレイヤーを新規アートメッシュとして追加」で取り込む。
2. 保存したコピーに `integrate-expressions.py 入力.cmo3 出力.cmo3` を実行する。v24画像、メッシュ、追従先、表示キーを組み込む。
3. `expression-keys.py 入力.cmo3 出力.cmo3` で変形キーを設定する。
4. Cubism で開く。アトラスの未配置8素材を選択し、「選択要素をテクスチャアトラスに配置」。アトラス上の全素材を選択して自動レイアウトし、保存・moc3書き出しを行う。
5. `check-expressions.py モデル.model3.json 出力ディレクトリ` で Unity の設定と同じ12表情を描画し、素材表示と中間値を検証する。
6. Unity の `CielIdleSetup.Run` で再取り込みし、`CielExpressionPlayCheck.Run` で実際の再生ループの表情切り替え・TTL・描画を確認する。

取り込みスクリプトは Cubism XML の形式情報を保持する。CAFF 保存処理も修正した。
従来は PNG のサイズが変わっても後続ファイルの絶対位置を更新しなかったため、
Cubism が main.xml を正しい位置から読めなかった。現在は保存時に再計算し、
`scripts/live2d/test_caff.py` でサイズ変更後の読み出し位置を検証している。

作業前の素材・Unityモデルと正式リグのコピーは `.local/expression-integration/` に退避した。
確認用の PSD、途中のモデル、Unity のログも同ディレクトリにある。Git 管理外の作業用データ。

## 確認と見た目の残り

- Core：追加素材6パラメーターで0のとき非表示・1のとき表示。笑い目では元の目を非表示。
- Core：12表情と、耳・目パチ・目線・頭の角度・笑い目を組み合わせた15の中間値で有限の頂点を確認。通常に戻すと追加素材が消える。
- Unity：モデル再取り込みとコンパイルは終了コード0。
- Unity：実際の再生ループで12表情を順に切り替え、表示パラメーター・有限の頂点・画像の前景画素を検証。TTLによる通常への復帰も成功、終了コード0。`assets/ciel/rig/proofs/expressions/unity/verification.txt`。

確認カメラの書き出しは URP の `SingleCameraRequest` を使う。新しい描画先を使うたびに
Cubism の描画グループを更新し、キャッシュされた `CurrentFrameBuffer` を更新する。
この処理がないと確認画像の2枚目以降が背景だけになるため、描画検証では前景画素数も確認する。

見本と一致する完成形にはまだ差がある。眉は前髪に隠れて見えにくい。
半泣きの涙は控えめで、驚き専用の白目・丸口、ぷんすか専用の膨らんだ頬は追加していない。
笑い目の肌パッチは元の素材報告どおり、拡大すると境界の色差が残る可能性がある。
耳は曲げて倒す方式なので、v22 の折れた耳の形とは異なる。
見た目の判断には数値だけでなく比較図と Unity の表示を使う。

## 嬉しい表情の素材候補 v28

ユーザーの配置調整依頼に合わせ、v27の目・口を再生成せず縮小・移動した。
鼻と顎を基準に見本の倍率を合わせ、笑い目は約20%、口は約15%小さくした。
笑い目を下げ、頬の赤みも左右別に位置を合わせた。赤みの表示量は淡い0.45を維持。
[比較図](../assets/ciel/generated/v28/proofs/happy-face-comparison.png)と
[調整記録](../assets/ciel/generated/v28/report.md)に詳細を残した。
これは素材合成の候補。現行の素材・Cubismモデル・Unityモデルにはまだ反映していない。

## v29 目の幅・目尻と横髪の接点の確認

v28の目が小さく浮いて見えるとの指摘を受け、幅だけ・接点だけ・両方と高さを
調整した3案を既存素材で比較した。
[比較図](../assets/ciel/generated/v29/proofs/happy-face-comparison.png)、
[条件別比較](../assets/ciel/generated/v29/proofs/controlled-comparison.png)、
[詳細記録](../assets/ciel/generated/v29/report.md)。
幅を260pxへ戻し、目尻を髪へ3px重ねた案では小ささと浮き感が軽くなる。
見本との差として目尻の尖り・まつ毛の弧が残り、さらに近づけるなら目素材の再編集が候補。
顔の土台や横髪の再生成は現時点で勧めない。v29は素材合成の確認で、モデルへは未反映。

## v30 輪郭線付きの一体抽出

ユーザーの依頼で、承認見本から笑い目・口・左右の赤み・鼻・頬から顎の輪郭線を
1枚の透明画像に再抽出した。[透明PNG](../assets/ciel/generated/v30/face-details-with-contour.png)、
[比較図](../assets/ciel/generated/v30/proofs/reference-extraction-comparison.png)、
[詳細記録](../assets/ciel/generated/v30/report.md)。個々の素材を分離せず、全体共通の縮小・移動のみ。
輪郭を比較・配置の基準に使える一方、生成を伴う抽出には線・口・赤みの差が残る。
見本と画素が一致する切り抜きではなく、バランスが完全に保たれたという結論にはしていない。
現行素材・Cubism・Unityへは未反映。

## v31 画像編集で分離・差し替え合成

v30の一体画像を画像編集のマスクで7枚（左右の目・左右の赤み・口・鼻・輪郭）へ分離。
新しい生成は行わず、元の画素とアルファを保った。重ね直した際の画素一致を確認した。
[見本との完成合成比較](../assets/ciel/generated/v31/proofs/reference-comparison.png)、
[編集用レイヤー文書](../assets/ciel/generated/v31/face-parts.ora)、
[詳細](../assets/ciel/generated/v31/report.md)。輪郭幅を基準に全パーツ共通の倍率・移動で配置。
通常の比較は顔の土台を維持して表情パーツを差し替えた静止合成。
輪郭線自体はガイドとして使用し、二重線を避けて完成比較では表示していない。
抽出輪郭と現在の土台のずれは別の診断図に残した。Cubism・Unityには未反映。

## v31採用版をCubismへ反映

ユーザーの採用指示により、v31の笑い目・笑い口・赤み・鼻を正式な
`assets/ciel/rig/ciel.cmo3`へ反映した。モデルはCubism 5.3.04で開き、
アトラスを再配置し、保存・moc3書き出しまで確認済み。
[実モデル描画と見本の比較](../assets/ciel/rig/proofs/happy-v31/face-comparison.png)、
[検証記録](../assets/ciel/rig/proofs/happy-v31/verification.json)。

### 表示方法

| パラメーター | 今回のニッコリ顔 |
| --- | --- |
| `ParamEyeLSmile`（左目 笑顔） | 1 |
| `ParamEyeRSmile`（右目 笑顔） | 1 |
| `ParamHappy`（嬉しい 顔：口・頬・鼻） | 1 |

通常顔へ戻すときは3つを0にする。`ParamHappy`は今回追加した。
左右の目は既存の笑顔パラメーターを使い、通常の目の各層を隠す構成を維持した。
`ParamHappy=1`では専用の口・頬・鼻を表示し、共通の口の6層・鼻・赤みを隠す。
輪郭線は配置の基準として使い、二重になるため描画用メッシュには追加していない。

### 現行素材の整理

- `Eye_L_Happy.png` / `Eye_R_Happy.png`は同じ名前で採用版へ置き換えた。旧笑い目を別メッシュとして追加していない。
- 専用素材`Mouth_Happy.png`・`Cheek_Happy.png`・`Nose_Happy.png`を追加。
  赤みは左右を同じキャンバス上で合成して1層にした。描き直しはしていない。
- `assets/ciel/current/layers.json`は62層で、名前の重複なし。
  旧版候補は現行素材へ混在させず、`generated/v25〜v31`を検証履歴として保持。
- 共通の口・赤み・鼻は他の表情に必要なため保持し、今回の表情中には隠れるようにした。
  他の表情の見た目の調整は進めていない。
- 作業前の正式モデルと現行素材は`.local/happy-integration/`へ退避。

### 検証と適用範囲

新しい5メッシュの表示・旧素材の非表示・通常復帰・IDの重複なしをCoreで確認。
顔の角度、口の開き、表情の中間値の45組み合わせで有限の頂点を確認した。
今回の笑い目以外の既存メッシュ57個は、通常時の頂点と不透明度が以前の書き出しモデルと一致。
静止合成だけでなく、書き出したmoc3とアトラスを使って比較図を作成した。
正式モデルをCubismで開き直し、3つのパラメーターを1にした
[エディター上の表示](../assets/ciel/rig/proofs/happy-v31/cubism-preview.png)も確認した。
現行素材から`ciel-current.psd`とXCFを作り直し、62層の名前・順序を再読み込みで検証。
現行PNGの一覧はmanifestと完全に一致し、余分なPNGはない。

取り込み用PSDの作成は`prepare-happy-materials.py`とGIMPの`build_layers_psd.py`。
設定は`integrate-happy.py`、検証は`check-happy.py`、採用は`promote-happy.py`。
取り込み処理はCubism保存後のインライン画像参照と共有アトラスを区別するよう修正した。
CAFFの書き込みでは符号ビットの立ったキーの上位オフセット欄を修正し、2つの回帰テストが成功。

今回はCubismへの反映まで。Unityのモデル・表情割り当ては更新していないため、
Unityへ適用する際は新モデルの取り込みと、嬉しい表情への`ParamHappy=1`の追加が必要。
素材生成の知見は[ciel-codex-request-guide-ja.md](ciel-codex-request-guide-ja.md)に追記した。

## v32 にこにこ：専用パラメーターで切り替え

ユーザーの再生成許可と切り替えやすさの要望を受け、`ParamRelaxed`（にこにこ）を追加。
1で専用の口・頬とまぶたの形をまとめて変更し、0で元の形へ戻す。
目・瞳・ハイライトと開口素材は既存のものを使い、まばたき・目線・口パクの制御を維持。
原画の再生成は口と頬のために1回実施し、輪郭付き一体画像から画像編集で分離した。
[詳しい構成](../assets/ciel/generated/v32/report.md)、
[見本との実モデル比較](../assets/ciel/rig/proofs/relaxed-v32/reference-comparison.png)、
[まばたきと開口](../assets/ciel/rig/proofs/relaxed-v32/blink-and-mouth.png)。

通常顔と前回の嬉しい顔は、専用パラメーター0で全既存メッシュの頂点・不透明度が一致。
81組み合わせの有限頂点と、閉眼・開口時の表示・通常復帰・重複IDなしを検証した。
正式モデル`assets/ciel/rig/ciel.cmo3`と現行素材64層へ反映済み。
通常・嬉しい・にこにこの切り替え用exp3.jsonを`assets/ciel/rig/expressions/`に用意した。
これらは表情用パラメーターだけを変更し、目の開閉・目線・口の開閉を固定しない。
前回の嬉しいから切り替える場合も、旧表情用の4パラメーターを明示的に切り替える。
Unityへの取り込みと会話からの割り当ては未実施。

### にこにこの下まぶたの追加調整

ユーザーの指摘を受け、下まぶたの中央を追加で持ち上げた。
目頭・目尻で変位が小さくなる曲線を使い、白目の下端・下まぶたの肌・下まつ毛を合わせた。
上まぶたは変更していない。追加量は中央で最大18pxを基準とし、目の開閉値に比例するため
完全閉眼では追加の変位が0になる。画像の再生成や素材の変更は行っていない。
[見本・調整前・調整後の比較](../assets/ciel/rig/proofs/relaxed-lower-lid/lower-lid-comparison.png)、
[まばたきと開口](../assets/ciel/rig/proofs/relaxed-lower-lid/blink-and-mouth.png)。

通常顔・前回の嬉しい顔・完全閉眼の全メッシュの頂点と不透明度が調整前と一致。
にこにこ中に位置が変わるのは左右の白目・下まぶたの肌・下まつ毛の計6メッシュで、
白目の上端も一致することを確認した。81組み合わせの動作検証も成功。
検証済みの変更を正式な`assets/ciel/rig/ciel.cmo3`へ反映した。
再現はv32のモデルに`adjust-relaxed-lower-lid.py 入力.cmo3 出力.cmo3 18`を1回適用し、
Cubismで保存・書き出し後、`check-relaxed-lower-lid.py`と`check-relaxed.py`で確認する。
変更前モデルは`.local/lower-lid-integration/ciel-before.cmo3`に退避。Unityは未更新。

### v33：下側が浮いて見える白い帯の修正

瞳と白目の下端は一致していたが、下まぶたの薄い肌パーツが瞳の下端に重なり、
既存の下まつ毛線も中央まで届いていなかった。にこにこ中だけ両者を隠し、
v32の一体画像から画像編集で分離した薄い下まぶた線を、白目の描画下端へ合わせた。
瞳・白目の形と位置は変更していない。開眼と半閉眼にキーを設け、完全閉眼では追加線を消す。

[変更前後](../assets/ciel/rig/proofs/relaxed-boundary-v33/boundary-comparison.png)・
[承認見本との比較](../assets/ciel/rig/proofs/relaxed-boundary-v33/reference-comparison.png)・
[まばたきと開口](../assets/ciel/rig/proofs/relaxed-boundary-v33/blink-and-mouth.png)。
通常・嬉しい・完全閉眼は全既存メッシュの位置と不透明度が以前と一致。
左右の線と白目の下端の距離は95百分位で1.32px未満、81組み合わせの動作検証も成功した。
正式モデル`assets/ciel/rig/ciel.cmo3`と現行素材66層・PSD・XCFへ反映済み。
共通の下まぶた素材は他の表情で使うため保持している。Unityは未更新。
再現手順は[v33の記録](../assets/ciel/generated/v33/report.md)。

### にこにこの目尻調整

目尻で下へ長く伸びていた上まつ毛の外側を、`ParamRelaxed=1`の変形キーだけで短縮した。
素材の生成・差し替えはしていない。中央の上まつ毛、瞳・白目・下まぶた、横髪・顔土台は変更なし。
半閉眼では調整量を減らし、完全閉眼では元のキーを保つ。

[変更前後](../assets/ciel/rig/proofs/relaxed-eye-corners/eye-corner-comparison.png)・
[見本との比較](../assets/ciel/rig/proofs/relaxed-eye-corners/reference-comparison.png)・
[まばたきと開口](../assets/ciel/rig/proofs/relaxed-eye-corners/blink-and-mouth.png)。
描画された外側の黒い部分の下端は右目で20px、左目で24px上がった（モデルの2172×2896キャンバス）。
通常・嬉しい・完全閉眼の位置と不透明度は以前と一致。
変わるのは左右の`LashUpper`だけで、中央と横幅は維持し、メッシュの反転もない。
81組み合わせの動作と前回の下まぶたの境界検証も成功した。

正式モデル`assets/ciel/rig/ciel.cmo3`へ反映。素材66層とPSD・XCFは変更不要。Unityは未更新。
再現はv33のモデルに`adjust-relaxed-eye-corners.py 入力.cmo3 出力.cmo3 0.55`を1回適用し、
Cubismで保存・書き出し後、`check-relaxed-eye-corners.py`・`check-relaxed.py`・
`check-relaxed-lid-boundary.py`で確認し、`promote-relaxed-eye-corners.py`で採用する。
変更前モデルは`.local/eye-corner-integration/ciel-before.cmo3`に退避した。

### にこにこの確定とUnity更新の準備

2026-10-13、ユーザーが目尻調整後のにこにこを確定。`current/approved.json`へ採用状態と正式モデルのハッシュを記録した。
最新素材66枚は`current/layers.json`と一致し、旧候補は`generated/`、過去の比較は`rig/proofs/`の記録として区別する。
他の表情で必要な共通素材は保持し、にこにこ中には専用素材へ切り替える。

検証済み書き出しを`assets/ciel/runtime/`へ整理。物理演算・うなずき・まばたき・口パクの既存設定を引き継ぐ。
Unityの`CielExpression`は新モデルを検出すると`ParamRelaxed`を使い、以前の目の細め方を重ねない。
`ParamHappy`も制御し、通常復帰時は両方を0へ上書きする。旧モデルは従来の設定を使う。
モデル自体はまだUnityへ適用せず、`CIEL > Model > Apply Current Package`で更新できる状態にした。
詳細は[更新パッケージの手順](../assets/ciel/runtime/README.md)。

### 驚きの調整案 v34

目の開きを増やす従来の値は上限で止まるため、専用の`ParamSurprised`を試作モデルへ追加した。
瞳を縮小し、白目・まぶたを丸く開く。縮小後の瞳とハイライトを下げ、下側の白目の余白を見本へ近づけた。
口は見本画像から画像編集で丸口を抽出して追加。新規生成は行っていない。
通常・嬉しい・にこにこの全既存メッシュは位置と不透明度が一致し、81組み合わせの動作検証も成功。

[見本・調整前・調整後](../assets/ciel/rig/proofs/surprised-v34/reference-comparison.png)と
[正式モデルの扱い](../assets/ciel/rig/README.md)を参照。
作成時点では試作として別保存し、採用済みモデルとUnity更新一式は変更していなかった。

### 驚きの採用とUnity更新一式

2026-10-14、ユーザーがv34の驚きを採用。正式な`rig/ciel.cmo3`、現行素材67層、PSD・XCF、
通常・嬉しい・にこにこ・驚きの4表情ファイルへ反映した。試作一式は`.local/surprised-adoption/adopted-draft/`へ退避。
`current/approved.json`には新しい正式モデルと検証済み書き出しのハッシュを記録した。
Unityの表情制御は新モデルでは`ParamSurprised`を使い、旧来の目・口の開き値を重ねない。
新旧モデルの切り替え設定、10ファイルの更新パッケージ、67層のハッシュをUnityで検証済み。
モデル自体は未適用で、`CIEL > Model > Apply Current Package`から反映できる。

### ぷんすかと折れ耳の候補（v35）

`rig/drafts/angry/angry.cmo3` に口・眉・左右の折れ耳の4層を追加した候補を保存する。`ParamAngry` と `ParamEarFold` は別キーで、折れ耳を他の表情にも利用できる。原画の向き・毛の重なりが変わるため、耳の大変形は差分素材で表現する。既存の耳デフォーマーを親として使い、顔の動きに追従させる。折れ耳時の `ParamEar` は基本0。

生成した文脈付き画像から使うのは耳だけ。眉・口は見本を直接画像編集して抽出し、眉に残った地色を透過処理した。目・まばたき・目線・頬・顔土台は既存のものを利用する。発話時は既存の開口パーツへ切り替える。

検証と比較は [ぷんすかの比較画像](../assets/ciel/rig/proofs/angry-v35/reference-comparison.png)、[動作の確認](../assets/ciel/rig/proofs/angry-v35/blink-and-mouth.png)、[候補の説明](../assets/ciel/rig/drafts/angry/README.md)。採用済みの通常・嬉しい・にこにこ・驚きのメッシュ位置と不透明度を比較し、候補の81組み合わせの動作を検証する。正式モデル・現行素材・Unity更新用パッケージは採用済みv34を維持する。

### しょんぼりの候補（v36）

v35のぷんすか候補に `ParamSad` を追加し、眉・口・目をまとめて切り替える。口は見本から抽出、眉は見本の輪郭を画像編集で清書した。目元は初案の中央40pxの下げ方から修正し、中央28pxと目尻・目頭の上下差で伏せ目を作る。虹彩・ハイライトを同じ変換で縦0.9倍、下へ28px移動する。閉眼キーと他の表情は維持し、目線にも補正を適用する。素材の再生成は行っていない。

耳は `ParamEarFold=1` でv35の折れ耳を共用し、`ParamEar=0` を基本とする。頬は既存素材を使う。しょんぼり時は他の専用表情キーを0にする。発話時は既存の開口パーツへ切り替える。

[候補モデル](../assets/ciel/rig/drafts/sad/README.md)は73層で、既存のぷんすかも含む。[見本との比較](../assets/ciel/rig/proofs/sad-v36/reference-comparison.png)、[まばたき・発話](../assets/ciel/rig/proofs/sad-v36/blink-and-mouth.png)を保存する。正式モデル・現行素材・正式なUnity更新用パッケージは、この候補へ変更していない。

虹彩の上側に白い帯が出ないよう、虹彩の上端だけを最大38px延長し、瞼の裏まで覆う。瞳孔付近とハイライトにはこの延長を適用しない。

上瞼は、見本と前回候補のまつげ上端を測り、左右別の二次曲線で追加補正済み。虹彩・ハイライトは前回の位置を維持する。最新の比較は [上瞼の変更前後](../assets/ciel/rig/proofs/sad-v36/lid-shape-comparison.png)。

### しょんぼり・ぷんすかの正式採用

ユーザー承認によりv36の上瞼の最終調整を正式モデルへ採用。v35のぷんすかと折れ耳を含む73層のモデルと現行PNG、PSD・XCF、6表情の切り替えファイル、12ファイルのUnity更新パッケージを整理した。旧候補一式は `.local/sad-adoption/adopted-drafts/` に退避。Unity側はParamSad・ParamAngry・ParamEarFoldをモデルに応じて使用し、旧リグの目・口・耳の変形を重ねず、他の表情では0へ戻す。Unityのモデル自体は未適用で、`CIEL > Model > Apply Current Package` から更新できる。

### 困り顔の候補（v37）

採用済み73層モデルに困り眉・口・汗を追加した76層の候補を別保存する。素材生成は行わず、見本の顔全体の座標を保って口・汗を画像編集で切り出し、眉を清書した。`ParamTroubled` で目・眉・口・汗を切り替え、折れ耳は `ParamEarFold` で共用する。旧Sweatパーツは困り顔中に非表示にする。

上瞼は見本のまつげ上端から左右別の曲線で合わせる。下瞼は初回の通常の形から見直し、困り顔では肌色の下瞼と旧線を非表示にして、白目の境界に合わせた既存のにこにこ用の線を共用する。虹彩・ハイライトは縦0.95倍、下へ18px移動し、虹彩上端を最大18px延長して白い隙間を防ぐ。閉眼・目線・発話は既存のキーを維持する。

[候補モデル](../assets/ciel/rig/drafts/troubled/README.md)、[見本との比較](../assets/ciel/rig/proofs/troubled-v37-lower-lid/reference-comparison.png)、[全表情の下まぶたの検討](../assets/ciel/rig/proofs/lower-lid-review/README.md)を参照。正式モデルと正式なUnity更新パッケージは変更していない。

### 困り顔の正式採用

ユーザー承認によりv37の下まぶた調整後を採用。正式モデル `assets/ciel/rig/ciel.cmo3`、現行PNG76層・PSD/XCF、通常を含む7表情、13ファイルのUnity更新パッケージを整理した。Unity側もParamTroubledを専用キーとして上書きし、折れ耳を共用、旧眉・口・汗・耳の変形を重ねず、通常や他の表情では0へ戻す。旧モデルには従来の値を使用する。

候補モデルと書き出しの重複は `.local/troubled-adoption/adopted-draft/` へ退避。Unityのモデル自体は未適用で、`CIEL > Model > Apply Current Package` から更新する。下まぶたの見直し結果は確認履歴として保持し、今回しょんぼり・驚きの形は変更していない。

### 照れ顔の調整候補（v38）

見本全体の鼻・顎の位置を基準に、ためらった口と鼻までつながる赤みを分離し、眉の輪郭を清書した。新規生成は行っていない。赤みの外周は内側へ25pxぼかし、元絵の鼻点を周囲の赤みに置き換えて二重表示を避ける。

`ParamEmbarrassed`で切り替える。虹彩とハイライトは横幅を左右別に調整して一緒に横へ寄せ、主な反射が上まぶたに隠れないようハイライトの縦位置も調整した。下まぶたの肌色パーツと旧線は照れ中に非表示にし、既存のにこにこ用の線を白目の境界へ合わせて共用する。折れ耳も既存素材を使う。

[候補モデル](../assets/ciel/rig/drafts/embarrassed/README.md)、[見本との比較](../assets/ciel/rig/proofs/embarrassed-v38/reference-comparison.png)。採用済み76層モデルに3層を追加した79層の候補を別保存。正式モデルと正式なUnity更新パッケージは変更していない。

### 照れの目尻・赤みの調整（v39）

v38を基に、照れ中だけ上まつげの外側の下向きの尾を短くした。開眼・半開きで滑らかに変形し、中央のアーチ・虹彩・白目・下まぶたは維持する。メッシュの折れがないことをSDK書き出しで検証した。

赤みはv38素材の面と斜線を分け、面をぼかして弱め、淡い赤色へ寄せて外周を滑らかに透明化した。新規生成・パーツ追加はなく79層のまま。[前回との比較](../assets/ciel/rig/proofs/embarrassed-v39/before-after.png)。最新候補とSDK書き出しは `assets/ciel/rig/drafts/embarrassed/`。正式モデルとUnityへは未適用。

### 照れ顔の正式採用

ユーザー承認によりv39の目尻・赤みの最終調整を正式モデルへ採用した。現行PNG79層、PSD・XCF、通常を含む8表情、14ファイルのUnity更新パッケージを整理した。Unity側はParamEmbarrassedで切り替え、折れ耳を共用し、旧赤み・目線・口・耳の変形を重ねない。他の表情では専用キーを0へ戻す。旧モデルには従来の値を使用する。

候補モデルとSDK書き出しの重複は `.local/embarrassed-adoption/adopted-draft/` へ退避した。Unityのモデル自体は未適用で、`CIEL > Model > Apply Current Package` から反映できる。新モデル・旧モデルの12表情の切り替えと更新パッケージの検証が通った。

### 半泣きの候補（v40）

この節は初回候補の記録。半泣きの顔v40と折れ耳v42は正式採用済みで、最新の実モデル比較は [teary-v42](../assets/ciel/rig/proofs/teary-v42/reference-comparison.png)。

鼻・顎で合わせた見本全体から、波打つ口と下まぶたにたまる涙を左右別に分離した。眉は輪郭を清書し、目元は見本の上まつげの輪郭へ合わせた。新規生成は行っていない。下まぶたの肌色の覆いと旧線を使わず、既存の線を白目の境界に合わせる。頬の赤みと折れ耳は既存素材を共用する。

`ParamTeary`で切り替える。涙は各白目と同じ親に付き、瞳の目線移動には追従しない。左右それぞれの開きに連動し、半開きでは薄く、閉眼では非表示。旧涙パーツを抑え、発話では既存の開口パーツを使う。

[候補モデル](../assets/ciel/rig/drafts/teary/README.md)、[見本との比較](../assets/ciel/rig/proofs/teary-v40/reference-comparison.png)。採用済み79層モデルに4層を追加した83層の候補とSDK書き出しを別保存。既存9ポーズ、左右別のまばたき、涙と目線の独立、81通りの組み合わせを検証した。正式モデルと正式なUnity更新パッケージは変更していない。

### 半泣きとサモエド折れ耳の正式採用（v40＋v42）

ユーザー承認により半泣きの眉・口・左右の涙と、大きめのサモエド折れ耳を正式モデルへ採用した。現行素材83層、PSD・XCF、通常を含む9表情、SDK15ファイルを整理した。耳は既存2層を差し替え、ぷんすか・しょんぼり・困り・照れ・半泣きで共用する。顔の他のパーツは生成画像から採用しない。

Cubismで原画を差し替え、耳のメッシュ範囲を作り直し、アトラス再生成・保存・SDK書き出しを確認した。以前の9ポーズの耳以外の形と表示、涙と目線の独立、左右のまばたき、口パク、81通りの組み合わせを検証。Unityで新旧モデルの12表情切り替えと更新パッケージのハッシュ検証を通過した。

UnityはParamTearyとParamEarFoldを毎フレーム上書きし、通常へ戻ると0にする。半泣き中は旧涙・目・口・耳の値を重ねない。旧モデルには従来の値を使用する。Unityモデル本体は未適用で、CIEL > Model > Apply Current Packageから更新できる。

旧候補CMO・SDKは.local/teary-adoption/adopted-draft/、不採用のv41素材は.local/archive/codex-generated/v41/へ退避。現行素材はassets/ciel/current/、編集対象はassets/ciel/rig/ciel.cmo3に一本化した。
