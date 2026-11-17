# 家の中だけの LiveKit（試験用）

> 責務：家の中だけのLiveKitと試験用の会話サーバー（試験・測定用）の構成と起動。

クラウドの LiveKit は接続時間に上限があり、上限を超えると本番・開発とも会話に入れない（2026-11-16に429 `connection minutes limit exceeded`を受けた）。試験と測定は、家の中のネットワークだけで動く LiveKit で行える。普段の開発と本番は、これまでどおりクラウドの LiveKit につなぐ。

## 構成

| 部品 | 置き場所 | 役目 |
|---|---|---|
| `livekit-local` | `livekit/livekit-server:v1.8.4`、設定は`server/livekit-local/livekit.yaml` | 家の中のアドレスだけで開く LiveKit。信号7880、TCPの予備7881、音声のUDP 7882（1ポートにまとめる） |
| `token-local` | `server/livekit-local/token_server.py` | アプリにトークンを出す窓口（7883の`POST /token`）。LiveKit の開発用トークンサーバーと同じ形（`server_url`・`participant_token`）で返し、部屋に試験用の会話サーバー`ciel-dev`を呼ぶ |
| `agent-local` | 開発の会話サーバーと同じイメージとプロンプト | 家の中の LiveKit につなぐ会話サーバー（8092）。推論先は独立して設定可能。記憶は開発のスコープ |

サービスの定義は`server/compose.livekit-local.yaml`で、開発の`compose.dev.yaml`と一緒に読む。鍵・アドレスは開発の`server/.env.livekit-local`（Git・デプロイの外、権限0600）。家の中のアドレスは本番の`.env.minecraft`の`MC_BIND`を使う。

## 起動と停止

アプリの「トークンの取得先」の初期値は`http://192.168.1.15:7883/token`。保存値がない場合・以前の値が空の場合もこの取得先を使う。別の取得先を入力して確定すると端末へ保存し、次回起動時もその値を優先する。空欄で確定すると初期値へ戻る。通常版と配信版の保存先は個別。「家の中の試験用サーバーにつなぐ」の選択も保存するが、初期値追加だけでクラウドから自動切り替えはしない。保存するのは取得先URLであり、期限付きの参加トークンは接続時に取得する。

設定画面が会話コンポーネントの保存値読み込みより先に作られても、画面更新時に現在の取得先を反映する。入力欄を編集中は上書きせず、表示値の同期で編集イベントや再接続は起こさない。

```bash
scripts/server/livekit-local.sh start
```

```bash
scripts/server/livekit-local.sh status
```

```bash
scripts/server/livekit-local.sh stop
```

`start`は、今の開発の会話サーバー（`ciel-dev-agent-dev-1`）のイメージと設定（`/app/config`）で試験用の会話サーバーを起動する。開発の会話サーバーを配布し直したら、`start`をもう一度実行して版をそろえる。初回は鍵を作る。

## Windows アプリからつなぐ

### LiveKitと推論先を別々に選ぶ

LiveKitは音声通信、LLMは判断・返答生成を担当する。「家の中の試験用サーバーにつなぐ」をONにしたまま、推論だけOpenAIへ送れる。開発の`server/.env.livekit-local`へ次を設定する。APIキーは既存の本番`server/.env.shared`を共有し、このファイルへ複製しない。

```dotenv
CIEL_LLM_BACKEND=local
CIEL_OPENAI_ROLES=mind
CIEL_MIND_MODEL=gpt-5.4-mini
CIEL_MIND_REASONING=none
```

`agent-local`は`.env.shared`、`.env.dev`、`.env.livekit-local`の順に読み、最後の設定を優先する。Composeの補間も同じ順序にする。`CIEL_OPENAI_ROLES`のようなenvironment指定だけでなく、役目別モデル名もコンテナへ渡る。設定を変えたら`start`で再作成し、アプリの会話をつなぎ直す。`CIEL_OPENAI_ROLES=`に戻すとmindもローカルへ戻る。開発・本番の会話コンテナの設定や、記憶スコープ・プロンプトの配布先は変わらない。

### 接続操作

設定の「そのほか」→「開発」で、トークンの取得先に`status`が表示するURL（例：`http://192.168.1.15:7883/token`）を入れ、「家の中の試験用サーバーにつなぐ」を入れる。切り替えると、つなぎ直す。家の中のネットワーク専用なので、外出先からはつながらない。

窓口は http で、Unity の通信（UnityWebRequest）は http を許さない設定のままにしている。アプリは家の中の窓口からだけ、.NET の HttpClient でトークンを受け取る。2026-11-16に、この Windows からトークンの窓口（7883）と LiveKit（7880）へ届くことを確かめた。同日、配信版アプリ（`fe25175`）から家の中の試験用サーバーにつながった（LiveKitに持ち主と試験用の会話サーバーが参加）。

## 測定

試験用の会話サーバーのコンテナの中で、往復を重ねる測定を流せる。クラウドの接続時間を使わない。

```bash
source scripts/server/ssh-target.sh "" && "${SSH[@]}" 'docker exec ciel-dev-agent-local-1 sh -c "cd /app && python bench_latency.py --agent ciel-dev --rounds 2"'
```

返事の推論だけを比べるときは、発言を文字で送る`bench_text.py`を使う（音声の台本は、音声認識の区切り方で返事が作り直されて揺れる）。別の版と比べるときは`LIVEKIT_LOCAL_REVISION=<コミット> scripts/server/livekit-local.sh start`で、開発へ配布したことのある版を起動する。その部屋の開発ログ（`scripts/server/debug-log.sh pull --dev`）から、返事ごとの時間とキャッシュを`scripts/server/conversation_latency_report.py`で集計する。結果は[音声の実測](../testing/voice-results-ja.md#家の中のlivekitでの往復の速さ)。
