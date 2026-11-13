@AGENTS.md

ローカルLLMの重み直接編集と人格・身体性・一般性能の比較には `.claude/skills/ciel-weight-space-programming/SKILL.md` を使う。

ベンチマークの達成度採点・改善量の比較を設計または見直すときは `.claude/skills/ciel-benchmark-progress/SKILL.md` を使う。WSPの評価感度の確認にも適用する。

Minecraft のベンチマークには `.claude/skills/ciel-minecraft-benchmark/SKILL.md` を入口として使う。共通の評価手順の正本もこのファイルにある。

音声認識精度・応答遅延のベンチマークには `.claude/skills/ciel-voice-benchmark/SKILL.md` を入口として使う。

シエルの会話モデルへ渡すプロンプト（`server/agent/config/prompts`、persona.toml、会話へ差し込む補足の文言）を書く・直すときは `.claude/skills/ciel-prompt-writing/SKILL.md` を使う。

文書の追加・整理・更新では[文書管理スキル](.claude/skills/ciel-documentation/SKILL.md)を使う。共有スキルの正本は`.claude/skills`、Codex側の`.agents/skills`は正本を読む入口とする。
