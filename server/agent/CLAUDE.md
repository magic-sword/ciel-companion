# 会話サーバーを扱う Claude へ

@AGENTS.md

- 今の会話の組み立ては pipeline（本番も開発用も `CIEL_MODEL=pipeline`）。直す前に [会話の組み立て（pipeline）の仕組み](../../docs/conversation-pipeline-ja.md) の 0 章と、触る部品の章を読む。
- なぜ今の形かは [会話の作り直しの成果](../../docs/conversation-improvements-2026-10-ja.md)。そこで外したやり方（小脳に [think] を言わせる・LiveKit の会話を書き換える・指示文だけで道具を止める）に戻さない。
