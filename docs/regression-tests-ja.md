# サーバーの回帰テスト

Minecraft の実際の採集・製作・停止を採点する試験は、[タスクのベンチマーク](minecraft-benchmark-ja.md)。ここで説明する通常回帰テストには、採点・環境復元のガード・RCON通信・試験要求の照合のオフラインテストも含む。

入口はGit管理の `scripts/server/run-regression.py`。PowerShellからは `scripts/server/test-regression.ps1` でも実行できる。実行場所によらずリポジトリのテストを見つける。

この回帰テストは料金がかからない（API キー・LiveKit・読み上げの接続先を外して動かす）。OpenAI・LiveKit を使う試験（`eval_*`・`bench_*`）は別にして、関係するところを変えたときだけ回す。[料金のかかる試験](paid-checks-ja.md)。

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


## 能力の段階的ロードとMCP境界を変更したとき

通常のunit suiteに`test_capabilities.py`を含む。加えて、実際の`Ciel._pipeline_llm`を通すオフライン結合確認を行う。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/check-capability-runtime.py
```

LLMの選択だけを固定し、サービス読込、次の推論への道具・指示の公開、SDKの引数注入、実際のMCP往復、検索ホストへの到達を検証する。モデル・DB・Minecraftは起動しない。出力のスキーマ文字数はコンテキスト規模の参考値で、トークン数・実モデルの選択精度・速度改善の測定ではない。

サービスの処理本体と基盤専用呼び出しは `test_service_boundaries.py` で検証する。自発的検索の実MCP経路、画像参照の期限、アプリのraw schema、記憶生成取消時の要求再投入、サービス期限と取消伝播、任意YouTube操作の拒否を含む。DBのスコープ・同意・競合検知まで確認する場合は `--suite all` を使う。


## サービス入力とリアクションの検証（初版実装済み）

[入力イベントと反応調停の設計](service-events-and-reactions-ja.md)に従い、`test_reactions.py`と既存のMouth・GameEnv・SongListenerのテストで共通ロジックを確認する。以下の実機条件を自動テストだけで確認済みとは扱わない。

| ケース | 確認すること |
|---|---|
| 未ロードのサービスから被ダメージ通知 | 道具をロードせず受信し、許可された反応を行える |
| 接触後にGPU推論が遅延 | 即時表情が推論を待たず、後続発話が期限切れなら再生しない |
| 同じイベントの再送・順序逆転・再接続 | 反応を重複させず、過去の状態や体感を再生しない |
| コメントと持ち主の入力が同時到着 | コメントの本文を命令へ昇格させず、道具の続きでも権限を維持する |
| 歌唱中に歌の変化・コメント・被ダメージ | 通常の歌の変化は表情中心とし、緊急度に応じて明示した規則で調停する |
| 被ダメージ中に通常のLLM表情が到着 | 痛がる表情の優先と有効期限を維持する |
| 作業結果と被ダメージが同時到着 | 作業状態を確定し、双方の反応を識別して通知の先行returnで失わない |
| キュー満杯・期限切れ | 件数と本文量を制限し、正式な状態を失わず、破棄理由を記録する |
| 生成失敗・発話割り込み | 表情適用と発話済みを区別し、未発話を完了扱いにしない |
| 会話終了・接続所有者の変更 | 受信と待機中の反応を閉じ、他の会話や未所有の体へ反応を流さない |

オフライン確認は仮想時計と模擬サービスで行う。実機では表情・音声の反応時間、重複、取りこぼし、不要な割り込みを確認する。Minecraftは既定の専用環境を使う。モデル・GPU共有負荷・入力種別・推論回数を記録し、既存の能力ロードやサービス処理の回帰テスト結果とは別に報告する。


入力調停を変更したら、実際の`Ciel._pipeline_llm`と音声ゲートを通す次の結合確認も行う。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/check-reaction-runtime.py
```

固定したモデル応答で、作業通知が被ダメージを置き換えないこと、期限切れの生成と音声を出さないこと、割り込みを検証する。実モデル・LiveKit接続・Minecraft・GPUは起動しない。Unity側は `dotnet build unity/Assembly-CSharp.csproj --no-restore` によるC#コンパイルと、Unity Editor／実機での確認を区別する。タッチv2・表情v2・ゲーム通知input_v 1の送受信を同時に更新し、旧版への無言のフォールバックを追加しない。

## 作業・会話の表示v2（2026-11-10）

仕様は[作業・会話の表示契約](work-display-contract-ja.md)。段一覧・進捗率の推定を撤去し、7種類のwork状態、確認の失効・復旧、対象を固定した操作、会話との並行表示を検証した。

| 検証 | 結果 |
|---|---|
| Python通常テスト一式 | 634件合格、失敗・エラー・スキップ0。DB段階は未選択 |
| 最終のベンチマーク受信検証後の関連テスト | test_minecraft_benchmark.pyの29件合格 |
| 本体のC#受信・操作・表示ソースを使う.NET検証器 | 35項目合格。時計・JSON・送信はスタブ |
| Unity本体＋Editor C#コンパイル | Assembly-CSharp-Editor.csproj（本体参照を含む）、エラー0、警告80 |
| Unity Editorバッチの表示確認 | ライセンスエラー198で実行前に停止。画面画像・Unityの実JSONパーサーは未確認 |
| 本番配布・Playerビルド・実機接続・ゲーム性能再測定 | 未実施 |

再実行：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/run-regression.py --suite unit --output server/benchmark/data/work-display-v2-complete
dotnet run --project scripts/unity/work-display-check/WorkDisplayCheck.csproj
dotnet build unity/Assembly-CSharp-Editor.csproj --no-restore -verbosity:quiet -nologo
```

生の結果はGit対象外の`server/benchmark/data/work-display-v2-complete/report.json`、コンパイル結果は`work-display-build-final.log`、起動失敗のログは`work-display-unity.log`。検証器の生成物も同じdata配下に置く。外部APIや共有GPUには接続していない。通知の版をv2へ更新したため、反映時はサーバーとUnityアプリを一緒に更新して会話を再接続する。
