# エラーの係（会話サーバーのエラーを 1 か所で受け止める）

> 責務：失敗の分類、利用者へ見せる通知、正常状態へ変換しない規則。

状態：作った（2026-11-07）。処理は `server/agent/errors.py`。

## なぜ

目的の係の 1 行の誤り（持ち主の呼び名を関数として呼んだ）で、心の道具 `start_goal` が内部エラーになった。心には LiveKit の「An internal error occurred」しか返らず、心は同じ頼みを `craft_item` で繰り返した。アプリの表示も変わらず、会話サーバーのログを探して初めて分かった（2026-11-07）。

## 何をするか

どこでエラーが起きても、`errors.ERRORS` が受け止めて、次の 4 つをする。

| すること | 中身 |
|---|---|
| 記録する | デバッグ用の会話ログに `error`（どこ・origin（tool・task・body）・例外の種類・メッセージ・自分たちのコードの場所 4 つまで）。会話をまたいで `server/agent/data/errors.jsonl` にも 1 行ずつ（2 MB で古いほうへ回す） |
| 心に伝える | 道具のエラーは `{"status": "tool_failed", "tool": …, "error": 例外の種類}` を返す（「internal error」の代わり）。心は正直に言い、別の道具で繰り返さない |
| アプリに知らせる | `agent.problem`（kind `bug`、service にどこ、at に場所）。接続の表示に「シエルの中でエラー・start_goal」と出る。同じ所は 60 秒に 1 回 |
| 集めて見る | `scripts/server/debug-log.sh errors`（開発用は `--dev`）で、場所ごとの数と直近のメッセージ |

## 受け止める所

- 心の道具：`tools/__init__.py` で全部を包む（`wrap_tools`）。ゲームの知識の窓口（MCP）の道具は包まない（LiveKit が受け止める）。
- 裏の処理：目的の係の流れ（`ERRORS.spawn`）。拾い損ねた asyncio の処理は、ループ全体の受け止め手（`install`）で拾う。
- 体（マイクラ）：技が体の中のエラーで終わった（done の reason `error`）とき（`report_body`）。

## 守ること

- エラーのメッセージには会話の中身が入ることがあるので、心とアプリには種類と場所だけを渡す。メッセージは記録（デバッグ用の会話ログ・errors.jsonl）にだけ残す（`health.py` と同じ決まり）。
- この記録は、足りない所を Claude Code に直させる「改造の依頼」（[ゲームの知識の窓口](minecraft-design-ja.md) の 7 章）の材料にもなる。
