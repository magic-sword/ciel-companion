# 素材生成の原本と検証履歴

ほっぺのくぼみの影 **v64** が最新。押したときだけ淡く出る左右2層（A案）を正式モデルへ取り込み、現行115層。[生成の記録](v64/report.md)、[モデルでの確認](../rig/proofs/cheek-v64/)。不採用のB案と引っ張り用の影の候補は削除した。尻尾は [tail](tail/)（v63）、身体・上着は [v60](v60/report.md)。

頭頂部の左右補完 **v47** が最新。折れ耳で見える斜めの切り口を丸い輪郭へつなぎ、頭を傾けたときに露出する後ろ髪本体の旧上端も整理した。現行92層・正式モデル・Unity更新用パッケージへ反映済み。[最新の全表情](../rig/proofs/crown-v47/all-expressions.png)、[正式モデルの頭頂部比較](../rig/proofs/crown-v47/native-crown-comparison.png)。旧素材と作業コピーは`.local/crown-completion-adoption/`に保管し、現行素材と混在させない。Unity本体は未更新。

顔の肌色の共通修正 **v46** を正式採用。[肌色採用時のモデル描画](../rig/proofs/skin-v46/all-expressions.png)。お腹の色味を基準に顔土台・まぶた・口元の肌色7層を画像編集で補正した。現行92層・正式モデル・Unity更新用パッケージへ反映済み。旧素材と作業コピーは`.local/skin-adoption/`へ退避した。Unity本体への適用はまだ行っていない。

頭頂部の共通素材 **v45** とジト目 **v44** を正式採用。[全表情の実モデル描画](../rig/proofs/crown-v45/all-expressions.png)。現行92層とUnity更新パッケージへ反映済み。頭頂部は全表情で共用し、頭・後ろ髪の動きに追従する。旧メッシュ引き伸ばし案は採用しない。途中のCMO・SDKは`.local/crown-adoption/`へ退避した。Unity本体への適用はまだ行っていない。

ジト目の原本・分離記録は **v44**。[見本との比較](../rig/proofs/crown-v45/reference-comparison.png)。見本から水平な上まつげと小さな口を分離し、平たい眉を合わせた。通常の虹彩・目線・まばたきと既存の耳を使う。現行素材は`../current/`、正式モデルは`../rig/ciel.cmo3`。

わくわくの採用版は **v43**。[見本との比較](../rig/proofs/excited-v43/reference-comparison.png)。見本から笑い口・赤み・左右のキラキラ入り虹彩を画像編集で用意した。新規生成はせず、既存のまばたき・目線・立ち耳とつなぐ。現行87層とUnity更新パッケージへ反映済み。候補CMO・SDKは `.local/excited-adoption/adopted-draft/` へ退避した。Unity本体への適用はまだ行っていない。

現行採用の折れ耳は **v42**、半泣きの顔は **v40**。[最新の実モデル比較](../rig/proofs/teary-v42/reference-comparison.png)。通常時の耳の量感を参考に見える面積を増やし、既存の折れ耳2層を差し替えた。正式モデル83層とUnity更新パッケージへ反映済み。Unity本体への適用はまだ行っていない。v41は不採用で、画像素材は `.local/archive/codex-generated/v41/` へ退避した。

現行の素材は`../current/`、正式なCubismモデルは`../rig/ciel.cmo3`。
ここは生成原本・依頼記録・配置・比較の履歴であり、候補をそのまま現行素材として使わない。
現在採用しているニッコリ顔はv30の輪郭付き一体抽出を画像編集で分離したv31。
v25〜v29の素材は比較用の旧候補。v23・v24の共通表情素材、耳、白目、瞳も現行素材に反映済み。
にこにこはv32の専用口・頬と、既存の目の専用変形キーを採用した。
v33はv32の一体画像から下まぶた線を分離した版。新規生成せず、にこにこ時の白い帯を除去して境界を合わせた。
にこにこの採用版は、さらに目尻を調整した正式モデル。最新の採用状態は`../current/approved.json`。
v32の口・頬とv33の下まぶた線が現行素材に残り、それ以外の候補画像は原本・検証履歴としてのみ保持する。
Unityへの更新は`../runtime/`を使い、この履歴フォルダから素材を選ばない。

Gitには、再生成で一致を保証できない画像の原本、分離素材と配置、依頼全文、主要な比較図、
検証結果を保存する。候補の原本も品質判断の根拠として残し、採用したものと混在させない。
作業モデル・PSD・XCF・バックアップは`.local/`または`../psd/`に置き、Gitへ追加しない。
確認用に完成した最新の候補一式は`../rig/drafts/`にまとめてGitへ保存する。候補のCubismモデルとSDK書き出しは一つずつ保持し、採用済みの正式モデルとは区別する。途中の作業モデル・旧書き出しは追加しない。
大量の中間合成と試行ごとのQA画像は`.gitignore`で除外し、ローカルで保持する。

完成モデルの比較・検証は`../rig/proofs/`。
v34の驚きは瞳位置補正後を採用済み。丸口を現行素材へ追加し、正式モデルは67層。
素材の入口は`../current/`、Unityへの更新一式は`../runtime/`。
生成方法は[素材の頼み方](../../../docs/ciel-codex-request-guide-ja.md)、
取り込みと適用範囲は[表情の取り込み記録](../../../docs/ciel-expression-integration-ja.md)を参照。

ぷんすかの採用版は **v35**。原本と検証履歴を保持し、[Cubism候補](../rig/drafts/angry/README.md)と[見本との比較](../rig/proofs/angry-v35/reference-comparison.png)を参照する。左右の折れ耳は文脈付きの生成画像から分離し、口・眉は見本から直接抽出した。目・頬・顔土台は既存素材を利用する。元画像・分離素材・配置情報は v35/ にまとめた。

しょんぼりの採用版は **v36**。[Cubism候補](../rig/drafts/sad/README.md)と[見本との比較](../rig/proofs/sad-v36/reference-comparison.png)を参照する。新規生成はせず、口・眉を見本から画像編集で用意し、目は専用の変形キーで伏せ目にした。v35の折れ耳を共用する。モデルは73層で、ぷんすかも含む。

両表情は正式モデルへ採用済み。最新の素材は `../current/`、モデルは `../rig/ciel.cmo3`、Unity更新は `../runtime/`。候補モデル・旧書き出しは `.local/sad-adoption/adopted-drafts/` に退避した。

困り顔の採用版は **v37（下まぶた調整済み）**。[最新比較](../rig/proofs/troubled-v37-lower-lid/reference-comparison.png)を参照。眉・口・汗の原本・分離素材・配置情報はv37に保持する。現行素材は `../current/`、正式モデルは `../rig/ciel.cmo3`、Unity更新パッケージは `../runtime/`。76層の正式モデルへ採用し、候補の重複は `.local/troubled-adoption/adopted-draft/` へ退避した。

照れ顔の採用版は **v39（目尻・赤みの最終調整済み）**。[最新比較](../rig/proofs/embarrassed-v39/reference-comparison.png)。v38は口・眉・赤みの初回抽出と配置の記録、v39は赤みの修正素材と目尻の調整記録。現在の素材は `../current/layers.json`、正式モデルは `../rig/ciel.cmo3`、Unity更新は `../runtime/`。候補モデル・旧書き出しは `.local/embarrassed-adoption/adopted-draft/` へ退避した。

半泣きの採用素材は **v40**。[採用モデルの案内](../rig/drafts/teary/README.md)と[最新の見本比較](../rig/proofs/teary-v42/reference-comparison.png)を参照。見本から口・左右の涙を分離し、眉・目元を合わせた。涙は目線についていかず、左右のまばたきに連動する。顔の素材は新規生成せず、折れ耳は文脈付き生成のv42へ更新。正式モデルとUnity更新パッケージへ反映し、候補CMO・SDKの重複はローカルへ退避した。
