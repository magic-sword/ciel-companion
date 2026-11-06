# 開発用と本番の記憶の共有

更新：2026-11-06（日本時間）。対象：`server/agent/speaker_store.py`（`CIEL_MEMORY_SCOPE`・`visible`・`protected`）、`speakers.py`（`_shared_elsewhere`）、`speaker_admin.py`、`server/compose.yaml`・`compose.dev.yaml`、`server/deploy-remote.sh`（dev）。

## 1. 何のためか

開発用の会話サーバー（[開発用の会話サーバー](decisions/dev-server-ja.md)）で実装を増やしていく。そのとき、

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

本番と開発用でハカセが同時に話しても、メモと関係は、前から使っている版番号（`memory_versions`。[複数端末の独立した会話](decisions/independent-conversations-ja.md)）で、古い内容からの書き込みを捨てて読み直す。「忘れて」の頼みも、どちらの会話にもすぐ効く（`memory_forgets`）。2 つの会話サーバーは別の接続なので、端末が 2 つの場合と同じ。

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

## 6. 確かめたこと

- 単体試験 `tests/test_memory_scope.py`：見える人の条件、新しい人・メモへの印、開発用からの削除・呼び名の変更・持ち主の解除と付け替えの拒否、本番では今までどおり消せること。
- 実 DB の試験 `tests/test_shared_memory_postgres.py`（`ciel_concurrency_test`）：本番から開発用の人が見えない、共有の印で開発用から見える、開発用で書いたメモが本番に `dev` の印で届く、開発用の「忘れて」が本番に効く、開発用から消せない。
