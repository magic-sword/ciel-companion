# 会話サーバーのキャラクター設定

GPT-Live と Realtime のプロンプト本文は、UTF-8 の Markdown として編集します。[管理方針・引き継ぎ手順](../../docs/decisions/prompt-management-ja.md) に、構成の理由、検証・公開・履歴管理の方法をまとめています。

| 編集するファイル | 内容 |
|---|---|
| [character.md](config/prompts/character.md) | 人物像、話し方、会話上のルール |
| [greeting.md](config/prompts/greeting.md) | 初回のあいさつを生成するための指示 |
| [emotion.md](config/prompts/emotion.md) | Irodori-TTS 用の感情タグの指示 |
| [touch.md](config/prompts/touch.md) | 画面のタッチ（`[タッチ]` の知らせ）への反応の仕方。処理は `touch.py` |
| [talk_quiet.md](config/prompts/talk_quiet.md) | おしゃべり度「ひかえめ」で、呼ばれたときだけ答え、それ以外は `[silent]` で黙る決まり。処理は `mode.py` |
| [talk_quiet_turn.md](config/prompts/talk_quiet_turn.md) | ひかえめのとき、返事を作らせるたびに添える短い念押し。処理は `turns.py` |
| [talk_chatty.md](config/prompts/talk_chatty.md)・[talk_chatty_nudge.md](config/prompts/talk_chatty_nudge.md) | おしゃべり度「おしゃべり」で、自分から話しかけるときの決まりと、しばらく静かなときに渡す合図。処理は `initiative.py` |
| [presence_solo.md](config/prompts/presence_solo.md)・[presence_close.md](config/prompts/presence_close.md)・[presence_public.md](config/prompts/presence_public.md) | その場にいる人（ひとり・身近な人・人前）ごとの、覚えている人のメモの使い方。処理は `mode.py`・`speakers.py` |
| [speakers.md](config/prompts/speakers.md) | 話している人（`[発言者：…]`）の読み方、名前を聞く・同意を取る流れ、人についての道具（`tools/people.py`）の使い方 |
| [notes.md](config/prompts/notes.md) | 会話の裏で、その人について覚えておくメモを書く記録係（`notes.py`、別の文字のモデル）への指示 |
| [conversation.md](config/prompts/conversation.md) | 今の接続中の会話を検索する道具の使い方。構成・検証は[共通会話履歴](../../docs/decisions/conversation-history-ja.md) |
| [relationship.md](config/prompts/relationship.md) | 会話の終わりに、シエルがその人をどう思っているか（親しさの段階・気持ち・一時的な気分）を書き直す係（`relationship.py`）への指示 |
| [persona.toml](config/persona.toml) | 上記のファイルの参照先 |

本文は Markdown のソースをそのままモデルへ渡します。見出しや箇条書きを使えます。編集者向けのメモはこの README や管理方針に置いてください。`emotion.md` のタグ名は声・表情の処理が使うため維持してください。

VS Code では `Alt+Z` で行を折り返し、Markdown の `Ctrl+K` → `V` で横にプレビューを表示できます。

## 変更を反映する

保存した内容は**次に開始する会話から反映**されます。進行中の会話は開始時の内容を使い続けます。Docker Compose はホストの `config/` を読み取り専用でマウントするため、本文や TOML の変更だけなら再起動・再ビルドは不要です。

今回のローダー変更を初めて導入するときは、リポジトリのルートで `scripts/server/deploy-server.sh` を実行してください（`server/compose.yaml` の一式を `docker compose up -d --build` します）。以前の本文を埋め込む TOML は使えないため、コード・TOML・Markdown を一式で更新します。

別の設定を使う場合は TOML と本文を用意し、`.env` の `CIEL_PERSONA_CONFIG=config/別の設定.toml` で選びます。環境変数の相対パスは `server/agent/` 基準、TOML 内の相対パスはその TOML のディレクトリ基準です。絶対パスも指定できます。Docker Compose ではマウントされる `config/` 内に配置してください。`.env` の変更後はサーバーの再起動が必要です（自宅サーバーの `~/work/ciel-companion/server` で `docker compose up -d`）。

## ローカルで読み込みを確認する

Python 3.11 以降で、`server/agent/` から実行します。LiveKit や API キーは不要です。

```sh
python -c "from persona import load_persona; p = load_persona(); print('OK:', p.fingerprint)"
```

ファイルがない、不正な TOML・UTF-8、必須の参照先が未指定、本文が空の場合は、ファイルや項目を示すエラーになります。このコマンドは読み込みだけの確認です。本文を変更したら、管理方針にある代表的な会話で品質も確認してください。

会話開始時のログに `persona_sha256` とモデル・声の設定が出ます。本文一式を識別するための値で、プロンプト本文は記録しません。編集したファイルは Git で管理し、本番には確認済みのコミットの一式を配布します。
