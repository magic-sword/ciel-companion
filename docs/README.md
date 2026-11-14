# 現在のドキュメント

> 責務：全資料の索引と各ファイルの責務。仕様・手順・結果の本文は複製しない。

この一覧から目的に合う正本を選ぶ。過去の仕様・改修履歴はGitから参照し、[管理ルール](project/documentation-policy-ja.md)に従って既存の正本を更新する。

## 読む順番

設計変更は[設計方針](project/design-policy-ja.md)と対象の契約から、導入は[開発環境](development/development-setup-ja.md)から始める。本番・開発の切替は[実行設定](operations/local-runtime-ja.md)、性能評価の全体像は[ベンチマーク案内](testing/benchmark-guide-ja.md)、条件と生データはカテゴリ別の実測資料、現在の配布範囲は[確認状況](testing/verification-status-ja.md)を参照する。文書を整理・追加するときは[共有スキル](../.claude/skills/ciel-documentation/SKILL.md)を使う。

## フォルダの担当範囲

ファイルは情報を所有する分野へ置く。関連するだけの別フォルダには複製せず、リンクを置く。MinecraftとLive2Dの固有仕様は、それぞれ共通契約の下のサブフォルダへ分ける。`docs/`直下にはこの索引だけを置く。

| フォルダ | 担当範囲 |
|---|---|
| `project/` | 文書管理、設計判断、全体構成、依存と利用許諾。 |
| `development/` | 開発環境の準備、SDK復元、ビルド・配置操作。 |
| `operations/` | 本番・開発の推論設定、共用LLM APIの運用。 |
| `testing/` | 回帰・有料試験の方法と、現在の測定根拠・未確認範囲。 |
| `conversation/` | 会話の流れ、プロンプト、能力公開、サービス境界、入力イベント、失敗の扱い。 |
| `services/` | 音声認識、記憶、会議、Web、歌、コメント、画像の契約と利用手順。 |
| `games/` | 環境MCP、work、体の命令の共通契約。 |
| `games/minecraft/` | Minecraft固有の実装とベンチマーク。 |
| `app/` | アプリ構成、作業表示、タッチ操作。 |
| `app/live2d/` | キャラクター制作仕様、リグ、参考モデルの分析。 |
| `publishing/` | 撮影台本と紹介映像の制作手順。 |
| `assets/showcase/` | READMEに掲載する実画像と差し替え手順。 |

## 索引

| 資料 | このファイルが所有する内容 |
|---|---|
| [README.md](README.md) | 全資料の索引と各ファイルの責務。仕様・手順・結果の本文は複製しない。 |

## 全体方針と文書管理

| 資料 | このファイルが所有する内容 |
|---|---|
| [project/documentation-policy-ja.md](project/documentation-policy-ja.md) | 資料の所有範囲、更新・統合・削除、リンク検証の管理ルール。 |
| [project/design-policy-ja.md](project/design-policy-ja.md) | 責任分担と採用する設計判断。詳細スキーマ・コマンド・測定値は各正本へ委ねる。 |
| [project/architecture-ja.md](project/architecture-ja.md) | プロセス・配置・接続・共有範囲の地図。 |
| [project/third-party-dependencies.md](project/third-party-dependencies.md) | SDK・モデル・素材の依存と利用許諾、リポジトリへ含める範囲。 |

## 開発環境とビルド

| 資料 | このファイルが所有する内容 |
|---|---|
| [development/development-setup-ja.md](development/development-setup-ja.md) | クローン後の依存復元、SDK導入、最初の表示・開発環境の準備。 |
| [development/build-ja.md](development/build-ja.md) | アプリのビルド、配置、更新、ログ取得の操作。 |
| [development/sdk-setup-ja.md](development/sdk-setup-ja.md) | 固定SDKの復元・互換修正・パッケージ確認。 |

## 推論の運用

| 資料 | このファイルが所有する内容 |
|---|---|
| [operations/local-runtime-ja.md](operations/local-runtime-ja.md) | 本番・開発の推論設定、設定ファイルの優先順位、切替・反映単位。 |
| [operations/shared-llm-api-ja.md](operations/shared-llm-api-ja.md) | 共用LLM APIの接続・容量設定・GPU/CPU制御と測定方法。 |

## テストと確認状況

| 資料 | このファイルが所有する内容 |
|---|---|
| [testing/regression-tests-ja.md](testing/regression-tests-ja.md) | 変更に応じたテストの選び方、コマンド、終了コード。 |
| [testing/benchmark-guide-ja.md](testing/benchmark-guide-ja.md) | 分野ごとの課題・合格条件・採用した改善と結果・残課題を見渡す入口。 |
| [testing/voice-benchmark-ja.md](testing/voice-benchmark-ja.md) | 音声認識精度と応答時間の評価根拠、録音コーパス、再生・集計・比較の方法。 |
| [testing/weight-space-benchmark-ja.md](testing/weight-space-benchmark-ja.md) | 人格・身体性・ツール・一般性能を比較する課題、採点、実行条件、音声・実機評価への接続。 |
| [operations/weight-space-programming-ja.md](operations/weight-space-programming-ja.md) | 重み直接編集の研究根拠、現行モデルへの適用判断、実験・量子化・復元の進め方。 |
| [testing/paid-checks-ja.md](testing/paid-checks-ja.md) | 外部APIを呼ぶ試験、費用と実行範囲の確認方法。 |
| [testing/verification-status-ja.md](testing/verification-status-ja.md) | 現在の機能確認・配布状況と、カテゴリ別の実測資料への索引。 |
| [testing/minecraft-results-ja.md](testing/minecraft-results-ja.md) | Minecraftの行動・依頼受付・対象指定の実測条件、結果、残課題、生データ。 |
| [testing/voice-results-ja.md](testing/voice-results-ja.md) | 音声認識・本返答の速度の実測条件、改善結果、残課題、生データ。 |
| [testing/capability-results-ja.md](testing/capability-results-ja.md) | 能力追加・公開方式・キャッシュの比較条件、改善結果、残課題、生データ。 |
| [testing/weight-space-results-ja.md](testing/weight-space-results-ja.md) | 人格・身体表現の指示候補の採点条件、採用判断、残課題、生データ。 |
| [testing/vision-results-ja.md](testing/vision-results-ja.md) | 画像API・会話添付の実測条件、改善結果、残課題、生データ。 |

## 会話と実行基盤

| 資料 | このファイルが所有する内容 |
|---|---|
| [conversation/conversation-pipeline-ja.md](conversation/conversation-pipeline-ja.md) | 入力から返答までの実行順、共通履歴、経路選択、発話の調停。 |
| [conversation/prompt-management-ja.md](conversation/prompt-management-ja.md) | Markdown/TOMLの指示管理、ロード・指紋・編集・評価の契約。 |
| [conversation/capability-runtime-ja.md](conversation/capability-runtime-ja.md) | 能力カタログ、段階的な公開、呼び出し権限と実行管理。 |
| [conversation/service-boundaries-ja.md](conversation/service-boundaries-ja.md) | 各サービスと会話ホスト、公開操作と基盤専用操作の分担。 |
| [conversation/service-events-and-reactions-ja.md](conversation/service-events-and-reactions-ja.md) | 非同期入力の契約、TTL・優先・集約・発話/表情の調停。 |
| [conversation/errors-design-ja.md](conversation/errors-design-ja.md) | 失敗の分類、利用者へ見せる通知、正常状態へ変換しない規則。 |

## 個別サービス

| 資料 | このファイルが所有する内容 |
|---|---|
| [services/local-stt-ja.md](services/local-stt-ja.md) | CPU音声認識のアダプター、途中/確定結果、モデル配置と評価方法。 |
| [services/shared-memory-ja.md](services/shared-memory-ja.md) | 本人確認・保存同意・DBスコープ、共有記憶と競合・忘却の実装契約。 |
| [services/people-memory-ja.md](services/people-memory-ja.md) | 利用者による人物・声・メモの登録、訂正、参照、削除の操作。 |
| [services/meeting-minutes-ja.md](services/meeting-minutes-ja.md) | 議事録の受付、対象範囲、ライブ・清書・送信・保存の契約。 |
| [services/meeting-bridge-ja.md](services/meeting-bridge-ja.md) | 会議へ参加する端末の音声・映像設定と利用手順。 |
| [services/web-research-ja.md](services/web-research-ja.md) | Web調査の依頼、引用確認、結果保持、画面と発話への対応。 |
| [services/singing-scoring-ja.md](services/singing-scoring-ja.md) | 歌の解析モデル、主観評価・途中反応・音声保持・GPUの扱い。 |
| [services/youtube-comments-design-ja.md](services/youtube-comments-design-ja.md) | 配信コメントの取得・選別・権限・会話への入力。 |
| [services/vision-design-ja.md](services/vision-design-ja.md) | 画像の受信・保持・参照ID・理解と利用不可の扱い。 |

## ゲーム共通

| 資料 | このファイルが所有する内容 |
|---|---|
| [games/game-environment-mcp-design-ja.md](games/game-environment-mcp-design-ja.md) | 環境を追加するためのMCP接続・profile・観測・所有権・通知。 |
| [games/game-work-contract-ja.md](games/game-work-contract-ja.md) | ゲーム非依存の依頼・予算・判断・取消・work状態の契約。 |
| [games/body-command-lifecycle-ja.md](games/body-command-lifecycle-ja.md) | 低水準の体の命令、世代・切替・後片付け・停止確認。 |

## Minecraft

| 資料 | このファイルが所有する内容 |
|---|---|
| [games/minecraft/minecraft-design-ja.md](games/minecraft/minecraft-design-ja.md) | Minecraft固有の体・計画・知識・視覚と接続先・変更入口。 |
| [games/minecraft/mindcraft-agent-loop-ja.md](games/minecraft/mindcraft-agent-loop-ja.md) | 固定版Mindcraftのモデル通信、観測・履歴・命令実行・継続判断の仕組みと、CIELへの接続点をコードから説明する。 |
| [games/minecraft/minecraft-long-horizon-ja.md](games/minecraft/minecraft-long-horizon-ja.md) | Minecraftの長い作業を進めるための、依存関係のグラフ・計画グラフの実行器・アイテム以外の目標へ広げた汎用の実行計画・LLMが判断する分岐と遅延した判断・世界の記憶・持ち主への相談の設計と、段階ごとの採用条件。 |
| [games/minecraft/minecraft-benchmark-ja.md](games/minecraft/minecraft-benchmark-ja.md) | 課題・practical-v1・採点・専用環境・実行・拡張・比較の方法。 |

## アプリ

| 資料 | このファイルが所有する内容 |
|---|---|
| [app/app-composition-ja.md](app/app-composition-ja.md) | Companion/Broadcastの共通Prefab・シーンと操作/配信出力の構成。 |
| [app/work-display-contract-ja.md](app/work-display-contract-ja.md) | goal.state/control v2、鮮度、表示対象を固定した操作と共通表示。 |
| [app/ciel-touch-interaction-ja.md](app/ciel-touch-interaction-ja.md) | タッチの当たり判定、部位・変形・入力の送信と端末内反応。 |

## Live2D

| 資料 | このファイルが所有する内容 |
|---|---|
| [app/live2d/ciel-live2d-production-spec-ja.md](app/live2d/ciel-live2d-production-spec-ja.md) | 外観と素材の制約、正式成果物、採用・組み込みの受け入れ条件。 |
| [app/live2d/ciel-live2d-rig-design-ja.md](app/live2d/ciel-live2d-rig-design-ja.md) | 現行リグの制御パラメーター、変形・物理・書き出し・採用操作。 |
| [app/live2d/ciel-live2d-reference-rig-analysis-ja.md](app/live2d/ciel-live2d-reference-rig-analysis-ja.md) | 参考サンプルの構造・数値と制作へ使う条件。現行モデルの台帳ではない。 |

## 紹介・公開

| 資料 | このファイルが所有する内容 |
|---|---|
| [publishing/demo-recording-ja.md](publishing/demo-recording-ja.md) | 紹介映像の台本、撮影条件、OBSへの取り込みと公開物の確認。 |

## 掲載画像

| 資料 | このファイルが所有する内容 |
|---|---|
| [assets/showcase/README.md](assets/showcase/README.md) | README掲載スクリーンショットの用途と差し替え方法。 |
