# 開発用の会話サーバー

決定日：2026-10-22。対象：`server/compose.dev.yaml`、`server/deploy-remote.sh`（dev）、`scripts/server/deploy-server.sh --dev`、`CielConversation.SetDevServer`。

## 背景

複数端末で同時に使えるようにした（[複数端末の独立した会話](independent-conversations-ja.md)）ので、試験・分析の最中にほかの人が本番を使うことがある。本番の会話サーバーで設定を切り替えたり、再起動したり、開発中のコードを入れたりすると、その人の会話に影響する。

## 決めたこと（利用者の判断）

| 項目 | 本番 | 開発用 |
|---|---|---|
| コードの場所（自宅サーバー） | `~/work/ciel-companion/server` | `~/work/ciel-companion-dev/server`（`deploy-server.sh --dev`。本番の `compose.yaml` は送らない） |
| 会話サーバー | 名前なし（ふつうの部屋に自動で入る） | 名前 `ciel-dev`（「ciel-dev を呼ぶ」部屋にだけ入る）。Compose のプロジェクト `ciel-dev`、状態確認の口 8091 |
| デバッグ用の会話ログ | 切っている（[決定記録](debug-log-ja.md)） | いつも残す（7 日で消える） |
| 覚えている人の記録 | DB のコンテナの `ciel` | 同じ DB のコンテナの `ciel_dev`（試験の登録・メモが本番の記憶に混ざらない。消せばやり直せる） |
| 議事録の下書き | 本番の Discord | 開発用の Discord のチャンネル（`server/.env.dev` の `CIEL_DEV_DISCORD_WEBHOOK`。利用者が書く。空ならサーバーに保存するだけ。本番の Webhook は必ず上書きして使わない） |
| 読み上げ（Irodori-TTS） | 共通 | 共通（GPU は 1 つ。同時に話すと順番待ちが少し起きる。会話ごとに順番を回す） |
| アプリ | ふだん | 設定 ＞ そのほか ＞ 開発「開発用のサーバーにつなぐ」。入れると、トークンを頼むときに部屋の設定 `room_config.agents = [{agent_name: "ciel-dev"}]` を添えて、つなぎ直す。左上に「C I E L ・ 開発用」 |

DB のコンテナは分けない。1 つで足り、バックアップ・更新も今のまま。DB そのものの版上げや大きな作り替えを試すときに分ける。

秘密情報は本番のものを読む（コピーしない）：OpenAI・LiveKit のキーは本番の `agent/.env`（`env_file`）、DB のパスワードは本番の `server/.env`（`--env-file`）。

## 確かめたこと（2026-10-22）

- 開発用のトークンサーバーに `room_config` を添えて頼むと、トークンに `roomConfig.agents: [{agentName: "ciel-dev"}]` が入る。
- その部屋に試験の参加者が入ると、開発用の会話サーバーだけが入り、**本番の会話サーバーは入らない**（本番のログにその部屋が出ない）。`room_config` の無いふつうの部屋には、本番だけが入り、開発用は入らない。本番の作りは変えていない。
- 開発用は `ciel_dev` を使い（覚えている人 0 人から）、デバッグ用の会話ログを書く。
- アプリの設定画面のスイッチと左上の表示（Unity の画面写真）。

まだのこと：アプリを作り直して、実機から開発用につなぐ確認。開発用の Discord のチャンネルへの送信（Webhook はまだ無い）。
