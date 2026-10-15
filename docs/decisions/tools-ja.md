# シエルの道具（function calling）の決定記録

日付：2026-10-16（日本時間）。

## 決めたこと

| 項目 | 決定 | 理由 |
|---|---|---|
| 情報の渡し方 | 覚えている人の一覧などを、最初から指示に入れない。会話モデルが**必要なときに道具を呼んで**調べる | 利用者の懸念（2026-10-16）：人数が増えると指示が長くなり、会話に関係ない名前を急に出すおそれがある。必要な分だけ取りに来させれば、指示は短いまま |
| 仕組み | Realtime API の function calling。道具は自宅サーバーの会話サーバーの中で動く | DB を外へ公開せずに使える。MCP と同じく「会話モデルが必要なときに呼ぶ」形 |
| 置き場所 | `server/agent/tools/`。モジュールごとに `@function_tool` の関数を `TOOLS` に並べ、`tools/__init__.py` の `TOOLS` に加える | 道具を足していけるように。会話サーバー本体（agent.py）を変えずに増やせる |
| 会話の状態 | 道具の中からは `context.userdata`（`tools.State`。今は話者の帳簿）を使う | LiveKit Agents の標準のやり方 |
| 使い方の教え方 | 関数の説明は短くし、いつ・どう使うかは `config/prompts/*.md` に書く | プロンプト管理方針（本文は Markdown で管理） |
| 個人情報 | 道具の結果は、会話に必要な分だけ返す。例：前に話した日は、本人が話しているときだけ教える | 他人の様子を聞き出せないように |

## 今ある道具

| 道具 | ファイル | 役割 |
|---|---|---|
| `name_speaker` | `tools/people.py` | 発言者に名前を付ける。本人が同意したときだけ声を保存（remember） |
| `forget_speaker` | `tools/people.py` | 本人の依頼で、声の記録を消す |
| `lookup_person` | `tools/people.py` | その名前の人の声を覚えているか調べる |
| `people_here` | `tools/people.py` | この会話で声を聞いた人（呼び名） |

## 道具の足し方

1. `server/agent/tools/` にモジュールを作り、`@function_tool` の関数を書いて `TOOLS` に並べる（例：`tools/people.py`）。
2. `tools/__init__.py` で読み込み、`TOOLS` に加える。会話の状態が要るなら `State` に足し、`agent.py` で入れる。
3. いつ使うかを `config/prompts/` の Markdown に書く（新しいファイルなら `persona.toml`・`persona.py` にも足す）。
4. 代表的な会話で、呼ぶべきときに呼び、呼ぶべきでないときに呼ばないかを確かめる。

## MCP との関係

| 方法 | どこで動くか | 使いどころ |
|---|---|---|
| function calling（今の方法） | 自宅サーバーの会話サーバー | 自前の処理・自宅の DB |
| LiveKit Agents の MCP 接続（`AgentSession(mcp_servers=[...])`、`MCPServerHTTP`・`MCPServerStdio`） | 自宅サーバー | 既製の MCP サーバー（カレンダー、検索など）をまとめて道具にしたいとき。会話モデルからは function calling の道具と同じに見える |
| Realtime API のリモート MCP | OpenAI のクラウドが MCP サーバーへ直接つなぐ | インターネットから届く MCP サーバー向け。自宅の DB を公開することになるので使わない。今の LiveKit の OpenAI プラグインには指定する口が見当たらない |

外部のサービスをつなぎたくなったら、まず LiveKit の MCP 接続で試す。
