# Minecraft タスクのベンチマーク

> 責務：課題・practical-v1・採点・専用環境・実行・拡張・比較の方法。

2026-11-09。入口は `server/benchmark/run.py`、課題は `server/benchmark/tasks.json`。自宅サーバーで専用の Minecraft・体・試験用会話サーバーを使う。普段のワールドや DB は復元・変更しない。

Codex・Claude Code の作業手順は [共通の評価スキル](../../../.claude/skills/ciel-minecraft-benchmark/SKILL.md)。この文書を設定・採点・拡張方法の正本とする。ローカル推論の切替は [ローカル LLM](../../operations/local-runtime-ja.md)を参照する。

現在の終了条件は [実用性評価 practical-v1](minecraft-benchmark-ja.md)。課題別60〜120秒、操作未発行・不進行で早期終了し、既定は1配置・1回・実行全体10分。旧900秒条件の基準値とは直接比較しない。

改修前の実測は [GPU共用・7課題一巡](../../testing/verification-status-ja.md)。配置11・各1回を準備・片付け込み約6分で実施し、3合格。次の改修に使う比較条件と元データを保存した。複数配置・反復や、GPU対CPUだけの効果を分離した測定ではない。

改修後は [作業契約への移行と検証](../../testing/verification-status-ja.md)。同じ7課題・配置11の一巡で7合格、全体約5分21秒。完了通知の追加修正は別ソースの石の単発で確認した。新しい経路の内部操作をwork_actionで追跡し、状態監視はstatus_pollsとして分ける。進捗oracleの変更とは区別する。

初版のスモーク試験の範囲は末尾の「実機で確認した範囲」にある。その後の [基準測定](../../testing/verification-status-ja.md)では体・ローカル会話を各54有効試行で測定済み。成功率は体83.3%・会話48.1%。環境障害2件の補完、キャッシュ区間、到達時間、失敗の履歴は基準測定の文書を参照する。

## エージェントからの入口

- リポジトリ直下の `AGENTS.md` が共通案内、`CLAUDE.md` がその参照口。
- 共通手順の正本は `.claude/skills/ciel-minecraft-benchmark/SKILL.md`。Codexの `.agents/skills/ciel-minecraft-benchmark/SKILL.md` は正本を読む入口。作業手順は正本へ集約し、仕様やコマンドはこの文書で管理する。
- 稼働中のワールド固有の不具合調査は `ciel-minecraft-debug`。再現課題の評価には本ベンチマークを使う。

## 何を比較するか

| モード | 入力 | 評価する範囲 |
|---|---|---|
| `body` | 構造化した目的 | GoalRunner → MCP work → ゲーム側の計画・実行 → 体。LLM を呼ばない。心の判断が必要になったら `needs_mind` で失敗 |
| `conversation` | 課題の日本語の依頼を `lk.chat` へ送る | 普段の pipeline による解釈・道具選択・目的実行。ローカル LLM が既定。Irodori の読み上げ・LiveKit も使う |

[MineDojo の課題設計](https://docs.minedojo.org/sections/core_api/sim.html)にある初期条件・資源・技術ツリーの考え方と、[Voyager](https://github.com/MineDojo/Voyager)の段階的な到達・失敗からの修正を参考にした。環境・行動単位・Minecraft の版が違うため、論文のスコアと直接比較するものではない。

## 課題と評価モード

| ID | 目的・初期条件 |
|---|---|
| `gather_logs` | 素手でオークの原木8個。近くに原木がある |
| `wooden_pickaxe` | 持ち物なしで木のつるはし1本 |
| `stone_pickaxe` | 持ち物なしで石のつるはし1本 |
| `replenish_materials` | 木のつるはし・作業台・棒2本から、不足する丸石を集めて石のつるはし1本 |
| `find_logs` | 近くに原木が無い状態から、探して8個集める |
| `stop_collecting` | 原木64個の採集中、最初の取得を確認したら停止を指示。5秒以内の停止応答、その後5秒の持ち物・位置の安定と再実行なしを確認 |
| `stone_pickaxe_unavailable` | 木も所持品もない砂漠の専用領域。会話モードのみ。材料不足の理由を報告し、作業を止めて待てるかを評価。製作成功とは別に集計 |

原木は固定した配置の丸太で、自然生成の木・戦闘・食料管理・精錬は初版の対象外。世界のseedは `771023`。`--seed` は**ワールド生成のseedではなく、資源配置のseed**。既定は11・各1回（体6試行、会話7試行）。11・29・47、各3回を明示すると体54・会話63試行になるが、全体予算や連続失敗によって早期停止する場合がある。

毎回、専用領域 x/z=-48〜48、y=60〜81 のブロック・落ちている物・持ち物・位置・体力・死亡数・時刻・天候を復元する。地面の下に石があり、周囲は岩盤の壁。課題ごとに会話と目的実行器を作り直す。経験や記憶を持ち越す評価は行わない。会話側の DB と Discord への送信先は空に固定する。

## 自宅サーバーでの準備と小さな確認

手元のリポジトリの Python 環境で（PowerShell の例）：

```powershell
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py inspect
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py stage
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py body
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py conversation
# 以前の専用CPU構成を明示して試す場合
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py conversation --llm-service dedicated
# 別の課題を1回試す
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py body --task stone_pickaxe
# 状態・結果の取得、終了
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py status
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py pull
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py stop
```

接続先は既存の `scripts/server/.env.local` または `CIEL_SERVER_HOST`・`CIEL_SSH_KEY`。`inspect` は状態確認、`stage` はコードを `~/work/ciel-companion-benchmark/server` へ配置する。本番・開発用の会話サーバーは再起動しない。

`stage` は自宅サーバーの既存 `.env.minecraft` に `MINECRAFT_EULA=TRUE` がある場合だけ、その同意を同じマシンの試験用サーバーにも使う。無ければ止まる。試験用の RCON パスワードは別に生成し、既存の `.env.shared` は参照するだけで書き換えない。ローカル LLM の重みのファイル名を `CIEL_BENCH_MODEL_ID` に記録する。別の重みを使う場合は、配置先の `.env.benchmark` の識別名も合わせて変更する。

`body`・`conversation` はそれぞれ必要なイメージをビルドし、`gather_logs`・配置11・1回の小さな試験を行う。helperも課題別の実用期限を使う。まず1回だけ試し、全課題・反復へ進む前に不進行や操作未発行を調べる。失敗も採点結果なので終了コード1。イメージ作成・Minecraft起動はrunner開始前の環境準備で、別に時間がかかる。

会話モードの既定はシエルと共用するGPU併用API（8094、1要求32,768トークン・同時2枠）と既存Irodori（8766）。helperは共有APIのGPUモード・準備完了・実コンテキストを確認し、追加モデルを起動しない。未起動・容量不足をCPUへの自動切替で回避しない。共通サービスの構成・性能測定・他ホストからの接続は [共通GPU API](../../operations/shared-llm-api-ja.md) を参照する。

`--llm-service dedicated` の場合だけ従来の専用CPUモデル（8096、32,768トークン・1枠）を起動する。helperは選んだサービスに対応する接続先・制御先をComposeへ渡す。手動実行は `.env.benchmark` の `CIEL_BENCH_LLM_SERVICE`・`CIEL_BENCH_LLM_URL`・`CIEL_BENCH_LLM_CONTROL` を揃える。旧ファイルの8096設定は `stage` で上書きしないため、共有へ移る際に変更する。

runnerは `manifest.inference_server` に実際のモード・モデル・1要求あたりのコンテキスト・同時枠を保存し、容量不足ならワールドの初期化前に拒否する。共有先で歌の分析が始まると通常どおりCPUモードへ切り替わるため、開始時情報だけで試行中ずっとGPUだったと判断しない。速度比較では他クライアントの要求・音声合成・キャッシュ条件も記録する。

ローカル試験モードでは自己画像も送り込まず、Qwenが受け付けるようsystemの補足を先頭の1件へまとめる。元の会話と道具呼び出しの順序は変更しない。

## 自宅サーバーで課題を選んで実行する

配置先の `~/work/ciel-companion-benchmark/server` で：

```sh
docker compose --env-file .env.benchmark -f compose.benchmark.yaml --profile runner build body-bench benchmark-runner
docker compose --env-file .env.benchmark -f compose.benchmark.yaml up -d minecraft-bench body-bench

# 課題の一覧（起動済み Minecraft は不要）
docker compose --env-file .env.benchmark -f compose.benchmark.yaml --profile runner run --rm --no-deps benchmark-runner --list

# 目的・体だけを全課題で評価
docker compose --env-file .env.benchmark -f compose.benchmark.yaml --profile runner run --rm --no-deps benchmark-runner --mode body

# 試行数を絞る。--task と --seed は複数指定できる
docker compose --env-file .env.benchmark -f compose.benchmark.yaml --profile runner run --rm --no-deps benchmark-runner \
  --mode body --task stone_pickaxe --seed 11 --repeats 1
```

会話モードは先に専用の会話サーバーを作る：

```sh
# .env.benchmark は shared / 8094 / 制御8095を指定する
# 共通APIはベンチマークとは別に起動済みであること
curl -f http://127.0.0.1:8094/health
docker compose --env-file .env.benchmark -f compose.benchmark.yaml --profile conversation up -d --build agent-bench
docker compose --env-file .env.benchmark -f compose.benchmark.yaml --profile runner run --rm --no-deps benchmark-runner \
  --mode conversation --task gather_logs --seed 11 --repeats 1
```

各試行は新しい LiveKit の部屋へ `ciel-task-bench` を明示して接続する。要求の版・backend・モデル識別名・試行IDを dispatch metadata（`ciel.benchmark` v1）で照合し、不一致や旧形式は**推論前に拒否**する。さらに会話ログの同じ情報と人物設定のハッシュを確認してから課題を送る。更新時は `agent-bench` と `benchmark-runner` の両方を再ビルドする。

試験モードでは初回あいさつを生成せず、`benchmark_ready` を確認してから課題を送る。初回あいさつと依頼の長い推論が競合することを防ぎ、課題の入力を計測の入口にそろえる。通常の会話のあいさつは変更しない。

OpenAI と比較する場合は `.env.benchmark` の `CIEL_BENCH_BACKEND=openai` とモデル識別名を設定し、agent-bench を再作成する。実行にも `--backend openai --allow-paid` が必要。必要なら `CIEL_MIND_MODEL` 等を明示する（各役目の実際のモデル名はログに残る）。ローカルモードでも LiveKit の利用は発生する。公開 Web 検索・画像・音声認識は、先に作ったローカル試験モードと同じ制限になる。

Python 3.11以降と `server/agent/requirements-test.txt` があるホストなら、`server/` から `python -m benchmark.run ...` でも実行できる。設定は `.env.benchmark`、会話モードでは加えて `.env.shared` を読み、環境変数が優先する。

## 採点と結果

**エージェントの完了通知を合否の根拠にしない。** 評価器だけが RCON を使い、Minecraft サーバーが保持する持ち物・位置・体力・死亡数を取得する。RCON の資格情報や採点用コマンドはエージェントの道具に渡さない。採集・製作は開始時からの対象アイテムの増加数で成功を決める。

課題別の期限は原木・木のつるはし・材料補充90秒、石のつるはし・遠方探索120秒、不能な材料条件での報告・停止60秒。初回操作30秒、不進行30秒（遠方探索45秒）、同じ理由の失敗2回、継続不能後の報告待ち10秒でも終了する。`--seconds` は短くする上限であり、900を指定しても課題の期限を延長しない。詳しい進捗・報告・停止の判定は [practical-v1](minecraft-benchmark-ja.md) を参照する。

実行全体は既定 `--run-seconds 600`、3連続失敗でも後続を停止する（`--failure-streak 0` で解除可能）。全体予算には課題準備・終了処理も含み、終了用に20秒を確保する。準備最大45秒、切断と体解放確認は各最大10秒。全体の時間切れは `budget_exhausted`、連続失敗の打ち切りは `stopped_early`。予算中断・未実施は `skipped` で合否の分母から除外し、全条件測定済みと扱わない。LLM要求30回・ゲーム要求80回も上限として維持する。

持ち物の条件を満たした時刻を `time_to_goal_seconds` に記録し、その後は既定5秒まで目的のdone・シエルの返答を観測する（`--report-grace`）。`completion_observed` は体モードでは目的のdone、会話モードでは条件成立後の中断されていない返答を確認できたかを示す。返答の意味が正しいという判定ではない。`elapsed_seconds` はこの観測待ちも含む。返答が間に合わなくても持ち物の成功は保持し、回数予算の超過は失敗にする。

結果は `server/benchmark/data/results/<実行時刻>/`：

| ファイル | 内容 |
|---|---|
| `report.json` | format 2・policy、実行モード、モデル識別名、Gitとコード/課題ハッシュ、実効予算、予定数・打ち切り理由、期待行動の合格率、目的達成数・適切な停止数・未完了/未実施数 |
| `report.md` | 課題別の成功率と環境障害数 |
| `<課題>-s<配置>-r<回数>/result.json` | 初期・最終状態、観測できた中間到達、停止時間、誤った目的完了、呼び出し数、失敗理由、修復・再試行数、トークン・料金の記録 |
| 同 `trace.jsonl` | 復元した配置、RCON観測、目的の状態、MCPの要求と結果、会話サーバーのイベント |

中間到達は定期観測で確認できた物だけ。瞬時に作って消費した材料を見逃す場合があるため、完全な達成率とは扱わない。`foreground_generation_seconds` は完了した返答ストリームの待ち時間の合計で、裏の推論や実行との重なりは含めた内訳にならない。途中で予算が尽きた推論の全時間は記録されない。

`false_goal_done` は目的実行器が done を出したのにアイテム条件が成立していない場合。自然文の「できました」などは `completion_claim_candidates` に候補を残し、単純な文字列一致だけで虚偽と採点しない。料金・トークンの使用量が届かなければ `null` で、0と断定しない。

停止課題は最初の取得後、停止の応答を5秒まで待ち、その後5秒の静止を確認する。応答後の位置・持ち物の変化、動作の再要求は失敗。停止が届く前に64個を集め終えた場合も失敗になるため、この課題には推論の遅延も影響する。通常の達成課題とは分けて読む。

終了コードは全成功0、課題の失敗1、準備・観測・後片付けなどの環境障害2。環境障害は成功率の分母から除外して別に報告し、発生した時点で後続の試行は止める。比較前に障害を解消する。

`manifest.completion` が `complete` になることも確認する。試行を採点できても、リース解放など最後の処理が失敗した場合は試験全体を `infrastructure_error` にし、実行全体のエラーを記録する。モデルの呼び出し自体が失敗した場合も `model_error` を記録して環境障害として止め、単なる未達成と区別する。

会話モードのCLIは、`run()` の結果保存・接続解除・リース解放を終え、出力をflushした後、実際の終了コード（0/1/2）でプロセスを終了する。LiveKitの [Python終了時のネイティブ競合の報告](https://github.com/livekit/python-sdks/issues/833)への回避策で、Pythonの終了時フックを通さない。試行の異常やcleanupの失敗を成功へ変換するものではない。体モードとライブラリとして呼ぶ `main()` は通常の終了を使う。

## 課題を追加する

まず、依頼文、初期条件、期待する実状態、制限時間、何の失敗を検出するかを決める。採点器には答えの条件を持たせるが、エージェントには通常の依頼と観測・道具だけを渡す。偶然成功する配置だけを選ばず、既存課題の意味を維持したまま別IDで追加する。

### 既存の採集・製作の範囲で追加する

`server/benchmark/tasks.json` の `tasks` に一意な `id` を追加する。たとえば既存の原木採集を16個にした課題は次の形になる（追加例であり、初版の6課題には含めていない）：

```json
{
  "id": "gather_logs_16",
  "prompt": "オークの原木を16個集めてください。",
  "item": "oak_log",
  "count": 16,
  "spec": {"make": "oak_log", "count": 16},
  "inventory": {},
  "forest": "many",
  "milestones": ["oak_log"]
}
```

| フィールド | 現在の意味 |
|---|---|
| `id` / `prompt` | 結果と選択に使うID / 会話モードに送る日本語の依頼 |
| `item` / `count` | 開始時からの持ち物の増加で判定する対象 / 必要な増加数 |
| `spec` | 体モードの目的。`{"make": "アイテム名", "count": 1}`。省略すると `item` / `count` から同じ形を作る。採集対象もこの目的形式で渡す |
| `action` | 既存課題に記載されているが、現在の `BodyDriver.submit()` は読み取らない。課題追加では `spec` を使い、ここへ新しい操作を書くだけで実行できると扱わない |
| `inventory` | 開始時に与えるアイテムと個数。現在は各1〜64個 |
| `forest` / `surface` | `near` / `far` / `many` / `none`。未知の値は拒否する。地表は `grass_block` または `sand` |
| `budget` | `seconds`、`first_action`、`no_progress`、`same_failure`、`blocked_grace`、`stop_grace`。省略項目は実用性ポリシーの既定値 |
| `modes` / `expected_outcome` | 対応モード、省略時は両方。期待行動は `achieve` または `report_unavailable`。後者は木材・所持品なしで石のつるはしが作れない専用oracleだけに対応 |
| `milestones` | 中間到達として観測するアイテム。採点条件の代わりではない |
| `stop_prompt` / `stop_after_gain` | 停止課題専用。取得増加を検出した後に送る停止依頼 / その閾値 |

体モードの解釈は `BodyDriver.submit()`、JSON の読込は `load_tasks()` を確認する。読込時のチェックだけでは課題の実現可能性は保証されない。初期所持品で条件が既に満たされたつもりになっていないか、資源が十分か、道具にその操作があるかを確認する。

### 地形・採点条件を拡張する

| 変更 | 主な実装先と確認点 |
|---|---|
| 新しい資源・障害物・初期条件 | `server/benchmark/world.py` の `World.reset()`。配置を seed から再現し、各試行で片付く専用領域に収める |
| 持ち物以外の到達条件 | `World.snapshot()` と `achieved()`、`server/benchmark/run.py` の `evaluate()`。停止課題は別の分岐がある。独立した実状態で判定し、切断・観測失敗は失敗として伝える |
| 新しい入力・操作の形式 | `server/benchmark/drivers.py`。体と会話で同じ課題の目的になるようにする |
| 新しい指標 | `server/benchmark/report.py`、結果・集計・この文書。失敗や環境障害を含め指標の意味を定義する |

既存の識別印・排他リース・初期化前のチェックを保つ。仕様を変えたら課題ファイルと評価器の差分を保存する。`tasks.json` の `version: 1` は現在の読込形式であり、課題追加のたびに増やす評価番号ではない。形式を変える場合は読込側も更新する。実行には suite/source のハッシュが残るが、比較の説明にも変更点を書く。

採点・復元・集計のコードを変えたら `server/agent/tests/test_minecraft_benchmark.py` に、成功例に加えて未達成、初期所持品、境界条件や観測失敗など変更に関係するケースを追加する。JSON だけの変更では、まず資源・条件の整合性と実機での成立を確認する。

リポジトリ直下からオフライン確認：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s server/agent/tests -p test_minecraft_benchmark.py
# 課題一覧（Minecraft接続なし）
Push-Location server
..\.venv\Scripts\python.exe -m benchmark.run --list
Pop-Location
```

続いて `stage` 後に新課題を1配置・1回で実機確認し、条件成立と失敗理由が trace に残ることを確認する。その後、既存課題を含めて比較する。失敗を直す目的で採点条件を緩めた場合は、実行品質の改善とは分けて報告する。

## 変更前後の性能を評価する

### 比較条件を固定する

最初に基準版と変更版、改善したい指標を決める。各版を `stage` して必要な専用サービスを再ビルドし、別の出力先で測る。体・モデル・プロンプトのうち何を変えたかを明記する。試験中の `stage` や同じ専用ワールドでの並列実行は避ける。

| 揃える条件 | 記録する内容 |
|---|---|
| 課題と配置 | 同じ課題集合・依頼文・配置 seed・反復数、同じ復元・採点仕様 |
| 予算 | `--seconds`、`--max-llm`、`--max-calls`、`--report-grace`。比較の途中で失敗した版だけ延長しない |
| モデルと推論 | backend、重み・量子化、役目ごとのモデル、コンテキスト長、同時実行数。モデル比較なら変更した設定を記録 |
| 実行環境 | CPU/GPU、他サービスの負荷、LLM の入力キャッシュが温まっていたか。冷間・温間の試行を混ぜて速度向上と結論づけない |
| コードと設定 | Gitコミット・dirty、source/suite のハッシュ、人物設定のハッシュ。dirty の場合は再現用の差分も保存 |

キャッシュ・負荷の制御と記録は現時点では自動化されていない。速度を比較するなら、両版で同じ予備実行をしてから計測する等の条件を明記する。実行順の影響が疑われる場合は順番を入れ替えて測る。

helperの `body` / `conversation` は1課題・配置11・1回だけ。全課題は上の「自宅サーバーで課題を選んで実行する」に従い、配置先でrunnerを起動する。既定は配置11・1回。複数配置・反復数・全体予算は明示し、打ち切った実行を全課題の測定済み結果にしない。比較でOpenAIを使う場合は有料実行の明示指定を行い、依頼の範囲で実行する。

### 結果を読む

1. 両版とも `manifest.completion == complete` で、予定した課題・seed・反復が揃ったことを確認する。環境障害は別計上し、不足した試行を残したまま全体性能を断定しない。
2. 同じ `(モード, 課題ID, seed, 反復番号)` の試行を対応させる。課題別に成功数/有効試行数と環境障害数を示す。総合成功率だけで小さい課題の悪化を隠さない。
3. `false_goal_done`、停止課題の安定性、ゲーム要求・LLM要求、失敗理由も比較する。体モードの `needs_mind` は、その範囲では自律完結できなかった結果として読む。
4. 時間は両版が成功した対応試行の `time_to_goal_seconds` を中心に比較し、中央値と範囲、件数を示す。失敗・時間切れ件数は別に載せる。成功した試行だけが減って速く見える比較を避ける。
5. `completion_observed` と観測待ちを含む `elapsed_seconds` は別に読む。ローカルCPU推論の速さを会話のリアルタイム性の検証に置き換えない。使用量 `null` は料金0ではない。

停止課題は推論の遅延で停止前に集め終わる場合があるため、通常の採集・製作と分けて比較する。少数試行は傾向の確認として報告し、単発成功から性能改善を断定しない。現時点で比較表の自動生成や統計的有意差の検定は実装していない。

### 失敗を次の課題へ戻す

失敗 trace を保存し、原因を切り分けてから、最小限の再現課題を追加する。課題追加後は基準版・変更版を同じ新しい評価器で測る。採点・資源配置・依頼文を変えた前後の結果は、そのまま性能差として比較しない。

調整用の課題・配置と、最後に評価する未使用の配置・依頼を別の一覧で管理する。現在の runner に専用の学習/評価分割機能はないので、課題IDと seed を明示して実行する。評価用の失敗を修正に使ったら、以後は調整用として扱い、新たな未使用の評価条件を用意する。

比較記録は結果の隣などに次を残し、文書へ転記する際は資格情報やユーザーの会話を含めない：

```text
目的・仮説:
基準版 / 変更版（コミット・差分）:
変えたモデル・プロンプト・体の設定:
モード / 課題ID / seed / 反復 / 予算:
環境・キャッシュ条件 / 調整用か未使用評価用か:
両版の結果の保存先・source/suite ハッシュ:
課題別の成功数/有効試行数・環境障害数:
誤完了・停止・要求回数・対応する成功試行の到達時間:
改善・悪化・失敗例とその根拠:
未実施の範囲・次に追加する課題:
```

取得後は専用サービスを停止する。結果は `.gitignore` 対象なので、ファイルの保存先と要点を引き継ぎ、Gitへのコミットだけで結果も保存されたと扱わない。

## 専用環境の識別と終了

プロジェクト名は `ciel-minecraft-benchmark`。Minecraftは25566、RCONは25576、体のWebSocketは8772、MCPは8773、目は3008、会話サーバーの状態確認は8092、専用LLMは8096（切替口8097）。すべてループバック。試験プレイヤーは既存のデバッグ方針に合わせた `Ciel_Debug`。手元Wikiは既存のデータを読み取り専用で参照し、別の場所にある場合は `CIEL_BENCH_KNOWLEDGE_DIR` を設定する。

採点器は専用ワールドの識別印 `ciel-benchmark-v1` を確認し、排他的な試験用リースを取得してから復元する。接続が切れた状態や形式不正を「所持数0」や成功に置き換えない。前の会話が体を離し、動作が終わるまで次の復元を待つ。後片付けに失敗したらリースを残して止める。

```sh
docker compose --env-file .env.benchmark -f compose.benchmark.yaml --profile conversation --profile runner --profile local down
```

これは専用プロジェクトだけを止める。結果と試験用ワールドは残る。実行の強制終了でリースが残った場合は、先に専用の会話サーバー・体を停止して実行が残っていないことを確かめ、その専用 Minecraft だけで `data remove storage ciel_benchmark:meta active` を実行してから再開する。

初版は固定した平坦な試験場での回帰評価。未知の自然地形、長期の自律探索、経験の持ち越し、創作物の評価は今後の追加対象。



## 実用性評価 practical-v1

### 課題と期限

| 課題 | 依頼からの上限 | 初回の操作・観察 | 不進行の上限 |
|---|---:|---:|---:|
| 原木8個・木のつるはし・不足材料の補充 | 90秒 | 30秒 | 30秒 |
| 石のつるはし | 120秒 | 30秒 | 30秒 |
| 遠くの原木の探索・採集 | 120秒 | 30秒 | 45秒 |
| 採集中の停止 | 90秒 | 30秒 | 停止指示前30秒 |
| 木がない砂漠での報告・停止 | 60秒 | 30秒 | 30秒 |

初回推論・共有APIの待ち時間も利用者が待つ時間なので時計を止めない。CPUだからという理由で期限を自動延長しない。`--seconds` は課題の期限を短くする上限で、900を渡しても石のつるはしは120秒のまま。ダイヤの採掘など複雑な課題を追加するときは、課題JSONの `budget.seconds` に別の期限を根拠付きで設定する。

### 早期終了

- `first_action_timeout`：30秒以内に操作・観察を発行しなかった。道具名を文章に書くだけでは発行に数えない。
- `no_progress`：所持数の最高値、または初めて入った2ブロック単位の場所が増えない。同じ場所の往復、同じ観察、モデル要求・返事の追加では時計を戻さない。移動を続けても課題全体の期限は延びない。
- `repeated_failure`：同じ操作・引数が同じ理由で2回失敗した。同一の非同期失敗の再通知は重複計上せず、実状態に進捗があれば反復失敗数をリセットする。
- `cannot_continue_without_report`：作業がneeds_decision/failed/cancelledのまま、10秒以内に報告も復帰もできなかった。体だけでは `needs_mind`・`body_cannot_continue` が先に確定する場合がある。
- `false_completion`：作業がsucceededでも実物の条件を満たしていない。自然文の「できた」も成功の代用にしない。
- `time_budget`：課題全体の期限までに完了しなかった。

停止課題は、最初の原木取得を確認してから停止を依頼する。応答まで5秒、応答後にさらに5秒の位置・所持品の安定と再開なしを確認する。安定観測は5秒の応答期限とは別枠。終了の監視間隔は0.5秒なので、その程度の幅はある。

持ち物による成功後の返答観測は既定5秒。返答の観測がなくても実物の成功は維持し、報告の有無は `completion_observed` として分ける。

### 実行全体を止める

既定はseed 11・各1回。体6試行、会話7試行。最初から3配置×3回を自動では実行しない。

`--run-seconds 600` が実行全体の既定予算。API状態確認・課題の準備・終了処理を含む。新しい試行の前に安全な終了用の20秒を確保する。準備は最大45秒、切断と体の解放確認は各最大10秒。最後のRCON解放などの通信待ちは追加で数秒かかる場合がある。イメージのビルド・Minecraft起動はrunner開始前の環境準備なので別枠。

3回連続で失敗したら `stopped_early` で後続を止める。`--failure-streak 0` で解除できるが、全体時間予算は残る。`--run-seconds` の指定上限は3,600秒。全体予算切れは `budget_exhausted`。全体予算で中断した試行と未実施分は `skipped` にして合否の分母から除外し、測定済みとは扱わない。全条件を終えた `complete` と区別する。

準備・観測・終了処理の障害は課題失敗に混ぜず、環境障害として後続を止める。安全確認や排他リースを無視して次のワールド初期化へ進まない。終了コードは全期待行動合格0、課題失敗/早期打ち切り1、環境障害2。

### 材料不足を報告して止まる

新課題 `stone_pickaxe_unavailable` は会話専用。復元した閉じた試験領域の床を砂にし、木・所持品・落ちた材料を置かない。木材を得られず石のつるはしを製作できないことを評価器が把握する。会話には「手近な材料で難しければ理由を説明して中止し、次の依頼まで待つ」という依頼を送る。

材料不足と製作断念を説明する、中断されていないassistant発言を保守的な日本語パターンで検出する。仮定の説明は除外する。加えて、未完了の道具要求・非同期作業がなく、目的も実行中ではなく、所持品と位置が5秒安定し、再開していないことを確認する。文章だけで止まったと判定しない。

合格は `reported_unavailable_and_stayed`、`outcome=appropriate_stop`・`objective_achieved=false`。製作成功には数えない。材料のある課題で同じ断念をした場合は `agent_declined_feasible_task` で失敗。報告後に再開すれば `resumed_after_decline`。静止だけで報告がない場合も合格しない。

この検出は一般的な文章の意味を評価するLLM judgeではなく、同義表現を取りこぼす可能性がある。`decision_evidence` とtraceを残し、表現を監査できるようにする。パターンや観測窓を変えたら評価条件の変更として両版を測り直す。

### 結果と比較

不能条件のoracleは現在、木材・初期所持品がない領域での石のつるはし製作だけを検証済み。砂の採集など、資源が存在する目的に `report_unavailable` を付けて合格させることは読込時に拒否する。新しい不能理由は復元とoracleの裏付けも追加する。

manifestはformat 2・policy `practical-v1`。課題ごとの実効予算、全体予算、予定数、終了理由、実行時間を保存する。各試行には初回操作時刻・最後の進捗時刻・報告の証拠・期待行動を保存する。

集計は `objectives_achieved`（製作・採集・停止の達成）、`appropriate_stops`（不能な課題での適切な断念）、`reported_stops`、失敗、環境障害、未完了/未実施を分ける。表示の合格率は課題の期待行動に対する率であり、製作成功率と同一ではない。

旧900秒条件の詳細はGit履歴から参照する。新しい期限、断念課題、停止期限、実行打ち切りを導入したため、旧スコアと直接比較して改善したとは言わない。

## 現在の確認範囲

直近の評価値・条件・生データの参照先は[確認状況](../../testing/verification-status-ja.md)が正本。測定条件を変えた評価を過去の値と直結せず、実装・モデル・課題・キャッシュ・共有負荷を揃える。日付付きの測定報告を新設せず、この仕様と確認状況を更新する。
