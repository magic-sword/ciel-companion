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
