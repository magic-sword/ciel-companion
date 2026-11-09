# Minecraft タスクのベンチマーク

2026-11-09。入口は `server/benchmark/run.py`、課題は `server/benchmark/tasks.json`。自宅サーバーで専用の Minecraft・体・試験用会話サーバーを使う。普段のワールドや DB は復元・変更しない。

Codex・Claude Code の作業手順は [共通の評価スキル](../.agents/skills/ciel-minecraft-benchmark/SKILL.md)。この文書を設定・採点・拡張方法の正本とする。ローカル推論の切替は [ローカル LLM](local-llm-ja.md)を参照する。

初版のスモーク試験の範囲は末尾の「実機で確認した範囲」にある。その後の [基準測定](minecraft-benchmark-baseline-2026-11-09-ja.md)では体・ローカル会話を各54有効試行で測定済み。成功率は体83.3%・会話48.1%。環境障害2件の補完、キャッシュ区間、到達時間、失敗の履歴は基準測定の文書を参照する。

## エージェントからの入口

- リポジトリ直下の `AGENTS.md` が共通案内、`CLAUDE.md` がその参照口。
- Codex 用のスキル本体は `.agents/skills/ciel-minecraft-benchmark/SKILL.md`。配置は [公式のローカルスキル仕様](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)に合わせている。
- Claude Code 用の `.claude/skills/ciel-minecraft-benchmark/SKILL.md` は共通スキルを読む入口。作業手順の更新は共通スキルへ行い、仕様やコマンドはこの文書を更新する。
- 稼働中のワールド固有の不具合調査は `ciel-minecraft-debug`。再現課題の評価には本ベンチマークを使う。

## 何を比較するか

| モード | 入力 | 評価する範囲 |
|---|---|---|
| `body` | 構造化した目的 | 既存の GoalRunner → GoalsAdapter → MCP → 体。LLM を呼ばない。心の判断が必要になったら `needs_mind` で失敗 |
| `conversation` | 課題の日本語の依頼を `lk.chat` へ送る | 普段の pipeline による解釈・道具選択・目的実行。ローカル LLM が既定。Irodori の読み上げ・LiveKit も使う |

[MineDojo の課題設計](https://docs.minedojo.org/sections/core_api/sim.html)にある初期条件・資源・技術ツリーの考え方と、[Voyager](https://github.com/MineDojo/Voyager)の段階的な到達・失敗からの修正を参考にした。環境・行動単位・Minecraft の版が違うため、論文のスコアと直接比較するものではない。

## 初版の6課題

| ID | 目的・初期条件 |
|---|---|
| `gather_logs` | 素手でオークの原木8個。近くに原木がある |
| `wooden_pickaxe` | 持ち物なしで木のつるはし1本 |
| `stone_pickaxe` | 持ち物なしで石のつるはし1本 |
| `replenish_materials` | 木のつるはし・作業台・棒2本から、不足する丸石を集めて石のつるはし1本 |
| `find_logs` | 近くに原木が無い状態から、探して8個集める |
| `stop_collecting` | 原木64個の採集中、最初の取得を確認したら停止を指示。停止の応答と、その後10秒の持ち物・位置の安定、再実行の有無を確認 |

原木は固定した配置の丸太で、自然生成の木・戦闘・食料管理・精錬は初版の対象外。世界の seed は `771023`。`--seed` は**ワールド生成の seed ではなく、原木配置の seed**で、既定は11・29・47。同じ配置で既定3回ずつ繰り返す（6課題×3配置×3回＝54試行／モード）。

毎回、専用領域 x/z=-48〜48、y=60〜81 のブロック・落ちている物・持ち物・位置・体力・死亡数・時刻・天候を復元する。地面の下に石があり、周囲は岩盤の壁。課題ごとに会話と目的実行器を作り直す。経験や記憶を持ち越す評価は行わない。会話側の DB と Discord への送信先は空に固定する。

## 自宅サーバーでの準備と小さな確認

手元のリポジトリの Python 環境で（PowerShell の例）：

```powershell
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py inspect
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py stage
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py body
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py conversation --seconds 600
# 別の課題を1回試す
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py body --task stone_pickaxe --seconds 600
# 状態・結果の取得、終了
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py status
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py pull
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py stop
```

接続先は既存の `scripts/server/.env.local` または `CIEL_SERVER_HOST`・`CIEL_SSH_KEY`。`inspect` は状態確認、`stage` はコードを `~/work/ciel-companion-benchmark/server` へ配置する。本番・開発用の会話サーバーは再起動しない。

`stage` は自宅サーバーの既存 `.env.minecraft` に `MINECRAFT_EULA=TRUE` がある場合だけ、その同意を同じマシンの試験用サーバーにも使う。無ければ止まる。試験用の RCON パスワードは別に生成し、既存の `agent/.env` は参照するだけで書き換えない。ローカル LLM の重みのファイル名を `CIEL_BENCH_MODEL_ID` に記録する。別の重みを使う場合は、配置先の `.env.benchmark` の識別名も合わせて変更する。

`body`・`conversation` はそれぞれ必要なイメージをビルドし、`gather_logs`・配置11・1回の小さな試験を行う。上限は既定240秒で、上の会話モードの例では600秒に延ばしている。失敗も採点結果なので終了コード1になる。初回のイメージ作成・Minecraft 起動には時間がかかる。

会話モードは、専用のローカル LLM（8096、CPU、コンテキスト32,768、同時実行1）と既存 Irodori（8766）を使う。重みは読み取り専用で共有し、既存ローカル LLM（8094）の設定・プロセスは変更しない。CPU なので長い指示の読み込みに数分かかる。LLM の要求タイムアウトは既定600秒で、試行の時間枠と合わせて設定する。比較時は他の利用が落ち着いた状態にする。

実機確認では、通常の会話と道具を含む要求が17,877トークンあり、既存モデルの入力上限12,288を超えたため専用サービスを設けた。ローカル試験モードでは自己画像も送り込まず、Qwen が受け付けるよう system の補足を先頭の1件へまとめる。元の会話と道具呼び出しの順序は変更しない。

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
  --mode body --task stone_pickaxe --seed 11 --repeats 1 --seconds 600
```

会話モードは先に専用の会話サーバーを作る：

```sh
docker compose --env-file .env.benchmark -f compose.benchmark.yaml --profile local up -d --build llm-bench
# 200になったことを確認してから会話側を開始する（読み込み中は503）
curl -f http://127.0.0.1:8096/health
docker compose --env-file .env.benchmark -f compose.benchmark.yaml --profile conversation up -d --build agent-bench
docker compose --env-file .env.benchmark -f compose.benchmark.yaml --profile runner run --rm --no-deps benchmark-runner \
  --mode conversation --task gather_logs --seed 11 --repeats 1
```

各試行は新しい LiveKit の部屋へ `ciel-task-bench` を明示して接続する。要求の版・backend・モデル識別名・試行IDを dispatch metadata（`ciel.benchmark` v1）で照合し、不一致や旧形式は**推論前に拒否**する。さらに会話ログの同じ情報と人物設定のハッシュを確認してから課題を送る。更新時は `agent-bench` と `benchmark-runner` の両方を再ビルドする。

試験モードでは初回あいさつを生成せず、`benchmark_ready` を確認してから課題を送る。初回あいさつと依頼の長い推論が競合することを防ぎ、課題の入力を計測の入口にそろえる。通常の会話のあいさつは変更しない。

OpenAI と比較する場合は `.env.benchmark` の `CIEL_BENCH_BACKEND=openai` とモデル識別名を設定し、agent-bench を再作成する。実行にも `--backend openai --allow-paid` が必要。必要なら `CIEL_MIND_MODEL` 等を明示する（各役目の実際のモデル名はログに残る）。ローカルモードでも LiveKit の利用は発生する。公開 Web 検索・画像・音声認識は、先に作ったローカル試験モードと同じ制限になる。

Python 3.11以降と `server/agent/requirements-test.txt` があるホストなら、`server/` から `python -m benchmark.run ...` でも実行できる。設定は `.env.benchmark`、会話モードでは加えて `agent/.env` を読み、環境変数が優先する。

## 採点と結果

**エージェントの完了通知を合否の根拠にしない。** 評価器だけが RCON を使い、Minecraft サーバーが保持する持ち物・位置・体力・死亡数を取得する。RCON の資格情報や採点用コマンドはエージェントの道具に渡さない。採集・製作は開始時からの対象アイテムの増加数で成功を決める。

既定の上限は1試行900秒・LLM要求30回・ゲームMCP呼び出し80回。`--seconds`・`--max-llm`・`--max-calls` で変えられる。回数の監視は0.5秒ごとなので、超過した呼び出しが始まる可能性はあるが、超過した試行を成功にはしない。準備と終了処理の呼び出しは予算から分ける。

持ち物の条件を満たした時刻を `time_to_goal_seconds` に記録し、その後は既定30秒まで目的の done・シエルの返答を観測する（`--report-grace`）。`completion_observed` は体モードでは目的の done、会話モードでは条件成立後の中断されていない返答を確認できたかを示す。返答の意味が正しいという判定ではない。`elapsed_seconds` はこの観測待ちも含む。返答が間に合わなくても持ち物の成功は保持し、回数予算の超過は失敗にする。

結果は `server/benchmark/data/results/<実行時刻>/`：

| ファイル | 内容 |
|---|---|
| `report.json` | 実行モード、モデル識別名、Gitコミット・変更の有無、コードと課題のハッシュ、予算、課題別成功率、各試行の結果 |
| `report.md` | 課題別の成功率と環境障害数 |
| `<課題>-s<配置>-r<回数>/result.json` | 初期・最終状態、観測できた中間到達、停止時間、誤った目的完了、呼び出し数、失敗理由、修復・再試行数、トークン・料金の記録 |
| 同 `trace.jsonl` | 復元した配置、RCON観測、目的の状態、MCPの要求と結果、会話サーバーのイベント |

中間到達は定期観測で確認できた物だけ。瞬時に作って消費した材料を見逃す場合があるため、完全な達成率とは扱わない。`foreground_generation_seconds` は完了した返答ストリームの待ち時間の合計で、裏の推論や実行との重なりは含めた内訳にならない。途中で予算が尽きた推論の全時間は記録されない。

`false_goal_done` は目的実行器が done を出したのにアイテム条件が成立していない場合。自然文の「できました」などは `completion_claim_candidates` に候補を残し、単純な文字列一致だけで虚偽と採点しない。料金・トークンの使用量が届かなければ `null` で、0と断定しない。

停止課題は最初の取得後、停止の応答を180秒まで待つ。応答後の位置・持ち物の変化、動作の再要求は失敗。停止が届く前に64個を集め終えた場合も失敗になるため、この課題には推論の遅延も影響する。通常の達成課題とは分けて読む。

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
| `forest` | 既存の配置は `near` / `far` / `many`。未知の値は現在の実装では近距離配置に入るため、新しい配置名を書くだけでは追加できない |
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

helper の `body` / `conversation` は1課題・配置11・1回だけ。全課題は上の「自宅サーバーで課題を選んで実行する」に従い、配置先で runner を起動する。課題・seed 未指定、`--repeats 3` なら初版は54試行／モード。会話側の時間上限と LLM 要求のタイムアウトも合わせる。比較でOpenAIを使う場合は有料実行の明示指定を行い、依頼の範囲で実行する。

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

## 実機で確認した範囲（2026-11-09）

自宅サーバーの専用ワールド、配置11、各1回の小さな確認：

| モード・課題 | 結果 | 記録 |
|---|---|---|
| body / gather_logs | 成功 | 原木8個をサーバー側で確認。全体約34.7秒、LLM要求0・ゲームMCP要求3 |
| conversation / gather_logs | 成功 | 原木8個を約51.9秒で確認。全体約82.1秒、LLM要求3・ゲームMCP要求1、記録されたモデル料金0ドル |
| body / stop_collecting | 成功 | 停止の確認まで約0.5秒、その後10秒の安定を確認。全体約15.8秒 |

この初期スモークの会話モードは Qwen3.5-35B-A3B-Q4_K_M のCPU実行で、入力キャッシュが温まった状態。これは性能比較の基準値ではない。完了後の返答は30秒の観測枠では確認できず、`completion_observed=false` として保存した。この時点では全課題・全配置・繰り返しは未実施で、その後の各54有効試行は [基準測定](minecraft-benchmark-baseline-2026-11-09-ja.md)に記録している。変更前後の改善を示す比較実験は未実施。

通常回帰テスト559件が成功。Minecraft側の既存テストは76件成功・1件スキップ（手元NodeのSQLiteにFTS5が無いため）。試験用コンテナは終了時に停止・削除し、結果と専用ワールドは保存した。本番のMinecraft・会話・ローカルLLMは更新・再起動していない。
