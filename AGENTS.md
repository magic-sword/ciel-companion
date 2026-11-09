# ciel-companion を扱うエージェントへ

設計・実装の変更前に[現在の設計方針（正本）](docs/design-policy-ja.md)を参照する。方針を変えたら、正本と対応する契約・実装状況を同じ変更で更新する。

- Minecraft の動作評価、課題の追加、モデル・プロンプト・体の変更前後の比較では、[ciel-minecraft-benchmark スキル](.agents/skills/ciel-minecraft-benchmark/SKILL.md)を読む。
- 終了条件は [practical-v1](docs/minecraft-benchmark-ja.md)。既定1配置・1回、課題60〜120秒、操作未発行30秒、全体10分。CPU待ちや失敗を救済して課題期限を延長しない。旧900秒条件の基準値と直接比較しない。
- ローカル推論は [共通GPU API](docs/shared-llm-api-ja.md) を参照。既定のベンチマーク会話もシエルと同じ8094を使う。追加のCPUモデル起動は明示した場合だけ。共有負荷・歌によるCPU切替を評価条件に記録する。
- 文字の推論と道具呼び出しはローカル LLM に切り替えて試験できる。設定は [ローカル LLM](docs/local-runtime-ja.md)。Minecraft の実機評価は自宅サーバーの専用環境を使う。手元PCへの Minecraft の新規起動や、普段のワールドの初期化で代用しない。
- ゲーム実行の構成は[作業契約](docs/game-work-contract-ja.md)を読む。profile 2 / work 1で、シエル側は受付・作業管理、ゲーム側は計画・実行・修復を担当する。旧goal_plan/step/repairと直接の採集・製作APIは撤去済み。評価器や試行初期化を変えた比較は旧アプリ側も同条件で測り直す。
- 稼働中の Minecraft で発生した不具合の現場調査には、[ciel-minecraft-debug](.claude/skills/ciel-minecraft-debug/SKILL.md)を使う。専用ベンチマークとは接続先・復元範囲が異なる。
- 会話サーバーを変更するときは、追加で [server/agent/AGENTS.md](server/agent/AGENTS.md)を読む。通常の検証方法は [回帰テスト](docs/regression-tests-ja.md)、全体の入口は [資料一覧](docs/README.md)。

- 作業・目標や会話中の表示を変更するときは[表示契約](docs/work-display-contract-ja.md)を読む。goal.state / goal.control v2、元のwork状態と確認の有効期間、表示対象のID・版を維持する。旧段一覧・paused集約へ戻さない。

- 文書は[管理ルール](docs/documentation-policy-ja.md)と[資料一覧](docs/README.md)の責務に従い、既存の正本を更新する。日付付きの設計書・実装記録・旧仕様の併記を増やさず、履歴はGit、確認済みの条件と未確認範囲は[確認状況](docs/verification-status-ja.md)へ置く。
