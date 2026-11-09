# ciel-companion を扱うエージェントへ

- Minecraft の動作評価、課題の追加、モデル・プロンプト・体の変更前後の比較では、[ciel-minecraft-benchmark スキル](.agents/skills/ciel-minecraft-benchmark/SKILL.md)を読む。
- 終了条件は [practical-v1](docs/minecraft-benchmark-practical-ja.md)。既定1配置・1回、課題60〜120秒、操作未発行30秒、全体10分。CPU待ちや失敗を救済して課題期限を延長しない。旧900秒条件の基準値と直接比較しない。
- ローカル推論は [共通GPU API](docs/shared-llm-api-ja.md) を参照。既定のベンチマーク会話もシエルと同じ8094を使う。追加のCPUモデル起動は明示した場合だけ。共有負荷・歌によるCPU切替を評価条件に記録する。
- 文字の推論と道具呼び出しはローカル LLM に切り替えて試験できる。設定は [ローカル LLM](docs/local-llm-ja.md)。Minecraft の実機評価は自宅サーバーの専用環境を使う。手元PCへの Minecraft の新規起動や、普段のワールドの初期化で代用しない。
- 最新の比較用記録は [GPU共用・practical-v1の7課題一巡](docs/minecraft-benchmark-gpu-shared-2026-11-09-ja.md)。配置11・各1回、3合格、準備・片付け込み約6分。複数配置・反復の性能基準ではなく、進捗oracleや旧作業snapshotの注意点も読む。[旧CPU・900秒条件の各54試行](docs/minecraft-benchmark-baseline-2026-11-09-ja.md)と成功率を直接比較しない。API容量・共有負荷の測定は [共通GPU API](docs/shared-llm-api-ja.md)、終了条件は [practical-v1](docs/minecraft-benchmark-practical-ja.md)。
- 測定で分かった問題の改修は [ゲーム実行を前提にしたシエルとMCPの再設計](docs/minecraft-execution-redesign-ja.md)を読む。LLMの判断、共通の作業管理、ゲーム側の計画・実行を分担する未実装の方針。既存の心・pipeline・GoalRunnerの維持を前提にしない。作業契約を先に定め、ADK採用は最小例で比較する。評価器や試行初期化を変えた比較は旧アプリ側も同条件で測り直す。
- 稼働中の Minecraft で発生した不具合の現場調査には、[ciel-minecraft-debug](.claude/skills/ciel-minecraft-debug/SKILL.md)を使う。専用ベンチマークとは接続先・復元範囲が異なる。
- 会話サーバーを変更するときは、追加で [server/agent/AGENTS.md](server/agent/AGENTS.md)を読む。通常の検証方法は [回帰テスト](docs/regression-tests-ja.md)、全体の入口は [資料一覧](docs/README.md)。
