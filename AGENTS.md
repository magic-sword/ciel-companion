# ciel-companion を扱うエージェントへ

- Minecraft の動作評価、課題の追加、モデル・プロンプト・体の変更前後の比較では、[ciel-minecraft-benchmark スキル](.agents/skills/ciel-minecraft-benchmark/SKILL.md)を読む。
- 文字の推論と道具呼び出しはローカル LLM に切り替えて試験できる。設定は [ローカル LLM](docs/local-llm-ja.md)。Minecraft の実機評価は自宅サーバーの専用環境を使う。手元PCへの Minecraft の新規起動や、普段のワールドの初期化で代用しない。
- 最新の評価は [基準測定](docs/minecraft-benchmark-baseline-2026-11-09-ja.md)を読む。体・ローカル会話を各54有効試行で測定済み。環境障害2件は分けて不足分を補完し、会話側は3つのキャッシュ区間で集計している。実行していない評価を成功済みと扱わない。
- 稼働中の Minecraft で発生した不具合の現場調査には、[ciel-minecraft-debug](.claude/skills/ciel-minecraft-debug/SKILL.md)を使う。専用ベンチマークとは接続先・復元範囲が異なる。
- 会話サーバーを変更するときは、追加で [server/agent/AGENTS.md](server/agent/AGENTS.md)を読む。通常の検証方法は [回帰テスト](docs/regression-tests-ja.md)、全体の入口は [資料一覧](docs/README.md)。
