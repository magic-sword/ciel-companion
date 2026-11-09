# 開発用と本番の記憶の共有

> 責務：本人確認・保存同意・DBスコープ、共有記憶と競合・忘却の実装契約。

更新：2026-11-06（日本時間）。対象：`server/agent/speaker_store.py`（`CIEL_MEMORY_SCOPE`・`visible`・`protected`）、`speakers.py`（`_shared_elsewhere`）、`speaker_admin.py`、`server/compose.yaml`・`compose.dev.yaml`、`server/deploy-remote.sh`（dev）。

## 1. 何のためか

開発用の会話サーバー（[開発用の会話サーバー](build-ja.md)）で実装を増やしていく。そのとき、

- 開発用で話しても、本番で覚えたハカセ（持ち主）のことをシエルが知っている。
- 開発用の会話で増えたハカセの記憶も、本番へそのまま持ち越す。
- ほかの人・開発用で試しに覚えた人の記憶は、本番に混ぜない。

それまでは、本番が DB のコンテナ `ciel-db-1` の `ciel`、開発用が同じコンテナの別のデータベース `ciel_dev` を使っていた。開発用ではハカセを知らなかった（`ciel_dev` に覚えている人は 0 人）。

## 2. 決めたこと（利用者の判断、2026-11-06）

| 項目 | 決めたこと |
|---|---|
| 共有の形 | **1 つのデータベース `ciel` を両方で使い、人に印を付けて分ける**。写し合い（同期）はしない。ハカセの記憶は 1 か所だけにあるので食い違わない |
| 開発用で書くもの | ハカセについて全部（名前と声の見本・メモ・関係・「忘れて」）。開発用で書いたメモには印（`person_notes.origin = 'dev'`）を付け、あとで見分け・取り消しができる |
| 消すとき | 開発用からの「〜を忘れて」（メモの一部）は本番にも効く。**人ごと消す・呼び名を変える・端末の持ち主をやめる**は、開発用からはできない（本番か、本番の管理コマンドで行う） |
| シエル自身の日記・好み | 両方で 1 つ（`ciel_events`・`ciel_likes`・`ciel_like_history` に印は付けない） |

## 3. しくみ

### 印

| 列 | 値 | 意味 |
|---|---|---|
| `people.origin` | `main`（既定）・`dev` | どちらの会話サーバーで覚えた人か |
| `people.shared` | `false`（既定）・`true` | 本番の人を開発用にも見せるか（ハカセだけ `true`） |
| `person_notes.origin` | `main`（既定）・`dev` | どちらの会話サーバーが最後に書いたメモか |

列は、会話サーバーが起動のたびに足す（`speaker_store.SCHEMA`。あれば何もしない）。今までの人・メモは `main` になる。

### どちらの会話サーバーか

環境変数 `CIEL_MEMORY_SCOPE`（`main`・`dev`。既定 `main`）。`compose.yaml` は `main`、`compose.dev.yaml` は `dev` を書く。`Store.scope` に持つ。

| | 本番（main） | 開発用（dev） |
|---|---|---|
| 見える人（`load_all`・`versions`） | `origin = 'main'` の人 | `origin = 'dev'` の人と、`origin = 'main' AND shared` の人 |
| 新しく覚えた人 | `origin = 'main'` | `origin = 'dev'`（本番から見えない） |
| メモを書く | `origin = 'main'` | `origin = 'dev'` |
| 人を消す・呼び名を変える | できる | 自分の印（`dev`）の人だけ。共有の人は `SharedPersonError`。会話では「本番で頼んでください」と返す（`SpeakerBook._shared_elsewhere`） |
| 同じ名前で声を覚え直す | できる | できる（`rename` は名前が同じなら何もしない） |
| 端末の持ち主 | 決める・やめる | 共有の人が持ち主の端末は、開発用からもその人の端末として分かる。やめる・別の人へ付け替えるはできない（`unpair` は `not_paired`、`pair` は `shared_owner`） |
| 日記・好み | 共通 | 共通 |

`memory_snapshot`・`apply_notes`・`apply_relationship`・`request_forget` は人の番号で動く。番号は見える人からしか来ないので、絞り込みは要らない。

### 同時に話したとき

本番と開発用でハカセが同時に話しても、メモと関係は、前から使っている版番号（`memory_versions`。[複数端末の独立した会話](architecture-ja.md)）で、古い内容からの書き込みを捨てて読み直す。「忘れて」の頼みも、どちらの会話にもすぐ効く（`memory_forgets`）。2 つの会話サーバーは別の接続なので、端末が 2 つの場合と同じ。

### 試験の会話を混ぜない

- 開発用で知らない人に名乗ってもらって覚えても、その人は `origin = 'dev'` なので本番には出ない。
- 回帰テスト（`scripts/server/run-regression.py`）は `CIEL_DB_URL` を外して動くので、DB に書かない。
- 実 DB を使う試験（`tests/test_shared_memory_postgres.py`）は、データベース名が `ciel_concurrency_test` のときだけ動く。
- 開発用でハカセと試しに話した分は、ハカセの本当の記憶として残る（利用者の判断）。消したいときは、`speaker_admin.py drop-dev-notes 2` で開発用で書いたメモだけを消せる。

## 4. 管理（`speaker_admin.py`）

本番のコンテナ（`ciel-agent-1`）と開発用のコンテナ（`ciel-dev-agent-dev-1`）のどちらでも使える。見える・直せる人は、そのコンテナの `CIEL_MEMORY_SCOPE` で決まる。

| コマンド | 本番 | 開発用 |
|---|---|---|
| `list` | `main` の人（印の列に `main・共有`） | `dev` の人と共有の人 |
| `notes <番号>` | メモ。開発用で書いたものに［開発用で書いた］ | 同じ |
| `share <番号>`・`unshare <番号>` | 開発用にも見せる・見せない | できない |
| `drop-dev-notes <番号>` | 開発用で書いたメモだけを消す | 同じ |
| `rename`・`delete` | `main` の人 | `dev` の人だけ |
| `delete-all` | `main` の人だけ | `dev` の人だけ |

## 5. 反映の順と注意

1. **開発用を先に配る**（`scripts/server/deploy-server.sh --dev`）。`deploy-remote.sh dev` が、起動の前に毎回 `ciel` をバックアップする（`~/work/ciel-db-backups/ciel-日時.sql.gz`、新しい 14 個）。開発中のコードが起動のときに共有の DB の表を作り替えるため。
2. 起動で列ができたら、ハカセに共有の印を付ける（`UPDATE people SET shared = true WHERE id = 2`。本番に新しいコードが入ったあとは `speaker_admin.py share 2`）。
3. 本番に新しいコードを入れるまでは、本番は印を見ない（開発用で覚えた人が本番からも見える）。2026-11-06 に、開発用と同じ日に本番へも入れた（`CIEL_MEMORY_SCOPE=main`）。DB の印を変えるときは、本番と開発用を同じ日に入れる。
4. 開発用の `ciel_dev` にあった日記（18 件）・好み（1 件）・好みの記録は、`ciel` へ写した（そのときの本番は 0 件）。`ciel_dev` は消さずに残してある。

戻すとき：`compose.dev.yaml` の `CIEL_DB_URL` を `ciel_dev` に戻せば、開発用は前の別々の記憶に戻る。本番は印を見ても見なくても、`main` の人だけを今までどおり使う。


## 本人確認・保存同意の境界

名前の仮登録、話者の推定、確かな本人、声の保存同意、会話内容の保存同意を分ける。同名・「たぶん」・端末の持ち主の推測だけで人物を統合したり、個人メモを読み出したりしない。会議の仮名簿は接続ごとに分離し、その場で確認できない過去の人物を参加者へ追加しない。

端末の持ち主は端末IDと合言葉の検証、本人の声による確認を経て結び付ける。合言葉そのものをDBへ保存せず、ハッシュを照合する。声の見本は経路別の上限を持ち、人違いの訂正・声の登録・削除を明示的に扱う。細かな閾値と保持数は`speakers.py`・`speaker_store.py`とテストを正本とする。

本人のメモ・関係・好みの生成はホストが確定した対象とスナップショットを使う。生成中に同意・名前・忘却・人物が変わった場合は版番号で古い保存を拒否する。忘却の受付中は古いメモ・気持ちの注入を止める。すでに外部モデルへ渡した過去の内容を遡及削除する保証とは区別する。

記憶のツール化は[サービス境界](service-boundaries-ja.md)を使い、任意の人物IDやSQLをLLMへ公開しない。利用者の操作は[人を覚える機能](people-memory-ja.md)、履歴と議事録は[会話pipeline](conversation-pipeline-ja.md)と[議事録](meeting-minutes-ja.md)、試験の到達点は[確認状況](verification-status-ja.md)を参照する。
