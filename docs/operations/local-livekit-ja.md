# 家の中だけの LiveKit

> 責務：家の中だけのLiveKit、本番・開発の会話サーバーの接続と起動。

クラウドの LiveKit は接続時間に上限があり、上限を超えると会話に入れない。本番・開発とも家の中のネットワークだけで動くLiveKitを選べる。LiveKitの通信先と、LLMの推論先は独立した設定である。

## 構成

| 部品 | 置き場所 | 役目 |
|---|---|---|
| `livekit-local` | `livekit/livekit-server:v1.8.4`、設定は`server/livekit-local/livekit.yaml` | 家の中のアドレスだけで開く LiveKit。信号7880、TCPの予備7881、音声のUDP 7882（1ポートにまとめる） |
| `token-local` | `server/livekit-local/token_server.py` | アプリにトークンを出す窓口（7883の`POST /token`）。開発指定があれば`ciel-dev`、指定がなければ`LIVEKIT_LOCAL_AGENT`を呼ぶ。本番切替時は`ciel-main`を設定する |
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

試験・測定のときは、推論をすべてローカルにする`measure`で起動する（[測定](#測定)）。

```bash
scripts/server/livekit-local.sh measure
```

```bash
scripts/server/livekit-local.sh stop
```

`start`は、今の開発の会話サーバー（`ciel-dev-agent-dev-1`）のイメージと設定（`/app/config`）で試験用の会話サーバーを起動する。開発の会話サーバーを配布し直したら、`start`をもう一度実行して版をそろえる。初回は鍵を作る。

## Windows アプリからつなぐ

### 本番をローカルLiveKitへ接続する

本番の`server/.env.livekit-production`に、既存の開発`server/.env.livekit-local`から`LIVEKIT_LOCAL_BIND`・`LIVEKIT_LOCAL_KEY`・`LIVEKIT_LOCAL_SECRET`だけをコピーして権限0600で保存する。Git・通常配布の対象外であり、`.env.shared`のクラウド資格情報は変更しない。本番の推論設定は引き続き`.env`、プロンプトは本番の`agent/config`、記憶は`main`を使う。

```bash
docker compose --env-file .env.shared --env-file .env.livekit-production --env-file .env \
  -f compose.yaml -f compose.livekit-production.yaml up -d --no-build --no-deps agent
```

本番agentは`ciel-main`として登録される。開発の`.env.livekit-local`には`LIVEKIT_LOCAL_AGENT=ciel-main`を設定し、`token-local`を再作成する。アプリでは「家の中の試験用サーバーにつなぐ」をON、「開発用のサーバーにつなぐ」をOFFにして本番へ入る。開発スイッチがONなら同じ窓口から`ciel-dev`へ入る。既存の会話は移動しないため再接続する。

`deploy-remote.sh`は`.env.livekit-production`の存在を確認して同じoverlayを読み、通常配布後もローカル接続を維持する。`livekit-local.sh stop`は本番が使用中なら停止を拒否する。クラウドへ戻す場合は同ファイルを退避し、通常のComposeで本番agentを再作成して、窓口の既定を`ciel-dev`へ戻す。クラウドの利用上限が解消していることを先に確認する。

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

**測定・確認・試験の会話は、家の中のLiveKitを使う。** クラウドのLiveKitの接続時間は、本番の利用者の会話に残す（上限を超えると、本番も開発も会話に入れなくなる。2026-11-20に開発の確認で上限に達した）。試験用の会話サーバーのコンテナ（`ciel-dev-agent-local-1`）は、家の中のLiveKitの`LIVEKIT_URL`・鍵を持っているので、測定のスクリプトはこのコンテナの中で動かす。開発の会話サーバー（`ciel-dev-agent-dev-1`）や本番のコンテナの中で動かすと、クラウドへつながる。

1. 開発へ配布したあと、`scripts/server/livekit-local.sh measure`で試験用の会話サーバーを同じ版にそろえて起動する。`measure`は返事の役目も含めて推論をすべて共有GPU API（8094）へ送り、`.env.livekit-local`のOpenAIの役目（普段の会話用）を使わない。最後の行に推論の設定が出るので、`OpenAIの役目=[]`を確かめてから回す。測定が終わったら`start`で普段の設定へ戻す（普段アプリからこのサーバーで話すときの設定）。
2. 配布の疎通確認：`scripts/server/smoke-livekit.py`を`ciel-dev-agent-local-1`の中で`--agent ciel-dev`で動かす（挨拶の声・文字の発言・返事の声）。
3. 会話の記録を読む処理（心の見極め・今のまとめ・メモ）を確かめるときは、合成した声で話しかける`bench_latency.py`を使う。文字で送る`bench_text.py`の発言は、会話の記録（声の文字起こしの確定で書く）に本文が入らない。`--lines`に1行1発言の台本、`--pause`に返事のあとの間（秒）を渡すと、静かな間に動く処理まで見られる。部屋の名前は最初の行（`room=…`）に出る。
4. 料金：`measure`なら、音声認識（Whisper）・読み上げ（Irodori）・推論のすべてが家の中で動き、料金はかからない。`start`のままだと、返事の役目（`mind`）は`.env.livekit-local`の`CIEL_OPENAI_ROLES`でOpenAIを使う（2026-11-20は`mind`がgpt-5.4-miniで、1回の返事が約0.003ドル）。2026-11-20、`measure`での疎通確認で返事の役目が`local`になることを確かめた（文字の発言から返事の声まで7.1秒。共有GPU APIは別の処理と共用）。
5. Minecraftのベンチマーク（`compose.benchmark.yaml`）も家の中のLiveKitを使う。ベンチマーク環境の`.env.benchmark`に`CIEL_BENCH_LIVEKIT_URL`・`CIEL_BENCH_LIVEKIT_KEY`・`CIEL_BENCH_LIVEKIT_SECRET`（このLiveKitの値）を置く。未設定やクラウドの接続先なら、実行器は試験を始めない。ベンチマークの会話サーバーは8093で動き、試験用の会話サーバー（8092）と並べられる。

試験用の会話サーバーのコンテナの中で、往復を重ねる測定を流せる。

```bash
source scripts/server/ssh-target.sh "" && "${SSH[@]}" 'docker exec ciel-dev-agent-local-1 sh -c "cd /app && python bench_latency.py --agent ciel-dev --rounds 2"'
```

返事の推論だけを比べるときは、発言を文字で送る`bench_text.py`を使う（音声の台本は、音声認識の区切り方で返事が作り直されて揺れる）。別の版と比べるときは`LIVEKIT_LOCAL_REVISION=<コミット> scripts/server/livekit-local.sh start`で、開発へ配布したことのある版を起動する。その部屋の開発ログ（`scripts/server/debug-log.sh pull --dev`）から、返事ごとの時間とキャッシュを`scripts/server/conversation_latency_report.py`で、シエルが自分から話した数と心の考えの点を`scripts/server/speaking_report.py`で集計する（考えは`CIEL_MIND_IDEAS=1 scripts/server/livekit-local.sh measure`で出す）。結果は[音声の実測](../testing/voice-results-ja.md#家の中のlivekitでの往復の速さ)。
