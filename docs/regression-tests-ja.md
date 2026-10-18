# サーバーの回帰テスト

入口はGit管理の `scripts/server/run-regression.py`。PowerShellからは `scripts/server/test-regression.ps1` でも実行できる。実行場所によらずリポジトリのテストを見つける。

## 初回の準備

Python 3.11または3.12で、テスト用の仮想環境を作る。音声モデル・GPU・Unity・APIキーは不要。通常テストには外部サービスの資格情報を渡さず、テスト内のモックと合成データを使う。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server/agent/requirements-test.txt
```

仮想環境はGit管理しない。Linuxでは `.venv/bin/python` を使用する。

## 修正のたびに実行する通常テスト

```powershell
.\scripts\server\test-regression.ps1 -Python .\.venv\Scripts\python.exe
```

会話履歴、話者・名前登録、共有記憶の同期、議事録、Web調査の制御、音声合成の待機・取り消し、回帰テストの結果報告を検証する。DB結合テストはこの段階では選択せず、結果に `db: skipped / Not selected by --suite` と明記する。

## デプロイ前の通常テスト＋DB結合テスト

Dockerが動いている端末で実行する。初回は固定したDBイメージを取得するため、通信が発生する場合がある。

```powershell
.\scripts\server\test-regression.ps1 -Python .\.venv\Scripts\python.exe -Suite all
```

- `pgvector/pgvector:0.8.0-pg17` で専用コンテナを作成する。名前とパスワードは実行ごとに生成する。
- 接続先は `ciel_concurrency_test`。ポートは空いているものを割り当て、127.0.0.1だけで待ち受ける。本番の `.env` や `CIEL_DB_URL` は使わない。
- ホストのデータや永続ボリュームはマウントしない。通常終了・テスト失敗時とも、この実行で作ったコンテナだけを削除する。
- 同時更新、忘却依頼、削除、トランザクションの競合を実際のPostgreSQLで検証する。Dockerが使えなければ失敗として扱い、DBテストを省略して成功にはしない。
- 強制終了・OS停止で後処理が動かなかった場合は、`docker ps -a --filter name=ciel-regression-` で残ったテスト用コンテナを確認し、該当する名前だけを指定して削除する。

Pythonで直接実行する場合：

```sh
python scripts/server/run-regression.py --suite unit
python scripts/server/run-regression.py --suite db
python scripts/server/run-regression.py --suite all
```

別途用意した**使い捨て専用DB**を使う場合のみ、`CIEL_TEST_DB_URL` を環境変数で設定し、`--db-mode external` を指定する。DB名が `ciel_concurrency_test` であることをテスト側でも確認してから書き込む。通常のアプリDBは指定しない。URLをコマンドライン引数やGitへ保存しない。

```powershell
# CIEL_TEST_DB_URLをローカルの環境変数で設定済みの場合
.\scripts\server\test-regression.ps1 -Python .\.venv\Scripts\python.exe -Suite all -DbMode external
```

## 結果と終了コード

結果は `.local/regression/<UTC日時-ID>/` に保存する。スクリプト・テスト・合成データ・手順をGitで管理し、結果やDB資格情報は管理しない。Python版の `--output <新規ディレクトリ>` で出力先を変更できる。既存の結果は上書きしない。

| ファイル | 内容 |
|---|---|
| `report.json` | 実行日時、Python版、Gitコミットと未コミット変更の有無、段階ごとの状態、テストごとの成功・失敗・スキップ、理由、所要時間 |
| `junit.xml` | CIやテスト結果ビューア用のJUnit形式 |
| `unit.json` / `db.json` | 実行した段階の詳細と診断出力 |

| 終了コード | 意味 |
|---|---|
| `0` | 選択した段階がすべて成功。選択しなかった段階は別にスキップ表示 |
| `1` | テスト失敗、依存不足、DB起動失敗、設定不足、時間超過など |
| `2` | 選択した段階でスキップ・期待された失敗があり、確認が未完了 |

段階ごとのテスト時間制限は既定300秒。Python版の `--timeout` で変更できる。DB起動の待機期限は別に45秒。各段階を別プロセスで実行し、環境変数にあった本番DB・OpenAI・LiveKit・議事録Webhookの資格情報は引き継がない。外部APIに実際に接続する評価は含まない。

新しい通常テストは `server/agent/tests/test_*.py` に追加すれば自動で対象になる。新しいDB結合テストのファイルを増やす場合は、入口スクリプトの `DB_TESTS` に登録し、通常テストから分離する。

## 自動テストで保証しないこと

実AIが適切なツールを選ぶかの会話評価は、今後、別の明示実行段階として整備する。現時点の通常テストはAIを呼ばず、API応答をモック化して周辺処理を検証する。

音声の聞き取り、話者識別の精度、会話の自然さ、GPUでの待ち時間、Windows・スマホの2台同時会話、Unityビルドは別の検証が必要。回帰テストの成功を、これらも確認済みという意味では扱わない。

2026-10-18の導入検証：通常テスト128件と、隔離した実PostgreSQLでの5件に合格。Windowsの非同期DB接続に必要なイベントループ設定を入口に含めた。実DBの検証はローカルDockerが停止していたため、一時DBへのSSH転送を使って `--suite all --db-mode external` で実施した。自動Docker起動経路のコンテナ削除はモックで検証済みだが、この端末での実起動は未確認。DB接続先が未設定の場合にエラーとなること、結果に未実行理由が残ることも確認した。本番サービスや本番DBは変更していない。
