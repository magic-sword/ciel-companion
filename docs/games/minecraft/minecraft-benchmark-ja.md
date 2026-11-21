# Minecraft タスクのベンチマーク

> 責務：課題・practical-v1・採点・専用環境・実行・拡張・比較の方法。

入口は `server/benchmark/run.py`、課題は `server/benchmark/tasks.json`。自宅サーバーで専用の Minecraft・体・試験用会話サーバーを使う。普段のワールドや DB は復元・変更しない。

Codex・Claude Code の作業手順は [共通の評価スキル](../../../../agent-skills/skills/ciel-minecraft-benchmark/SKILL.md)。この文書を設定・採点・拡張方法の正本とする。ローカル推論の切替は [ローカル LLM](../../operations/local-runtime-ja.md)を参照する。

現在の終了条件は [実用性評価 practical-v1](minecraft-benchmark-ja.md)。課題別60〜120秒、操作未発行・不進行で早期終了し、既定は1配置・1回・実行全体10分。旧900秒条件の基準値とは直接比較しない。

測定結果・ソース指紋・保存先は[Minecraftの実測](../../testing/minecraft-results-ja.md)を参照する。会話受付・能力公開や採点条件が異なる版の値を、現在の性能として合成しない。内部操作の`work_action`と状態取得の`status_polls`も区別する。

## エージェントからの入口

再実行に必要なコードと設定はGitで管理する。対象は`scripts/server/benchmark-home.py`、`server/benchmark/`の実行器・採点器・`tasks.json`・`whitelist.json`・Dockerfile、`server/agent/benchmark_contract.py`と関連テスト、`server/compose.benchmark.yaml`・`server/.env.benchmark.example`、依存定義・ロックファイルと本手順書。結果を取得しただけのローカルファイルを実行の前提にしない。

`server/benchmark/data/`の実行結果・ログ・ソーススナップショット、実際の`.env.benchmark`・認証情報・専用ワールド・モデル重みはGit対象外。過去の測定IDや当時の構成に固定された調査用スクリプトも、この結果領域にあるものは現行の再実行手順に含めない。繰り返し必要な実行・集計処理は`scripts/server/`または`server/benchmark/`へ組み込み、手順書と一緒に追跡する。モデル・Minecraftイメージ等は、ここで指定する版・取得元とライセンスに従い各環境で準備する。

- リポジトリ直下の `AGENTS.md` が共通案内、`CLAUDE.md` がその参照口。
- 共通手順の正本は `../agent-skills/skills/ciel-minecraft-benchmark/SKILL.md`。Codexの `../agent-skills/skills/ciel-minecraft-benchmark/SKILL.md` は正本を読む入口。作業手順は正本へ集約し、仕様やコマンドはこの文書で管理する。
- 稼働中のワールド固有の不具合調査は `ciel-minecraft-debug`。再現課題の評価には本ベンチマークを使う。

## 評価の3段構成

Mindcraft移行後は、評価を3段に分けて原因を切り分ける。段ごとに別の値として報告し、掛け合わせた通しの成功率だけで判断しない。

| 段 | 入力 | 測るもの | 課題と採点 |
|---|---|---|---|
| 1. 体 | Mindcraftの英語の目標文を`body`でAgentへ直接渡す | 採集・製作・建築の達成度 | 目標・対象・個数・初期所持品はvendorのMindcraft課題定義、領域・期限・中間到達はCIEL。[Mindcraft定義の課題](#mindcraft定義の課題)を参照 |
| 2. 会話 | 日本語の文字の依頼 | 意図・権限の判断、Mindcraftへの受け渡し、停止・表示 | [依頼意図の受付](#遊んでいる間の発言の振り分け)、[対象候補の受付](#遊んでいる間の発言の振り分け)、`conversation`の実機課題 |
| 3. 音声 | 録音した指示 | 聞き取りの誤りが受付をどれだけ変えるか | 計画中・未実装。下記 |

CIEL固有の課題（指差し・目線・座標指定、保護物、停止・取消、整地・建築の施工、移動・追従）はMindcraftに対応する評価が無いため、第1段・第2段で従来どおり扱う。Mindcraftを上流の新しい版へ更新したときは、第1段の`mc_*`課題を新旧両版で測り、上流由来の変化として記録する。

第3段は、Minecraft向けの指示（アイテム名・個数・座標の数字・「そこ」などの指示語・言い直し）を録音したコーパスを用意し、[音声評価](../../testing/voice-benchmark-ja.md)の`stt`で文字にした結果を、正解文と並べて第2段の受付評価へ入力する。受付の判断が正解文と聞き取り結果でどう変わるかを比べ、Minecraftは動かさない。音声からゲームまでの通し実行は少数の動作確認に限り、成功率の評価には使わない。指差しと発話の時刻対応もこの段で扱う。コーパス・実行器は未作成。

## 何を比較するか

### 遊んでいる間の発言の振り分け

持ち主の発言で体が動くか、話すだけかは、`scripts/server/benchmark-intent-routing-home.py`で会話サーバーの一つの決定（`server/agent/game_decision.py`）を共有GPU APIで測る。操作は記録だけで、ワールドには発行しない。課題・条件・結果は[振り分けの実測](../../testing/minecraft-results-ja.md#雑談と依頼の振り分け)。以前の受付（`GameIntake`）の比較・指差しの受付の評価は、受付と一緒に2026-11-16に撤去した。

## 課題と評価モード

## 段階1（施工）の評価

範囲を指定した整地・建築・指差しの課題（`clear_small_area`・`build_floor`・`build_wall`などの施工8件、`point_move`・`point_recover`・`gaze_move`などの指差し8件、`s1_*`の段階1の12件）と、その採点（`spatial.py`・`stage1.py`・`audit.py`・`pointing.py`）は、CIEL独自の施工計画器と指した所への作業を前提にしていた。どちらも体から削除したため、課題・採点・指示棒を操作する評価用の手順（`owner.js`の指示棒操作、`pointing-home.py`）と一緒に2026-11-21に削除した。施工は今はMindcraftの`!buildStructure`と座標命令が受け持つ（[設計](minecraft-design-ja.md#主要タスクの拡張計画)）。それを測る課題は、今の命令に合わせて改めて作る。以前の課題と結果はGitの履歴と[Minecraftの実測](../../testing/minecraft-results-ja.md)にある。

## 既存の採集・製作・移動

| ID | 目的・初期条件 |
|---|---|
| `gather_logs` | 素手でオークの原木8個。近くに原木がある |
| `wooden_pickaxe` | 持ち物なしで木のつるはし1本 |
| `stone_pickaxe` | 持ち物なしで石のつるはし1本 |
| `gather_cobblestone` | 木のつるはしだけで丸石30個を採集し、開始位置から1ブロック以内へ持ち帰る。120秒、seed11、1回 |
| `replenish_materials` | 木のつるはし・作業台・棒2本から、不足する丸石を集めて石のつるはし1本 |
| `find_logs` | 近くに原木が無い状態から、探して8個集める |
| `stop_collecting` | 原木64個の採集中、最初の取得を確認したら停止を指示。5秒以内の停止応答、その後5秒の持ち物・位置の安定と再実行なしを確認 |
| `come_here` | 「シエル、こっちに来て」。約20ブロック先の持ち主へ接近し、3ブロック以内で2秒間、今回のcome命令の完了と停止を確認 |
| `follow_owner` | 「シエル、ついてきて」。持ち主を3地点へ順に移し、各地点3ブロック以内で追従中の2秒保持を確認。その後停止指示、5秒以内の停止と5秒間の安定を確認 |
| `go_to_coordinates` | X=20、Z=-12へ移動。1.5ブロック以内で2秒間、今回のgo_to命令の完了と停止を確認 |
| `stone_pickaxe_unavailable` | 木も所持品もない砂漠の専用領域。会話モードのみ。材料不足の理由を報告し、作業を止めて待てるかを評価。製作成功とは別に集計 |

原木は固定した配置の丸太で、自然生成の木・戦闘・食料管理・精錬は対象外。世界のseedは `771023`。`--seed` は**ワールド生成のseedではなく、資源配置のseed**。既定は11・各1回（課題の一覧は`--list`で確認する）。複数配置・反復は明示し、全体予算や連続失敗による未実施も記録する。

毎回、専用領域 x/z=-48〜48、y=60〜81 のブロック・落ちている物・持ち物・位置・体力・死亡数・時刻・天候を復元する。地面の下に石があり、周囲は岩盤の壁。課題ごとに会話と目的実行器を作り直す。経験や記憶を持ち越す評価は行わない。会話側の DB と Discord への送信先は空に固定する。

移動課題では専用の対象役`Bench_Owner`を追加し、採点器のRCONだけが位置を変える。対象役は試験用ワールドにだけ接続し、採集・製作課題では領域外に待機させる。追従の3地点は走行・回避全般の評価ではなく、停止した対象への追従先更新と継続を測る。

`benchmark/body-observer.js`は同じRunnerの状態と相手entityを200msごとに読み取り、別の移動ロジックは持たない。採点はRCONの位置・距離と、今回の命令の開始後に確定したbody状態を突き合わせる。古い完了や返答だけの約束では合格しない。初期化の位置通知が体へ届くまで最大5秒待ち、届かない場合は環境障害として停止する。

`benchmark/agent_observer.py`は元の会話エントリポイントを呼び、起動が5秒以上待つときだけタスクの関数名・行番号を記録する。依頼解釈のロジックは変更しない。以下の能力増加条件では、試験用の能力だけを追加する。

### Mindcraft定義の課題

第1段（体）の採集・製作は、vendorした上流の課題定義`server/minecraft/src/vendor/mindcraft/tasks/`から読む。取り込むファイルは`scripts/server/update-mindcraft-vendor.py`の`TASK_FILES`で指定し、上流の更新に追従する。`server/benchmark/mindcraft_tasks.py`が、目標文`goal`・対象`target`・個数`number_of_target`（省略時1）・初期所持品`initial_inventory`を課題へ展開する。tasks.jsonでそれらを上書きすることは拒否する。

| ID | 上流の定義 | 期限 | 中間到達 |
|---|---|---:|---|
| `mc_gather_oak_logs` | `basic/single_agent.json`の`gather_oak_logs`。木の斧から原木4個 | 90秒 | 原木 |
| `mc_crafting_oak_log` | `single_agent/crafting_train.json`の`crafting_oak_log`。原木1個 | 60秒 | 原木 |
| `mc_crafting_stick` | 同`crafting_stick`。棒4本 | 90秒 | 原木・板材・棒 |
| `mc_crafting_wooden_pickaxe` | 同`crafting_wooden_pickaxe` | 90秒 | 原木・板材・棒・作業台・木のつるはし |
| `mc_crafting_stone_pickaxe` | 同`crafting_stone_pickaxe` | 120秒 | 上記・丸石・石のつるはし |

採用条件は、1体用の`techtree`課題で、使用禁止の命令・不足アイテムの指定が無く、対象が単一アイテム、初期所持品に対象を含まないこと。上流の採点は持ち物の絶対数だが、この条件により開始時からの増加数で同じ判定になる。読み込みはこの条件を満たさない定義を拒否する。上流の`timeout`（300〜1000秒）は`result.json`の`upstream`へ記録するだけで、期限はpractical-v1で課題ごとに決める。

目標文は英語のままなので`modes`は`body`だけとし、会話モードへ使わない。日本語の依頼は従来の`gather_logs`・`wooden_pickaxe`・`stone_pickaxe`などで評価する。領域は専用アリーナ（近くの原木と地下の石）であり、上流の自由なワールドとは資源配置・期限が違う。MineCollabの公表値と直接比較しない。金インゴット・鉄のつるはし・盾は、鉱石を置く地形で次節の長い作業として扱う。銅・レッドストーン・ダイヤ、ハサミ・羊毛の上流課題はまだ採用していない（上流の配置には羊が無い）。羊毛はCIEL独自のベッドの課題で扱う。複数体の協力課題と人とAIの課題も対象外。

### 長い作業（long-horizon-v1）

依存関係の段が10を超える製作は、practical-v1の60〜120秒に収まらない。上流の定義を同じ方法で読み、別の評価条件`long-horizon-v1`で測る。課題の期限は121〜600秒、モデル要求の上限は80回、操作の上限は200回（practical-v1は30回・80回）。課題を`--task`で名指ししたときだけ実行し、practical-v1の課題と同じ実行に混ぜない（混ぜると拒否する）。結果はpractical-v1の値と直接比べない。期限は難易度に合わせ、実行器の段数×40秒（上限600秒）とする。上流の`timeout`は課題によらず一律の値なので使わない。精錬中は持ち物が増えないため、不進行の判定は60秒にする。

| ID | 上流の定義 | 初期所持品 | 鉱石 | 期限 | 実行器の段数 |
|---|---|---|---|---:|---:|
| `mc_long_gold_ingot` | `crafting_gold_ingot` | 鉄のつるはし | 金2・石炭2 | 320秒 | 8 |
| `mc_long_iron_pickaxe` | `crafting_iron_pickaxe` | 石のつるはし | 鉄4・石炭2 | 480秒 | 12 |
| `mc_long_shield` | `crafting_shield_missing_iron_ingot` | 板材7 | 鉄2・石炭2 | 600秒 | 15 |

`long_wheat_farm`はCIEL独自の課題で、目標は持ち物ではなくブロックの状態である（上流のMindcraftに農地の課題は無い）。依頼文は「Make a 3 by 3 wheat farm with water in the middle.」。
- **配置：** 地面は石で、農地にできる草地は3×3の1か所だけにする。場所を固定し、マスごとに読めるようにするためである。ほかに水を汲む2×2の池と、種を取る苔の上の草原（12×12）を置く。鉄3・石炭2の鉱石も置く。
  - 置く位置は配置seedで決め、木と反対側にする（`server/benchmark/farm.py`）。
- **採点：** 草地の周り8マスの小麦（y=64）と中央の水（y=63）をRCONで確かめ、9マスすべてで成功とする。
- **進捗と中間到達：** 正しいマスが増えたら進捗に数え、部分達成度は正しいマスの割合にする。中間到達は鍬・種・バケツ・水入りバケツまでの持ち物で数える。
- **期限：** 600秒・不進行60秒。節の期限の合計（約1000秒、節ごとの上限の和）は作業契約の上限600秒を超えるため、今は上限に合わせている。

ベッドの2課題もCIEL独自で、依頼文は「Craft a white bed.」、目標は白いベッド1個である。モブから入手する経路を測る。
- **`long_white_bed`：** 白い羊3匹。倒すだけでも足りる。期限280秒・不進行60秒。中間到達は原木・板材・作業台・白い羊毛・ベッド。
- **`long_white_bed_one_sheep`：** 白い羊1匹と鉄2・石炭1の鉱石。倒すと羊毛は1個なので、ハサミを作って刈る必要がある。期限600秒・不進行60秒。中間到達に丸石・鉄の原石・鉄インゴット・ハサミを加える。1回の刈り取りで3個出る確率は1/3で、多くの配置では毛が戻るのを待つ（平均約50秒）。
- **羊の配置：** 森の側の、中心から4〜14ブロック離れた位置に、配置seedで置く（`server/benchmark/world.py`）。色は白に固定する。召喚後に数をRCONで確かめ、終了時の数も記録する。
- **難易度：** アリーナはピースフルなので、敵対モブ（蜘蛛・エンダーマン）の課題はまだ置かない。

家の課題もCIEL独自で、依頼文は「Build a dirt shelter.」である。上流のNPCの建物の設計図（`src/agent/npc/construction/dirt_shelter.json`）を建てる。
- **配置**（`server/benchmark/house.py`）：
  - 地面は石で、草地は小屋と同じ5×6の1か所だけ。
  - 土は幅4の帯（建てられない幅）から取る。
  - 木は3本ずつ3列の9本（`dense_forest`）、鉱石は石炭6。拠点の近くにプレイヤーが見つける程度の資源にする。
  - 白い羊3匹は、アリーナの壁の先、幅4の小道の先の放牧地（中心から104ブロック以上）に置く。最初は64ブロック以内に羊が見えない。
  - `long_dirt_shelter`は鉄鉱石3を放牧地の地面に置く（`far_ores`）。ハサミで刈る方法を選んだとき、見えない鉄を探して使えるかを測る。
- **採点：** 草地に収まる向き（0度・180度）ごとに101マスをRCONで確かめ、多く合う向きで数える。
  - 土は`#minecraft:dirt`、松明は`torch`か`wall_torch`、ベッド・扉・板材は色や木の種類を問わない。
  - 全マスが合えば成功。部分達成度は合ったマスの割合。
- **オーナー：** 体が尋ねたら（作業が`needs_decision`で`decision.kind=question`）、台本のオーナーが2秒後に答える。
  - 答えは課題の`owner.reply`、既定は「Up to you.」。
  - `owner.say`の`after_command`の命令が初めて出たら、その言葉を実行中の作業へ渡す（`minecraft_task_say`）。
  - 質問の回数・オーナーの言葉・体の作業中の発話を数える。合否には使わない。
- **`long_dirt_shelter_keep_sheep`：**
  - 鉄3・石炭6を置く（家の近く）。
  - 最初の`!chooseOption`でオーナーが「Please don't kill the sheep. Shear them for the wool instead.」と言う。尋ねられたら「Please shear the sheep for the wool. I want to keep them.」と答える。
  - 家が完成し、羊が1匹も減っていなければ成功（`keep_mobs`）。
- **期限：** 評価条件`planned-work-v1`。会話の受け渡しと同じ120秒で依頼し、体の計画が見積もりで延ばす作業の期限（[作業契約](../game-work-contract-ja.md)、上限30分）で測る。課題の上限は1800秒・不進行60秒。long-horizon-v1の結果とは直接比べない。

鉱石は地表（y=63）に1個ずつ埋め、位置は配置seedで決める（x=−14〜14、z=±10〜16。木・出発点と重ならない）。鉱石を置かない課題の木の位置は変わらない。中間到達には初期所持品を含めない。

作業契約の1件の期限は最大600秒で、会話からの依頼は従来どおり120秒を求める。長い作業の評価は、課題の期限をそのまま作業の期限として体へ渡す。

#### 計画の実行器の有無を比べる

農地の課題で実行器を使わない体と比べるときは、`--blocked-action`を5回付けて`!obtainItem`・`!buildFarm`・`!sowFarmland`・`!buildStructure`・`!chooseOption`を禁止する。`--blocked-action '!obtainItem'`を付けると、専用環境の体だけで`!obtainItem`を使えなくする（`CIEL_MINDCRAFT_BLOCKED_ACTIONS`）。命令の一覧・製作計画の文・失敗文のヒントからも`!obtainItem`への案内が消え、`!getCraftingPlan`の計画は残る。manifestの`body_blocked_actions`に記録する。比べるのは「実行器あり」と「Mindcraftの1手ずつの選択（計画の照会あり）」で、上流そのままの体ではない。

1回の実行は3600秒までなので、3課題×3配置は2回に分ける（金と鉄で約2400秒、盾で約1800秒）。

```powershell
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py body --task mc_long_gold_ingot --task mc_long_iron_pickaxe --seed 11 --seed 12 --seed 13 --failure-streak 0 --run-seconds 3600
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py body --task mc_long_shield --seed 11 --seed 12 --seed 13 --failure-streak 0 --run-seconds 3600
# 実行器なしの版は、同じ2回に --blocked-action '!obtainItem' を付ける
.\.venv\Scripts\python.exe -m server.benchmark.arm_compare <実行器なしの結果> <実行器ありの結果>
```

温度0では同じ配置の繰り返しは同じ命令を選ぶため、繰り返し回数ではなく配置seedを増やす。`arm_compare`は課題と配置で試行を対にし、両方で採点できた試行だけを比べる。環境障害と未実施は失敗に数えない。

### 能力数の増加による選択性能

`conversation --distractors 0..100 --distractor-surface work|catalog|both`で、通常環境へ登録せずにダミー能力を追加できる。既定は0個。`work`は依頼受付に渡すwork能力、`catalog`はゲームサービスをロードした後の直接操作、`both`は両方に同数を追加する。100個・bothなら各面100個であり、合わせて100個ではない。

`benchmark/distractors.py`は精錬、農業、動物誘導、収納、建設、巡回など20種類×5対象の100定義を固定順で生成する。小さい条件は同じ一覧の先頭部分を使う。連番だけの無意味な道具名や「ダミー」と書いた説明は選択候補に見せない。通常の権限フィルター・段階的ロードを通し、選択された操作はワールドへ送信せず`benchmark_distractor`エラーにする。後で本来の目的を達成しても、ダミー操作を呼んだ試行は`distractor_selected`として失敗を記録する。

runnerのmanifestと会話側ログに個数、公開面、定義版、定義SHA256を記録し、一致しない場合は環境障害として拒否する。実際のwork能力数・直接操作数もログに残す。0個と100個の予備比較後、必要に応じ10・50個を測る。各条件で成功数、誤選択数、最初の操作までの時間、入力トークン、推論回数、RCONでの達成を比較する。同一モデル・課題・予算を保ち、採集と移動を別集計する。追加前から失敗する課題だけでは増加による劣化を評価できない。

```powershell
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py conversation --task gather_logs --distractors 100 --distractor-surface both
```

この試験は合成能力による競合の評価であり、追加機能の実行性能や将来の全ツール集合を保証しない。実装済みの課題文に加え、言い換え・否定・引用・質問・類似能力との境界、提示順、反復、長い会話での保持を別条件として評価する必要がある。参考PDF『Agent Skills』の21〜27ページが扱うトリガー・実行・回帰・共存時の評価を区別し、本資料の合格率へ他システムの数値を転用しない。

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
# 比較する課題だけを選ぶ。--taskは繰り返し指定できる
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py conversation --task gather_logs --task come_here --task follow_owner --failure-streak 0
# 現行の全課題を配置11・各1回、モードごとに600秒以内で測る
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py body --all --failure-streak 0
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py conversation --all --failure-streak 0
# 状態・結果の取得、終了
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py status
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py pull
.\.venv\Scripts\python.exe scripts/server/benchmark-home.py stop
```

接続先は既存の `scripts/server/.env.local` または `CIEL_SERVER_HOST`・`CIEL_SSH_KEY`。`inspect` は状態確認、`stage` はコードを `~/work/ciel-companion-benchmark/server` へ配置する。本番・開発用の会話サーバーは再起動しない。

`stage` は自宅サーバーの既存 `.env.minecraft` に `MINECRAFT_EULA=TRUE` がある場合だけ、その同意を同じマシンの試験用サーバーにも使う。無ければ止まる。試験用の RCON パスワードは別に生成し、既存の `.env.shared` は参照するだけで書き換えない。ローカル LLM の重みのファイル名を `CIEL_BENCH_MODEL_ID` に記録する。別の重みを使う場合は、配置先の `.env.benchmark` の識別名も合わせて変更する。

`body`・`conversation` はそれぞれ必要なイメージをビルドし、`gather_logs`・配置11・1回の小さな試験を行う。helperも課題別の実用期限を使う。まず1回だけ試し、全課題・反復へ進む前に不進行や操作未発行を調べる。失敗も採点結果なので終了コード1。イメージ作成・Minecraft起動はrunner開始前の環境準備で、別に時間がかかる。

`--all`は対応する全課題を1回ずつ選ぶ。`--failure-streak 0`は現在の失敗も一巡記録するため連続失敗の打ち切りだけを解除する指定で、課題・全体の期限は延びない。試験中の`stage`や別モードの並列実行は行わない。

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

各試行は、[家の中のLiveKit](../../operations/local-livekit-ja.md#測定)の新しい部屋へ `ciel-task-bench` を明示して接続する（`.env.benchmark`の`CIEL_BENCH_LIVEKIT_URL`・`_KEY`・`_SECRET`。未設定やクラウドの接続先なら始めない。会話サーバーのポートは8093）。要求の版・backend・モデル識別名・試行IDを dispatch metadata（`ciel.benchmark` v1）で照合し、不一致や旧形式は**推論前に拒否**する。さらに会話ログの同じ情報と人物設定のハッシュを確認してから課題を送る。更新時は `agent-bench` と `benchmark-runner` の両方を再ビルドする。

試験モードでは初回あいさつを生成せず、`benchmark_ready` を確認してから課題を送る。初回あいさつと依頼の長い推論が競合することを防ぎ、課題の入力を計測の入口にそろえる。通常の会話のあいさつは変更しない。

OpenAI と比較する場合は `.env.benchmark` の `CIEL_BENCH_BACKEND=openai` とモデル識別名を設定し、agent-bench を再作成する。実行にも `--backend openai --allow-paid` が必要。必要なら `CIEL_MIND_MODEL` 等を明示する（各役目の実際のモデル名はログに残る）。LiveKitは家の中のものを使い、クラウドの接続時間は使わない。公開 Web 検索・画像・音声認識は、先に作ったローカル試験モードと同じ制限になる。

Python 3.11以降と `server/agent/requirements-test.txt` があるホストなら、`server/` から `python -m benchmark.run ...` でも実行できる。設定は `.env.benchmark`、会話モードでは加えて `.env.shared` を読み、環境変数が優先する。

## 採点と結果

**エージェントの完了通知を合否の根拠にしない。** 評価器だけが RCON を使い、Minecraft サーバーが保持する持ち物・位置・体力・死亡数を取得する。RCON の資格情報や採点用コマンドはエージェントの道具に渡さない。採集・製作は開始時からの対象アイテムの増加数で成功を決める。

課題別の期限は原木・木のつるはし・材料補充90秒、石のつるはし・遠方探索120秒、不能な材料条件での報告・停止60秒。初回操作30秒、不進行30秒（遠方探索45秒）、同じ理由の失敗2回、継続不能後の報告待ち10秒でも終了する。`--seconds` は短くする上限であり、900を指定しても課題の期限を延長しない。詳しい進捗・報告・停止の判定は [practical-v1](minecraft-benchmark-ja.md) を参照する。

起動時の準備（体と中核APIの接続時に、固定の実行用指示を登録して1回推論する処理）は日常の利用でも依頼の前に済むため、試行の準備段階で行い、課題の期限・初回操作・不進行の時間に含めない。所要時間は`result.json`の`preparation`（`status`・`seconds`・`reference_chars`）に参考値として記録する。依頼文が入ってからの推論は、毎回の入力が異なるため従来どおり期限に含める。準備は準備段階の上限（既定45秒）にも含まれ、超えた場合は環境障害になる。準備の導入前の結果と比べるときは、`preparation`の有無と所要時間を併記する。

実行全体は既定 `--run-seconds 600`、3連続失敗でも後続を停止する（`--failure-streak 0` で解除可能）。全体予算には課題準備・終了処理も含み、終了用に20秒を確保する。準備最大45秒、切断と体解放確認は各最大10秒。全体の時間切れは `budget_exhausted`、連続失敗の打ち切りは `stopped_early`。予算中断・未実施は `skipped` で合否の分母から除外し、全条件測定済みと扱わない。LLM要求30回・ゲーム要求80回も上限として維持する。

持ち物の条件を満たした時刻を `time_to_goal_seconds` に記録し、その後は既定5秒まで目的のdone・シエルの返答を観測する（`--report-grace`）。`completion_observed` は体モードでは目的のdone、会話モードでは条件成立後の中断されていない返答を確認できたかを示す。返答の意味が正しいという判定ではない。`elapsed_seconds` はこの観測待ちも含む。返答が間に合わなくても持ち物の成功は保持し、回数予算の超過は失敗にする。

結果は `server/benchmark/data/results/<実行時刻>/`：

| ファイル | 内容 |
|---|---|
| `report.json` | format 2・policy、実行モード、モデル識別名、Gitとコード/課題ハッシュ、実効予算、予定数・打ち切り理由、期待行動の合格率、目的達成数・適切な停止数・未完了/未実施数 |
| `report.md` | 課題別の成功率と環境障害数 |
| `<課題>-s<配置>-r<回数>/result.json` | 初期・最終状態、観測できた中間到達、部分達成度`progress`、Mindcraft課題では出典`upstream`（ファイル・ID・定義のSHA-256・上流の期限）、停止時間、誤った目的完了、呼び出し数、失敗理由、修復・再試行数、トークン・料金の記録 |
| 同 `trace.jsonl` | 復元した配置、RCON観測、目的の状態、MCPの要求と結果、会話サーバーのイベント |

中間到達は定期観測で確認できた物だけ。瞬時に作って消費した材料を見逃す場合があるため、完全な達成率とは扱わない。

持ち物の課題では合否の横に`progress`を記録する。`target`は対象の増加数÷必要数（0〜1）、`milestones`は観測できた中間到達の割合で、対象を達成した場合は全中間到達を数える。中間到達の割合は観測の下限値。合否を置き換えず、同じ合否の中での改善を見るために使う。`report.json`の課題別集計と`report.md`は、合否を採点できた試行だけの平均（`mean_target_progress`・`mean_milestones_progress`）を表示し、未実施・環境障害を0点として混ぜない。不能条件の報告課題では対象の増加が無いのが正しいため、`target`を改善量として読まない。`foreground_generation_seconds` は完了した返答ストリームの待ち時間の合計で、裏の推論や実行との重なりは含めた内訳にならない。途中で予算が尽きた推論の全時間は記録されない。

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
| `navigation` / `body_call` | 移動課題の種別（come/follow/coordinates）、対象の地点列、距離・保持時間、方向探索の開始前提と、体モードで呼ぶ公開ツール。移動課題にはitem/countを置かない。schemaと範囲は`navigation.py`で検証 |
| `spec` | 体モードの目的。`{"make": "アイテム名", "count": 1}`。省略すると `item` / `count` から同じ形を作る。採集対象もこの目的形式で渡す |
| `action` | 既存課題に記載されているが、現在の `BodyDriver.submit()` は読み取らない。課題追加では `spec` を使い、ここへ新しい操作を書くだけで実行できると扱わない |
| `inventory` | 開始時に与えるアイテムと個数。現在は各1〜64個 |
| `forest` / `surface` | `near` / `far` / `many` / `none`。未知の値は拒否する。地表は `grass_block` または `sand` |
| `budget` | `seconds`、`first_action`、`no_progress`、`same_failure`、`blocked_grace`、`stop_grace`。省略項目は実用性ポリシーの既定値 |
| `modes` / `expected_outcome` | 対応モード、省略時は両方。期待行動は `achieve` または `report_unavailable`。後者は木材・所持品なしで石のつるはしが作れない専用oracleだけに対応 |
| `milestones` | 中間到達として観測するアイテム。採点条件の代わりではない。部分達成度の分母 |
| `mindcraft` | `{"file": "tasks/...", "task": "<上流ID>"}`。目標文・対象・個数・初期所持品を上流定義から読む。`prompt`・`item`・`count`・`inventory`・`spec`・`action`とは併記できず、`milestones`に対象を含める |
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

helperの `body` / `conversation` は既定1課題・配置11・1回。`--all`で全課題の一巡を選べる。複数配置・反復数・全体予算を変える場合は上の「自宅サーバーで課題を選んで実行する」に従い配置先のrunnerを使い、打ち切った実行を全課題の測定済み結果にしない。比較でOpenAIを使う場合は有料実行の明示指定を行い、依頼の範囲で実行する。

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
| 接近・座標移動 | 60秒 | 30秒 | 30秒 |
| 方向情報からの接近 | 120秒 | 30秒 | 45秒 |
| 3地点への追従と停止 | 90秒 | 30秒 | 30秒 |

初回推論・共有APIの待ち時間も利用者が待つ時間なので時計を止めない。CPUだからという理由で期限を自動延長しない。`--seconds` は課題の期限を短くする上限で、900を渡しても石のつるはしは120秒のまま。ダイヤの採掘など複雑な課題を追加するときは、課題JSONの `budget.seconds` に別の期限を根拠付きで設定する。

### 早期終了

- `first_action_timeout`：30秒以内に操作・観察を発行しなかった。道具名を文章に書くだけでは発行に数えない。
- `no_progress`：対象・中間アイテムのどれも前回の観測より増えず、初めて入った2ブロック単位の場所も増えない。使い切った原木の集め直しや板材の作り直しは増加に数え、消費・設置による減少は数えない。同じ場所の往復、同じ観察、モデル要求・返事の追加では時計を戻さない。移動を続けても課題全体の期限は延びない。2026-11-13までは各アイテムの最高値を超えたときだけ数えており、集め直しで作業中でも打ち切っていた。manifestの`progress_rule`（現在`inventory_gain_since_last_observation`）で判定を区別し、以前の結果とは同じ体の版で測り直して比べる。物を捨てて拾い直す往復でも時計が戻る点は、この判定の限界。
- `repeated_failure`：同じ操作・引数が同じ理由で2回失敗した。同一の非同期失敗の再通知は重複計上せず、実状態に進捗があれば反復失敗数をリセットする。
- `cannot_continue_without_report`：作業がneeds_decision/failed/cancelledのまま、10秒以内に報告も復帰もできなかった。体だけでは `needs_mind`・`body_cannot_continue` が先に確定する場合がある。
- `false_completion`：作業がsucceededでも実物の条件を満たしていない。自然文の「できた」も成功の代用にしない。
- `time_budget`：課題全体の期限までに完了しなかった。

停止課題は、最初の原木取得を確認してから停止を依頼する。応答まで5秒、応答後にさらに5秒の位置・所持品の安定と再開なしを確認する。安定観測は5秒の応答期限とは別枠。終了の監視間隔は0.5秒なので、その程度の幅はある。

持ち物による成功後の返答観測は既定5秒。返答の観測がなくても実物の成功は維持し、報告の有無は `completion_observed` として分ける。

### 実行全体を止める

既定はseed 11・各1回。全課題では体27試行、会話28試行。最初から3配置×3回を自動では実行しない。

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

評価値・条件・生データの参照先は[Minecraftの実測](../../testing/minecraft-results-ja.md)が正本。現在の配布範囲は[確認状況](../../testing/verification-status-ja.md)を参照する。測定条件を変えた評価を過去の値と直結せず、実装・モデル・課題・キャッシュ・共有負荷を揃える。日付付きの測定報告を新設せず、この仕様と該当する実測資料を更新する。
