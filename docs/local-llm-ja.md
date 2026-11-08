# ローカル LLM（裏処理・Minecraft の動作試験）

状態：作った（2026-11-07）。開発用の会話サーバーだけで使っている。処理は `server/local-llm/`（動かす係）と `server/agent/models.py`（振り分け）。

## 返答と道具呼び出しもローカルへ切り替える（2026-11-09）

`CIEL_LLM_BACKEND=local` で、心・小脳の返答、道具の呼び出しと結果を受けた続き、聞く係、議事録のライブと清書、既存の裏処理をすべてローカル LLM へ送れる。既定は `openai` で、従来の `CIEL_LOCAL_ROLES` による役目別の振り分けも維持する。OpenAI への自動フォールバックはない。設定の変更には会話サーバーの再作成が必要。

一括切り替えは `CIEL_MODEL=pipeline`・`CIEL_VOICE=irodori` でだけ使える。ローカル側は `/v1/chat/completions` のストリーミング・道具呼び出し・JSON 出力に対応していること（現在の Qwen と llama-server を想定）。返答にも `CIEL_LOCAL_TIMEOUT`（既定 90 秒）を適用し、Qwen の thinking は無効にする。遅さや、ローカルモデルが正しい道具を選べるかは別途実機で確認する。

OpenAI のクレジットなしで試すため、一括切り替えでは文字入力が既定になる。音声認識・画像認識・Web 検索は今回のローカル LLM には接続していない。マイクは購読せず、画像と Web 検索には利用不可を返す。ゲーム中の発言は道具のある心へ回し、振り分け用の OpenAI 埋め込みと例文の学習を止める。Minecraft の状態取得・行動・手元の Wiki 検索は使える。音声や画像を使った試験、通常の意味による振り分け、会話のリアルタイム性の比較はこのモードの対象外。

### 開発用で起動する

先にコードを開発用のサーバーへ反映し、本番側の `~/work/ciel-companion/server` でローカル LLM を起動する。会話と道具の指示は裏処理より長いため、コンテキストを広げる設定を渡せる。以下は GPU メモリーに余裕を持たせる CPU の例（遅い）。GPU を使う場合は `LOCAL_LLM_MODE=gpu` にし、読み上げとの同時動作とメモリーを確認する。

```sh
LOCAL_LLM_CTX=32768 LOCAL_LLM_MODE=cpu docker compose --profile local-llm up -d --build local-llm
curl -f http://127.0.0.1:8094/health
```

開発用の `~/work/ciel-companion-dev/server` で（通常の開発用起動と同じ DB 設定を渡す）：

```sh
CIEL_DEV_LLM_BACKEND=local CIEL_DEV_LOCAL_TIMEOUT=180 \
  docker compose --env-file ../../ciel-companion/server/.env -f compose.dev.yaml up -d --build agent-dev
```

`CIEL_DEV_INPUT` は空のままにすると local では text、openai では voice になる。既存の `CIEL_DEV_MODEL=realtime` を設定している場合は外すか pipeline に戻す。`CIEL_DEV_LOCAL_LLM_URL`・`CIEL_DEV_LOCAL_LLM_MODEL` で接続先とモデルの別名も変えられる。通常の起動へ戻すには、上のコマンドの `CIEL_DEV_LLM_BACKEND=local` を `openai` に替えて agent-dev を再作成する。

### 文字で Minecraft に指示する

LiveKit のキーを設定済みの `server/agent/` で、追加した文字入力端末を動かす。Minecraft と体の MCP が起動しており、ほかの会話が体を受け持っていないことが必要。

```sh
python local_chat.py --agent ciel-dev --game minecraft
```

端末は一時的な試験用の部屋を作って ciel-dev を呼び、ゲームの接続状態を待ってから入力を受け付ける。「近くの木を調べて」「原木を3個集めて」などを入力し、返答と行動の完了を待って次を送る。返答の文字とゲーム・目的の状態を端末に表示する。`/quit` で部屋を閉じる。Unity を使う場合も文字入力モードではマイクからの指示は届かないため、この端末を試験の入口にする。

この端末自体は接続先の LLM 設定を変更しない。先に agent-dev を local で起動すること。LiveKit と、設定済みの保存・通知先（DB・Discord）は従来どおり使うため、完全なオフライン実行ではない。開発用で記憶を更新する点も従来どおり。

音声入力も併用したい場合だけ `CIEL_DEV_INPUT=voice` を明示する。この場合、文字の推論はローカルでも、文字起こしは OpenAI API を使い料金がかかる。

確認済み：外部 API を使わない回帰テストと、SDK の要求を模擬 HTTP 接続で検証する道具呼び出し・結果を受けた続きのテスト。ローカル LLM と Minecraft をつないだ実機試験は未実施。

## なぜ

OpenAI のクレジットが切れた（2026-11-07）。料金の内訳（開発用の会話 2,145 発言）は、内なる考え 39%・返事 38%・議事録の清書 9%・今のまとめ 6%。裏で動く役目は少し遅れても会話が止まらないので、自宅サーバーのローカル LLM に移す。返事（心・小脳）は、指示が長く（1 万トークンほど）、道具の使い分けもあり、今の GPU（空き 3 GB）では遅すぎるので OpenAI のまま。

## モデルと動かし方（自宅サーバーで測った）

内なる考え 1 回分（本物の指示＋作り物の会話、約 4,000 トークン）で測った。機械は i7-13700（24 スレッド）・メモリー 125 GB・RTX A2000 12 GB（シエルの声 Irodori が 8.9 GB）。

| モデル | 動かし方 | 読み込み | 書き出し | 1 回（2 回目） | GPU |
|---|---|---|---|---|---|
| Qwen3.5-4B | CPU だけ | 120 t/s | 11 t/s | 97 秒（27 秒） | 0 |
| Qwen3.5-4B | 読み込みだけ GPU | 974 t/s | 11 t/s | 23 秒（22 秒） | +0.2 GB |
| **Qwen3.5-35B-A3B** | **専門家は CPU、残りは GPU** | 305 t/s | **33 t/s** | **25 秒（13 秒）** | **+2.6 GB** |
| Qwen3.5-35B-A3B | 読み込みだけ GPU | 266 t/s | 11 t/s | 48 秒（37 秒） | +0.4 GB |
| Gemma 4 26B-A4B | 読み込みだけ GPU | 350 t/s | 8 t/s | 54 秒（45 秒） | +0.5 GB |

- 選んだのは **Qwen3.5-35B-A3B（Q4_K_M、unsloth の GGUF、21 GB）**。答えの中身もいちばん濃かった。
- Qwen3.5 は答える前に「考える」作り。切らないと書ける量を使い切って答えが空になったので、`chat_template_kwargs: {enable_thinking: false}` を送る（`models.options`）。
- 声と同時に確かめた：LLM が考えている最中も、声は 15 文とも止まらず、1 文 0.5〜0.8 秒が 0.6〜1.1 秒になっただけ。GPU は 12 GB 中 11.75 GB まで使った。

## 形

```
server/local-llm（コンテナ local-llm。profile local-llm）
  supervisor.py：llama-server を子として動かし、形を切り替える
    gpu の形：-ngl 99 --n-cpu-moe 99（専門家は CPU、残りは GPU）
    cpu の形：GPU を見せない（CUDA_VISIBLE_DEVICES を空）。1 回 50 秒ほど
  LLM の窓口：127.0.0.1:8094（OpenAI と同じ形。--alias local）
  切り替えの窓口：127.0.0.1:8095（GET /mode、POST /mode {"mode": "cpu"|"gpu"}。動き出すまで待って返す）
  重み：LOCAL_LLM_DIR（既定 ~/models/llm。Git・デプロイの外）

会話サーバー（server/agent/models.py）
  CIEL_LOCAL_LLM_URL（例 http://127.0.0.1:8094/v1）と CIEL_LOCAL_ROLES（例 thought,brief,notes,relationship,growth）に書いた役目だけ、
  ローカルへ送る（client_for・options）。時間の上限は CIEL_LOCAL_TIMEOUT（既定 90 秒）。料金は 0 として記録する
```

### 歌を聴くあいだは CPU の形

歌を聴く係（`server/singing`）は、分析のモデル（約 2 GB）を GPU に載せる。声・LLM・分析は同じ 12 GB に入らない。会話サーバーの歌の係（`singing.py`）が、読み上げに GPU を空けてもらう（`/release`）前に、ローカル LLM を cpu の形にし（`CIEL_LOCAL_LLM_CONTROL`）、分析が終わったら gpu の形に戻す。やめたときは、分析のモデルが外れる 35 秒後に戻す。次の歌が始まったら、その「戻す」はやめる。切り替えのあいだ（読み直しに 10〜30 秒）LLM は答えないので、裏の役目はその回を飛ばす。

## 動かし方

```sh
# 自宅サーバーの ~/work/ciel-companion/server で（重みは ~/models/llm に置いてある）
docker compose --profile local-llm up -d --build local-llm
curl -s 127.0.0.1:8095/mode
```

## 内なる考えの質の比べ（2026-11-07）

`eval_thoughts.py --only <場面>` を 2 場面で回した（開発用の会話サーバーのコンテナの中）。考えるのは gpt-5.4-mini（`-e CIEL_LOCAL_ROLES=` で OpenAI に戻す）とローカルの Qwen3.5-35B-A3B、採点は gpt-5.4（1〜5 点）。料金は約 1.5 ドル（大半が採点）。結果は自宅サーバーの `~/work/ciel-eval`。

| 観点 | 星の話（mini / ローカル） | 疲れて短い答え（mini / ローカル） |
|---|---|---|
| 具体的か | 3.69 / 3.44 | 2.78 / 2.71 |
| 話題に合うか | 4.06 / 3.69 | 4.11 / 3.86 |
| 話す・聞く価値 | 3.50 / 2.88 | 3.33 / 2.86 |
| 切れ端に反応していないか | 4.56 / 3.44 | 3.89 / 3.14 |
| シエルらしさ | 4.12 / 3.81 | 4.67 / 4.57 |
| いちばん強い考えを今話すとよいか | 3.60 / 3.80 | 3.67 / 3.67 |
| 知りたいことの質 | 3.43 / 3.43 | 2.75 / 2.00 |
| 良くない考えの割合 | 19% / 50% | 56% / 71% |

- ローカルは一段落ちる。とくに「切れ端に反応していないか」「話す価値」「良くない考えの割合」。
- 気持ちの強さを付けすぎる：疲れて「うん」としか言わない相手に 4・5・4（mini は 3・2・4）。そのままだと話しかけすぎる。
- 考えが長く、セリフのようになる（「〜寄り添ってあげたいな。」）。語尾に「〜わ」「〜ようね」が混じる。mini は短い心のメモ。
- シエルらしさはほぼ同じ。
- 1 回の時間（ローカル、gpu の形）：読み込み 100〜290 t/s・書き出し 33 t/s、1 回 4〜24 秒。

## まだのこと

- 本番の会話サーバーは OpenAI のまま（開発用で質を確かめてから、`compose.yaml` の agent に 3 つの環境変数を足す）。
- 内なる考えをローカルに置くかどうか（上の比べでは一段落ちる。指示をローカル向けに直して評価し直すか、OpenAI に戻す）。
- まとめ・メモ・関係・育つ好みの質の比べ（まだ測っていない）。
- 声の係（Irodori）は、長く読み上げると作業用の GPU が増えることがある（前に 10.8 GB）。PyTorch は足りなくなると取っておいた分を手放して取り直すので止まりはしないが、余裕は小さい。
