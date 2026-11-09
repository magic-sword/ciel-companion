# 現在のドキュメント

> 責務：全資料の索引と各ファイルの責務。仕様・手順・結果の本文は複製しない。

この一覧から目的に合う正本を選ぶ。各ファイルは下記の責務だけを持ち、過去の仕様・改修履歴はGitから参照する。[管理ルール](documentation-policy-ja.md)に従って既存の正本を更新する。

## 読む順番

設計変更は[設計方針](design-policy-ja.md)と対象の契約から、導入は[開発環境](development-setup-ja.md)から始める。本番・開発の切替は[実行設定](local-runtime-ja.md)、実際に確認できている範囲は[確認状況](verification-status-ja.md)を参照する。

## 入口

| 資料 | このファイルが所有する内容 |
|---|---|
| [README.md](README.md) | 全資料の索引と各ファイルの責務。仕様・手順・結果の本文は複製しない。 |
| [documentation-policy-ja.md](documentation-policy-ja.md) | 資料の所有範囲、更新・統合・削除、リンク検証の管理ルール。 |
| [design-policy-ja.md](design-policy-ja.md) | 責任分担と採用する設計判断。詳細スキーマ・コマンド・測定値は各正本へ委ねる。 |
| [architecture-ja.md](architecture-ja.md) | プロセス・配置・接続・共有範囲の地図。 |

## 開発と運用

| 資料 | このファイルが所有する内容 |
|---|---|
| [development-setup-ja.md](development-setup-ja.md) | クローン後の依存復元、SDK導入、最初の表示・開発環境の準備。 |
| [build-ja.md](build-ja.md) | アプリのビルド、配置、更新、ログ取得の操作。 |
| [sdk-setup-ja.md](sdk-setup-ja.md) | 固定SDKの復元・互換修正・パッケージ確認。 |
| [local-runtime-ja.md](local-runtime-ja.md) | 本番・開発の推論設定、設定ファイルの優先順位、切替・反映単位。 |
| [shared-llm-api-ja.md](shared-llm-api-ja.md) | 共用LLM APIの接続・容量設定・GPU/CPU制御と測定方法。 |
| [regression-tests-ja.md](regression-tests-ja.md) | 変更に応じたテストの選び方、コマンド、終了コード。 |
| [paid-checks-ja.md](paid-checks-ja.md) | 外部APIを呼ぶ試験、費用と実行範囲の確認方法。 |
| [verification-status-ja.md](verification-status-ja.md) | 直近の検証・性能の条件、ソース識別、生データの場所、未確認範囲。 |

## 会話とサービス

| 資料 | このファイルが所有する内容 |
|---|---|
| [conversation-pipeline-ja.md](conversation-pipeline-ja.md) | 入力から返答までの実行順、共通履歴、経路選択、発話の調停。 |
| [prompt-management-ja.md](prompt-management-ja.md) | Markdown/TOMLの指示管理、ロード・指紋・編集・評価の契約。 |
| [capability-runtime-ja.md](capability-runtime-ja.md) | 能力カタログ、段階的な公開、呼び出し権限と実行管理。 |
| [service-boundaries-ja.md](service-boundaries-ja.md) | 各サービスと会話ホスト、公開操作と基盤専用操作の分担。 |
| [service-events-and-reactions-ja.md](service-events-and-reactions-ja.md) | 非同期入力の契約、TTL・優先・集約・発話/表情の調停。 |
| [local-stt-ja.md](local-stt-ja.md) | CPU音声認識のアダプター、途中/確定結果、モデル配置と評価方法。 |
| [shared-memory-ja.md](shared-memory-ja.md) | 本人確認・保存同意・DBスコープ、共有記憶と競合・忘却の実装契約。 |
| [people-memory-ja.md](people-memory-ja.md) | 利用者による人物・声・メモの登録、訂正、参照、削除の操作。 |
| [meeting-minutes-ja.md](meeting-minutes-ja.md) | 議事録の受付、対象範囲、ライブ・清書・送信・保存の契約。 |
| [meeting-bridge-ja.md](meeting-bridge-ja.md) | 会議へ参加する端末の音声・映像設定と利用手順。 |
| [web-research-ja.md](web-research-ja.md) | Web調査の依頼、引用確認、結果保持、画面と発話への対応。 |
| [singing-scoring-ja.md](singing-scoring-ja.md) | 歌の解析モデル、主観評価・途中反応・音声保持・GPUの扱い。 |
| [youtube-comments-design-ja.md](youtube-comments-design-ja.md) | 配信コメントの取得・選別・権限・会話への入力。 |
| [vision-design-ja.md](vision-design-ja.md) | 画像の受信・保持・参照ID・理解と利用不可の扱い。 |
| [errors-design-ja.md](errors-design-ja.md) | 失敗の分類、利用者へ見せる通知、正常状態へ変換しない規則。 |

## ゲーム

| 資料 | このファイルが所有する内容 |
|---|---|
| [game-environment-mcp-design-ja.md](game-environment-mcp-design-ja.md) | 環境を追加するためのMCP接続・profile・観測・所有権・通知。 |
| [game-work-contract-ja.md](game-work-contract-ja.md) | ゲーム非依存の依頼・予算・判断・取消・work状態の契約。 |
| [body-command-lifecycle-ja.md](body-command-lifecycle-ja.md) | 低水準の体の命令、世代・切替・後片付け・停止確認。 |
| [minecraft-design-ja.md](minecraft-design-ja.md) | Minecraft固有の体・計画・知識・視覚と接続先・変更入口。 |
| [minecraft-benchmark-ja.md](minecraft-benchmark-ja.md) | 課題・practical-v1・採点・専用環境・実行・拡張・比較の方法。 |

## アプリとモデル

| 資料 | このファイルが所有する内容 |
|---|---|
| [app-composition-ja.md](app-composition-ja.md) | Companion/Broadcastの共通Prefab・シーンと操作/配信出力の構成。 |
| [work-display-contract-ja.md](work-display-contract-ja.md) | goal.state/control v2、鮮度、表示対象を固定した操作と共通表示。 |
| [ciel-touch-interaction-ja.md](ciel-touch-interaction-ja.md) | タッチの当たり判定、部位・変形・入力の送信と端末内反応。 |
| [ciel-live2d-production-spec-ja.md](ciel-live2d-production-spec-ja.md) | 外観と素材の制約、正式成果物、採用・組み込みの受け入れ条件。 |
| [ciel-live2d-rig-design-ja.md](ciel-live2d-rig-design-ja.md) | 現行リグの制御パラメーター、変形・物理・書き出し・採用操作。 |
| [ciel-live2d-reference-rig-analysis-ja.md](ciel-live2d-reference-rig-analysis-ja.md) | 参考サンプルの構造・数値と制作へ使う条件。現行モデルの台帳ではない。 |
| [demo-recording-ja.md](demo-recording-ja.md) | 紹介映像の台本、撮影条件、OBSへの取り込みと公開物の確認。 |
| [assets/showcase/README.md](assets/showcase/README.md) | README掲載スクリーンショットの用途と差し替え方法。 |
| [third-party-dependencies.md](third-party-dependencies.md) | SDK・モデル・素材の依存と利用許諾、リポジトリへ含める範囲。 |
