# 現在の確認範囲と配布状況

> 責務：現在の機能確認・配布状況と、カテゴリ別の実測資料への索引。

目的・合格条件・改善と結果は[ベンチマーク案内](benchmark-guide-ja.md)から読む。この資料は現在の配布・確認範囲と、実測の正本への索引を持つ。試行の条件・ソース・失敗・生データはカテゴリ別の資料に置く。数値は測定時のソースの証拠であり、現在のHEADや配布済みサービスの成績へ自動で読み替えない。

| 実測の正本 | 何を確認できるか |
|---|---|
| [Minecraft](minecraft-results-ja.md) | 体と会話の課題、整地・建築・対象指定、未達成の理由 |
| [音声](voice-results-ja.md) | 認識の精度、本返答の開始時間、録音と実機の差 |
| [能力選択とキャッシュ](capability-results-ja.md) | ツール公開方式、能力追加時の選択、入力再利用と待ち時間 |
| [人格と身体表現](weight-space-results-ja.md) | 指示候補の自動評価と人手採点の未完了範囲 |
| [画像](vision-results-ja.md) | 合成画像のAPI試験と会話への画像添付 |

## 確認範囲

### 会話評価の段階1〜5と達成度スコア

[会話評価仕様](weight-space-benchmark-ja.md#段階15の会話評価の全体設計)に沿い、長さの超過量・反復数・JSON/ツールの項目一致・根拠付き品質点を対応ペアで比較する。保存済みの現行版と簡潔化候補の各12会話・28返答を再集計済み。超過2件は6文字→0、8文字→0と改善量が見える。この比較の品質レビューは未入力。完走率は会話品質の満点を示さない。

段階4の限定プローブとして失敗回復4課題・12往復雑談2課題を追加。未編集Qwenで各1回・計42返答を測定し、通常雑談の同一質問再出現1ターン、終了要求後の旧話題継続1ターンを確認した。後者はCodexの非盲検レビューで判定。利用者報告の「何を話しても原木用途へ戻る」強い固着は未再現。当日午前1時前後の本番・開発ログは取得できず、実ホストの記憶・要約・状態の再提示を含む再現が残る。[条件と証拠](weight-space-results-ja.md#未編集qwenの質問反復話題固着)。評価器42テスト成功。段階4の全負荷点・holdout、段階5、logit補助観測は未実施。

利用者提供の配信をChromeで開き、4:30〜10:30と46:00〜48:30の動画音声だけを取得してローカルWhisperで文字起こしした。ASR草稿上では、用途回答・整地への変更依頼・ゾンビ撃退への称賛の後に、原木10個の採集宣言と拠点質問が再登場する。既存の「作業終了・保留なし」という合成条件との差を整理済み。原音の人手校正、元STT・内部状態、同じ症状のモデル単体再現は未完了。[配信音声からの再現条件](weight-space-results-ja.md#配信音声で確認した再現条件)を参照する。

配信由来の`stream-replay-suite.json`を追加し、未編集Qwenでdev4課題・15返答を完走。根拠付きの探索レビューで、不要な再質問・旧質問への復帰4返答、旧採集計画の不要な再出現2返答を検出した。取消済み条件で、称賛への返答後に採集へ戻る例を確認。4種類の旧説明の再出現を別々に採点し、該当返答は固着の少なさ3.75/5。長い説明全体の反復、独立レビュー・holdout・反復測定は未確認。[測定条件と基準値](weight-space-results-ja.md#配信由来ベンチマークでの現在モデルの測定)。採点器45テスト成功。本番モデル・promptは変更していない。

### 量子化35Bの重み直接編集

過去の質問の文面・形式・話者を切り分け、未編集35Bで通常返答126件と話者読解36件、計162要求を完走。不要質問は基準6/12、同義置換4/12、疑問符→句点6/12、過去の記録文6/12。元履歴の話者・宛先・時点は14/14全正答だが、反実仮想で話者を入れ替えた履歴では全正答2/12に低下した。話者ラベルごとのコピーも観測。単純な文字列複写・疑問符・常時の話者識別不能だけでは説明できず、過去の質問内容を現在の発話候補へ再利用する仮説を優先する。[条件・曖昧な課題の除外・限界](weight-space-results-ja.md#過去の質問の文面形式話者の比較)。内部活性・学習履歴は未確認、通常設定は未変更。

入力要因の原因調査として、未編集35Bで9文脈・8条件・2反復＝144要求を完走した。過去assistantの質問文を除くと対象12返答の不要質問は6→2、自己設定の圧縮では8、失敗通知の未実行表現への置換では6。疑わしい性格設定の削除は質問減少と引き換えに不要な採集開始宣言2件を生じた。履歴の質問の再生成が有力な調査対象だが、長い能力説明への置換・残る反復もあり、通常設定へは採用していない。[条件・対照・限界](weight-space-results-ja.md#反復を引き起こす入力要因の比較)。内部活性・原因層は未特定。関連テスト52件成功。

会話状態の切り分けとして、未編集共有GPUで9文脈・5条件・2反復の90要求と、人格を外した追加読解36要求を完走した。通常返答の不要質問は6/12、正しい状態の補足後も4/12。追加読解で全5項目に正答する文脈でも通常返答で準備質問を再提示する4件を確認した一方、判定自体の誤りも残る。理解と返答選択の双方を次の改善対象とし、内部機序や本番入力の原因は未確定。[条件・採点・限界](weight-space-results-ja.md#会話状態の判定と返答選択の検証)。関連テスト50件成功。重み・通常prompt・本番アプリは変更していない。

現行Qwen35B GGUFの別コピーでEOS出力行のQ6_Kスケールを1.05倍にする試験を実施。変更8byte・対象外一致を確認し、同一の専用CPU条件で未編集と候補の7課題を比較。両版完走7/7、自動check6/7で、本文・ツール操作は同一。改善がなく候補は不採用。専用コンテナを終了し、通常共有モデルの稼働継続を確認した。[条件・証拠・未確認範囲](weight-space-results-ja.md#量子化35bのeos重み編集)。

35Bの中間6層・192個の減衰biasを編集した2候補と、EOS1.10倍の1候補を同一CPU環境で追加比較した。弱い減衰は3反復で合計文字数25.3%減・目安超過9→0だが、不要な再質問は双方6/39対象返答。強い減衰は反復件数が減る一方で長文化・内容の誤り、EOS1.10は再質問が残る。改善と非劣化の両立は未達で通常モデル・promptを維持。[実測と採点根拠](weight-space-results-ja.md#量子化35bの減衰と終了重みの比較)。CPU基準では旧採集計画再開が出ず、GPUの基準値とは直接比較していない。

弱い減衰候補と未編集の保護評価は各44課題を完走し、自動checkは双方38/44・新規自動失敗0。ただし共感返答が103→249文字に長くなり、曜日訂正会話の同じ質問の再提示が1→2回へ増えた。意味の改善と退行を分けて記録し、採用ゲート未達でholdoutは未実施。全8run完了、専用コンテナ残存0、通常共有GPUの同じgenerationでの稼働継続を確認した。関連テスト47件成功。独立人手・実音声・画像・実Minecraftの非劣化は未確認。

### 段階1〜3の会話ベンチマーク

現行Qwenと簡潔化prompt候補でdev各12会話・28返答を測定し両版完走。中央値68→47文字、目安超過2→0件。ただし候補は提案の欠落があり採用見送り。条件は[実測](weight-space-results-ja.md#段階13の会話測定)。人手採点、holdout、実ホスト・音声、重み編集は未実施。

24課題（dev12・holdout12）と、実際に生成した応答を履歴へ戻す会話実行・ターン別の長さと完全一致反復の記録・人手レビュー出力を追加。仕様と実行方法は[重み編集ベンチマーク](weight-space-benchmark-ja.md#段階13の会話課題)。意味の反復に対する人手採点、音声経路での検証は未実施。

### Minecraftの衝突幅補正

2026-11-11、修正を`5d2eb54`にコミットし、開発・本番の身体へ反映した。対象は`skills.js`での初期化呼び出しと新規`player-physics.js`だけ。本番の既存の施工・製作実装を維持し、開発の段階1改修全体は本番へ持ち込んでいない。imageは開発`6a292d253e99eef4acc55b8057e4a435de73c90c61a05be7c4358926d11d47e1`、本番`5024b0dfe2d023031d7b999b4f9712aef46c5fd8a871e5c5df34b8908c7d598f`。各配置先と実コンテナの全ソース（開発33・本番32ファイル）が一致し、他の全サービスのID・image・起動時刻は不変。両方の入場と、実行中の本番`Ciel`の物理更新・半幅`0.30000001192092896`を読取確認した。デバッガーは終了後に閉鎖済み。

配布根拠は両環境の`server/data/deployments/collision-5d2eb54/verification.json`・`before.json`・`after.json`・`sources-before.json`、旧skillsは`skills-before.js`。現場の`Ciel_Debug`比較では段差の座標巻き戻しが371回から0回となり、歩行目標へ到達した。Node130件成功・既存1件skip、配布した両コンテナでも衝突回帰4件ずつ成功。[条件と未確認範囲](minecraft-results-ja.md#段差での座標巻き戻し)を参照。利用者から開発`Ciel_Dev`の到着とスキン適用の報告を受けた。本番での実音声の接近・原木採集は未確認。

`Ciel_Dev`だけが応答した件は、配信アプリの保存値`ciel.devServer=1`と開発agentへの命令到達を確認した。配信アプリを正常終了してこの設定だけを`0`へ戻し、再起動した。新しい会話を本番agentが受け持つことと、アプリの「ゲーム：入っている」を確認済み。本番agentは8771の`Ciel`、開発agentは8775の`Ciel_Dev`という分離を維持する。アプリはマイクOFFで再起動した。

### 返答生成の役目別OpenAI切替

2026-11-11、実装`ad04a29`の`models.py`・`voice_preparation.py`だけを開発・本番へ選択して反映した。起動中とホストの他ソースを照合してから対象agentのみをビルド・再作成し、各段階で他の9サービスのID・image・起動時刻不変を確認した。Minecraft本体・本番と開発の体・知識・共有LLM・TTS・DB・歌の再配布は行っていない。リポジトリ全体や他のserverファイルまで同じコミットへ配布したという意味ではない。

開発でmindだけOpenAIへ切り替える実設定を確認したが、短文の実API疎通はHTTP 429・`credit_balance_exhausted`で失敗した。開発設定を元へ復元して再作成し、両環境はmind・thoughtともローカル、開発Whisper・本番Vosk、worker登録・HTTP 200を確認した。本番のAPI切替は有効にしていない。残高追加後の速度・品質比較が残る。

2ファイルの実イメージ内SHA-256は、modelsが`35231702fcefb5bc8e219b8881cc3553f8a94841b73d7887381d0c4797654f5f`、voice_preparationが`fdb132498c0d0fcbbf883d61fb44943bcb9f1f30e22e816213ab27f9eaedc97b`で実装コミットと一致。開発imageは`07c7621aa5026af15fb97f0be444e85f67c65aed224fe338dfed2696dea1ea4b`、本番imageは`d4dfc3ef4faacf838fc8dd400e676e71502a68ff6a3cb493a09c293fb76eed8f`。通常回帰797件・隔離DB9件成功。条件・復旧・証拠は[音声の実測](voice-results-ja.md#openai部分切替の疎通と復旧)、操作は[役目別切替](../operations/local-runtime-ja.md#待ち時間の大きい役目だけopenaiへ送る)を参照する。

| 対象 | 直近の根拠 | 残る確認 |
|---|---|---|
| ドキュメント整合性 | 2026-11-11、文書一覧・責務・ローカルリンク検査と検証器の自己テスト6項目に成功。実測の根拠は分野別の資料を参照 | 外部URLの到達性は対象外 |
| 会話ホストの通常回帰 | 段階1の最終固定版でunit795件・使い捨てDB結合9件が同じ実行で全合格（`server/benchmark/data/stage1-final-draft-acceptance-regression/report.json`）。オフラインMCP結合成功、Node126件合格・既存1件skip（`stage1-node-obtain-interpretation.log`） | 実アプリ端末・人のマイク・継続負荷。途中のDocker起動失敗も保存し、成功した再実行と区別する |
| 本番・開発のbackend | 本番は`eec8d6d`配布を維持。開発は段階1の未コミット固定版へ更新し、282ファイルと実コンテナの一致、LiveKit worker登録、MCP読取疎通、pipeline/local/voice/Whisper設定を確認。本番8サービスのID・image・起動時刻を維持 | 最終開発版での人のマイク、実アプリの表情・発話・割り込み、継続負荷 |
| 能力カタログ・サービス分離・反応 | unitとpipelineを通す各結合スクリプトの導入確認。現行の通常回帰に含む | 実モデルの選択精度、実機の表情・発話遅延と同時入力 |
| Unity作業表示 | 実ソースを使う.NET検証35項目、C#本体・Editorビルド成功。Editorで状態表示11・カード57・構成42項目成功 | 現行Playerの実サービス接続、全画面・実機の品質 |
| ローカル画像API | 常設APIに256px前処理とCPU画像エンコーダーを反映。本番・開発で画像能力を確認し、開発側で1024px画像添付→認識返答→音声受信、説明文生成まで成功。[画像の実測](vision-results-ja.md)を参照 | 写真・OCR・実ゲームの品質、Unity端末の画像選択UI、連続入力・同時会話の負荷 |
| ローカルSTT | 同一合成コーパス各30試行でVosk小型・大型とCPU Whisperを比較。WhisperのCER3.3%、呼びかけと一般語を区別。[音声の実測](voice-results-ja.md)を参照 | 人のマイク、雑音、小声、未使用の発話・固有名詞 |
| 音声会話ベンチマーク | 会話一本化・背景制御・実ツール付き準備を専用workerで実測。長い合成入力は基準30.686秒→最終候補3.091秒（各1回）。短い挨拶・途中候補・認識誤りは[音声の実測](voice-results-ja.md)に記録 | 専用workerの性能を通常版で再測定していない。人の録音、本人認証、継続会話、同時負荷、能力追加時の遅延 |
| WSP評価環境・改善候補 | 通常promptを維持。量子化GGUFのEOS・減衰bias編集を実行し、短文化と反復・内容退行を別評価。採用条件は未達。[人格の実測](weight-space-results-ja.md)を参照 | 改善モデルの採用、holdout・未使用系列、独立した人格の人手評価、実音声・実MCP・実機の比較 |
| Minecraft | 受付の改修前後を代表6課題で比較。ダミー0個は3/6→6/6、100個は1/6→6/6。配置11・各1回、共有GPU。`5af980b`を本番・開発へ配布し、ソース一致と会話疎通を確認。追加の施工課題は次の行を参照 | 施工追加後の全集合での反復、言い換え・否定・質問の実モデル評価、人の音声・自然地形は未確認 |
| Minecraftの方向探索 | `0f9149c`で本番の体へ初回反映し、`30951b8`から体を再構築して再入場を確認。専用実機で256ブロック先のチャンク情報、384ブロック先の角度だけからの接近・停止を確認 | 改修した受付からの遠距離探索は未測定。通常ワールドの自然地形、見失いからの復帰の実機反復 |
| Minecraftの指示棒・目線・対象候補 | `eec8d6d`を本番・開発の会話と共用の体へ配布。通常ワールドをバックアップしてPaperへ移行し、プラグイン・MCP定義・体の再接続・seed保持を確認。専用評価は会話7/8→8/8、最終補強後3/3、受付8入力5/8→8/8。[対象候補の実測](minecraft-results-ja.md#対象候補の固定と正確な座標の受け渡し)を参照 | 通常ワールドでの実クリック・人の音声と目線、聞き返し文と後続経路、同じ軸を複数指定する座標文 |
| Minecraftの整地・建築 | 最大64マスの除去・床・壁を`5445a62`に実装・コミットし、`30951b8`から通常の体へ配布。施工body8/8、会話6/8→7/8。既存の採集・接近・追従も会話3/3。配布前の実測でunit737件成功、今回のNode102成功・既存1件skip。通常ワールドの施工は未確認 | 条件付き整地依頼のZ上限を誤解する1件が残る。自然地形・大規模施工・実音声・反復・未使用寸法は未測定 |
| Minecraft段階1の施工改修 | prepare→work、全域事前検査、埋め戻し、停止後継続、確認草案を実装し、最終固定版を開発`Ciel_Dev`へ反映。G1受付16/48→48/48（新k群24/24）、G2 body26/42→42/42、文字22/42→42/42。各モードの改修版は目的達成27・適切な停止15、施工監査の範囲外変更0。監査故障注入3/3。再利用の条件・出典・失敗は[実測](minecraft-results-ja.md#段階1の施工改修と開発測定)を参照 | 報告レビュー・G3実マイク・実指示棒・音声停止は未完了。機械判定で段階1完了とはしない。本番の体は従来版 |
| キャラクター | current/rig/runtimeの正式manifest・確認図、Unity更新検証 | 配布モデルで明記した衣服・大きな腕の補正等、端末ごとの負荷 |

生データの多くはGit対象外。文書やハッシュをコミットしただけでは保存したことにならない。表のテスト件数を新しい実行なしに増やしたり、以前の小さい件数を各仕様書へ残したりしない。

### 2026-11-11の配布確認

commit `30951b8`を標準`deploy-server.sh --dev`、続いて`deploy-server.sh`で開発・本番の会話サーバーへ配布した。開発側の作業前DBバックアップはサーバーの`~/work/ciel-db-backups/ciel-20261111-073620.sql.gz`。任意profileの共有LLMとMinecraftの体・知識サービスはComposeで個別に再構築し、MinecraftサーバーとDBは再作成せず維持した。両会話workerはLiveKitへ再登録し、Minecraftの体は再入場、知識サービスはMCP入口の起動を記録した。全対象コンテナはrunning、再起動回数0。共有LLMはhealthy、`/health`はok、`/mode`はGPU ready、32,768トークン・2枠・ubatch512・`cache_ram_mib=8192`・`checkpoint_step=8192`。主要ソースのSHA-256は手元と本番・開発の配置先で一致した。新イメージは本番agent `sha256:90024dc9d528`、開発agent `sha256:c64795983ec0`、共有LLM `sha256:e10aeca668700`、Minecraftの体・知識 `sha256:cb3a94a007d08`。一時LiveKitルームで両環境とも`voice.ready`、挨拶音声、文字入力への返答音声を確認した。文字送信から返答音声受信は開発2.233秒、本番2.220秒の各1回。疎通確認の値であり、音声入力や20〜30秒の遅延の改善率には読み替えない。人のマイクや通常ワールドでの施工、連続会話の速度は未測定。

方向探索の単体結果は`server/minecraft/data/player-locator-tests.txt`、配布確認はGit対象外`server/minecraft/data/deploy-locator-0f9149c/verification.json`。サーバー側の`~/work/ciel-companion/server/data/deployments/locator-0f9149c/`へ旧ソース・配布前後の状態・確認結果を保存し、旧イメージは`ciel-minecraft-body:before-locator-0f9149c`で保持した。配布後の体のイメージは`sha256:8c5e37f4f50fefd370790c6be98a72464942efddac7e6bcc1689736c95d0ddf4`。

## 対象候補と指示棒の本番・開発への反映

2026-11-11、実装コミット`eec8d6d4e604ff8843f37b4d5e92ff1a6d0a0d7f`を本番・開発へ配布した。両agent内の`game_intake.py`・`target_candidates.py`・受付promptがGitの内容と一致することを確認。本番imageは`e2e00929b20fa0a54e13c13825c0bb48af13344c8d5765a06c4a4eab5eb7a300`、開発は`42d264ab5357c019b060790f148f84f0fb67611f002ae64b5c86b5352981ab2c`。両方の一時LiveKitルームで準備完了・挨拶音声・文字入力→返答音声に成功した。人のマイクを通した性能試験ではない。

共用Minecraftは停止・保存後のバックアップを取り、`compose.yaml`と`compose.pointing.yaml`でPaper `1.21.11-132-c5eb079`へ移行した。既存ワールドのseed保持と体の参加、正常healthを確認。Paper imageは`d9a5a6eb0be70e94978051352649cb76b859f75518556b88f1a820e99ce2e708`、体は`a3fd9f0bcfa556316392b6f43708bafb656a162740dc0905fb20ff0733136068`。プラグインSHA-256は専用評価と同じ`b27992f9ad136d16d3e2f04765466b636bb8f704fb426df9c60f99bb13375dfe`。本番MCPのprofile 2・4操作の対象対応定義・選択ファイルversion 1も確認した。実クリックやゲーム作業を通常ワールドで自動実行した確認ではない。

バックアップと前後状態・疎通結果はサーバーの`~/work/ciel-companion/server/data/deployments/target-candidates-20261111T011825Z/`。DBは`database.sql.gz`、ワールドは`minecraft-before-paper.tar.gz`、指紋は`world-backup.json`。共有GPU APIは再作成せず、generation `b668da4b0f25403ea308cb9b63ba3dee`を維持した。Minecraft更新時は[Paper用の両Compose指定](../operations/local-runtime-ja.md#Minecraftの指差し機能を導入する構成)を使う。

## 段階1の開発用Minecraftへの先行反映

利用者から開発への随時デプロイを許可され、`deploy-server.sh --dev --minecraft`を追加した。開発agentは専用body/MCPへ接続し、共用の通常Paperワールドには`Ciel_Dev`として参加する。MCPは8775、bodyは8774、eyeは3009のループバック。開発の設定・DBを退避し、既存whitelistを保持してCiel_Devを追加した。通常ワールドの初期化や本番の体の更新は行っていない。

初回配布ではagent/Minecraftソース320ファイルの指紋一致、prepareを伴う`minecraft.edit_region`と`minecraft.obtain_item`の公開、既存本番8サービスのコンテナID・イメージ・起動時刻の維持を確認した。サーバーの`~/work/ciel-companion-dev/server/data/deployments/minecraft-stage1-1794367996389552605/`に前後状態・ソース照合・検証結果を保持する。`20261111-123515`と`20261111-131130`は当時の開発版の配布記録。

受付の高さラベル・軸名併記・肯定依頼制約を含む先行版は`20261111-144948`に反映し、278ファイルの一致を確認した。証跡は`minecraft-stage1-final-1794376176061440500/`と、回収先`server/benchmark/data/stage1-dev-deployment-final/`に保持する。

最終固定版は`20261111-201955`に`deploy-server.sh --dev --minecraft`で反映した。agent/Minecraftのpy・js・json・md・tomlの282ファイル、agentの主要ソース・3種類の受付指示、体の全srcの実コンテナ内指紋を照合。実際のpersonaローダーが読み込む指示も一致し、MCPのprofile 2/work 1・prepare・高さラベル・旧clear/build撤去、開発接続先8775、持ち主設定、Ciel_Devの参加とLiveKit worker登録を確認した。実行設定はpipeline/local/voice/Whisper。開発agent imageは`185beda81de394690699faccfe5214269872fd424c5061ef846851e10b700c3d`、bodyは`4d75d0abd8e1d9761f624105d4dc171867fa0a0671a018a2a0f4c6e9a83bc575`。本番8サービスのID・image・起動時刻を維持し、通常10サービスが稼働した。

最終証跡は`~/work/ciel-companion-dev/server/data/deployments/minecraft-stage1-final-1794395358159843124/`のbefore/after/source-files/verification JSON、回収先は`server/benchmark/data/stage1-dev-final-verification/`。DBバックアップは`~/work/ciel-db-backups/ciel-20261111-201955.sql.gz`。資格情報・DB・ワールドは回収していない。これは配布・登録・読取疎通の確認であり、通常ワールドの施工や実マイクの合格記録ではない。

実マイク・指示棒・音声停止の確認はまだ行っていない。利用者は準備が整ったら手順の案内を希望しており、[G3の操作手順](../games/minecraft/minecraft-benchmark-ja.md#g3の操作手順)を案内する。開発反映だけで段階1完了とはしない。

## 本番・開発のローカル推論への反映

自宅サーバーの本番`~/work/ciel-companion/server`と開発`~/work/ciel-companion-dev/server`で、共有`.env.shared`と独立した`.env`・`.env.dev`を使用する。両環境とも`CIEL_LLM_BACKEND=local`、pipeline・voice、GPU解放制御8095を設定する。STTは本番CPU Vosk・開発CPU Whisper、記憶スコープは本番main・開発dev。旧`CIEL_DEV_*`は使わない。資格情報・Webhookを保持し、設定ファイルの権限は0600。

2026-11-10の配布時には本番・開発agentへ`45c8d73`のserverソースを反映した。当時のイメージと配布後確認は[併用方式の実測](capability-results-ja.md#本番開発への反映)を参照する。その時点の共有APIイメージは`sha256:42e2f4875762c8c44087f0758c922071f74eb0936649da37d37afd44a00d9610`で、GPU・32k×2枠・health正常、画像上限256pxを維持した。この配布時には共有APIコンテナを再作成していない。後続の[画像の実測](vision-results-ja.md#常設画像apiの256px前処理)と混同しない。

2026-11-10、利用者の共有API更新・短時間再起動への承認後、共有APIだけを再作成した。イメージは`sha256:40751d8718106ce5f0b67c27a972c245871c5ad6aa22ea31d0c71ad4b36c5b8d`。`generation_scope=inference_process`と世代識別、分類なし/foreground/backgroundの短い生成要求の200、入場待ちヘッダー、不正分類の400を実機で確認した。この共有API更新時には残る8サービスを維持した。後続の本番デプロイで会話worker側の準備処理・分類付与・文分割も反映した。開発workerは旧版で、未分類の要求は前景として扱う。通常会話の高速化は実際の音声計測で別に確認する。

反映と復帰確認の根拠はサーバー`~/work/ciel-companion/server/local-llm/data/shared-gpu-20261110T041641Z/`の`configuration.json`・`rollout-verification.json`。回収先は`server/benchmark/data/shared-api-import-1794284236239377600/data/shared-gpu-20261110T041641Z/`。秘密を含む復旧用backupはサーバーに保持し回収しない。今回の短文3要求は疎通確認で、音声ベンチマークの再測定ではない。

同日の利用者のコミット・デプロイ依頼により、`61ac247`を`deploy-server.sh`で本番へ配置した。Git管理のserver354ファイルの作業ツリーとの指紋一致、workerのLiveKit登録、起動ログのTracebackなし、再起動回数0を確認。標準Compose処理でagentとsingingを再作成し、共有LLM・TTS・DB・Minecraft3サービス・開発agentの7コンテナはID・イメージ・起動時刻を維持した。不採用のプロンプト候補は評価用ディレクトリのみで、通常promptとLLM重みは基準を維持する。

デプロイ前後の状態とソース照合はGit対象外`server/benchmark/data/deploy-wsp-preflight/before.json`・`after.json`。復旧用の旧agentソースとDBはサーバー`~/work/ciel-companion/server/data/deployments/61ac247-20261110T055626Z/`内に権限制限して保持する。初回の起動処理は既存スクリプトのCRLFにより停止したが、`.gitattributes`指定のLFへ作業ツリーを修復し、再実行の`DEPLOY_SERVER_DONE`を確認した。

本番workerに一時LiveKitルームを作り、voice.ready、初回挨拶の文字/音声、文字入力後の応答文字/音声受信を確認した。最初の数字37指定では期待する文字列が60秒以内に確認できず（`smoke.json`）、次の挨拶による疎通試験は応答84文字と音声受信で成功（`smoke-greeting.json`）。音声は保存せず、各ルームは削除済み。準備通知は初回13.49秒、次回3.12秒で、キャッシュや共有負荷を揃えていない単発値のため速度改善率にはしない。人格指紋は`19fc8c7672656f6bc76040ee338924bf5b2773fdc29d1d03741164761a3f55c7`、LLM世代は前後同じ`5c3ff24d8e4543b68a36b40576fb05a9`。人のマイク・実アプリ・STT精度の検証は含まない。

## 配信アプリのマイク再接続

2026-11-11、作業ツリーの`CielConversation.cs`を修正した。切断時に`_busy / _micRestarting`を解除してマイク操作のcoroutineを停止し、旧接続の録音開始・公開完了・機器切替が新しい接続を変更しないよう世代とルームを照合する。録音・公開に失敗した場合は音源とトラックを破棄して再試行可能にし、予期しない切断は接続済み表示を残さない。SDKの接続完了前はDisconnectが無効になるため、遅延完了した旧ルームも個別に閉じる。

Unity 6000.6.4f1で`CielMicrophoneReconnectCheck.Run`の10検証が成功。公開待ち状態での切断、旧機器切替の遅延再開、旧ルームの切断通知、音声機器がない状態での録音フラグ解除、接続中のマイク操作拒否、繰り返しの終了を、実マイク・LiveKitを開かずに確認した。既存の`CielAppCompositionCheck`42件も成功し、正式出力`unity/Builds/Broadcast/CIEL Broadcast.exe`を再ビルド（284MB、42秒）した。

起動中の同じ配信アプリを通常終了する前に、旧ビルドをGit対象外`.local/mic-reconnect-build-before/`へ退避した。修正版を元の場所から再起動し、マイクOFFでのルーム接続と、NullReference/ObjectDisposed/InvalidOperation等の起動例外およびマイク初期化エラー0件をPlayer.logで確認した。ユーザー設定の変更、マイクON、配信・録画開始、サーバー再配布は行っていない。

証拠はGit対象外`unity/Logs/mic-reconnect-check.log`（10件）、`unity/Logs/mic-reconnect-build.log`（42件・CIEL_BUILD_OK）。Playerの`Assembly-CSharp.dll` SHA-256は`00ce02bc7eddbf2566f4ab995e5ac6ad03662315e0e8ed764e810ab7653643e8`。実マイクを使った連続再接続と相手への入力到達、Androidでの権限待ち、日常版の再ビルドは未実施。仕組みと再確認方法は[アプリ構成](../app/app-composition-ja.md#会話の再接続とマイク)を参照する。

## Unityの描画

初回の制限環境ではEditorがライセンスエラー198となった。通常権限ではUnity Personalが有効・サインイン済み、Editor 6000.6.4f1を認識し、再実行で成功した。MCP登録やライセンスの変更は行っていない。`server/benchmark/data/work-display-unity-retry.log`と`work-display-unity-render.log`、`.local/app-refactor/audience-card-{work,decision,unknown}-v2.png`を確認した。

900×500の実行中・判断待ち・状態不明を目視し、会話専用行、予算、文字の収まりを確認した。本番配布やPlayerの実サービス接続試験とは区別する。ソースのみの検証器はUnityのJsonUtility・描画の代用ではない。

## 共有LLM APIの容量

32,768トークン/要求・2枠のGPU併用で、約29.4k入力×2要求まで応答した。API容量試験のGPU使用量ピーク10,748MiB、空き最小1,188MiB。大きい入力では約14.2kトークンのキャッシュがあり、最大32トークンの短いOKを生成した試験。長い道具選択の品質、持続生成速度、最大可能容量を確認したことにはならない。

本番コンテナから共有APIへ接続できることも確認したが、並行するMinecraft要求により短文も約42秒待った。低遅延を保証しない。保存先は`server/benchmark/data/shared-api-import-1794223022247818000/`、サーバー`~/work/ciel-companion/server/local-llm/data/`。現在の構成と再実行方法は[共有API](../operations/shared-llm-api-ja.md)が正本。

## 更新のしかた

新しい確認で該当行・条件・参照先を置き換える。以前の詳細はGit履歴で追えるようにし、日付付きの報告書を増やさない。未実施は未実施のまま残し、ソース変更・コンパイル・実モデル・実機・配布・本番稼働を別々に示す。
