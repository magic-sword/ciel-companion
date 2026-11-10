# 本番・開発でローカル推論を選ぶ

> 責務：本番・開発の推論設定、設定ファイルの優先順位、切替・反映単位。

同じ会話ホストを本番・開発で使い、環境の違いは設定ファイルで表す。変数名に環境名を付けない。配布コミット・稼働設定と確認範囲は[確認状況](../testing/verification-status-ja.md)で管理する。

## 設定ファイルの責務

ローカル音声の`CIEL_VOICE_FAST`は既定`1`。ジョブのモデル準備、背景推論の分類、短い最初の文を有効にする。`0`は同じソースで旧動作と比較するための設定。新しい`voice_warmup_file`・`voice_first_sentence_file`を持つpersona.tomlとコードを一緒に配置する。準備済み状態には世代を返す新しい制御先が必要で、ソースの更新だけで既存の共有APIへ適用されたとは扱わない。

| ファイル | 内容 | 読む環境 |
|---|---|---|
| 本番`server/.env.shared` | LiveKit・OpenAI・YouTubeの資格情報、DBパスワード | 本番・開発・専用ベンチマーク |
| 本番`server/.env` | 本番の推論、入力、モデル、Webhook、共有LLMサービスの配置・容量 | 本番だけ |
| 開発`server/.env.dev` | 開発の推論、入力、モデル、Webhook | 開発だけ |
| 各端末の`server/agent/.env` | Pythonを直接起動する場合の資格情報と動作設定 | その直接起動だけ。Composeは読まない |

本番は`~/work/ciel-companion/server`、開発は`~/work/ciel-companion-dev/server`。共有ファイルは本番側に一つ置く。`.env.shared`に置ける名前は`LIVEKIT_URL`、`LIVEKIT_API_KEY`、`LIVEKIT_API_SECRET`、`OPENAI_API_KEY`、`YOUTUBE_API_KEY`、`CIEL_DB_PASSWORD`だけ。backend・モデル・Webhook・記憶スコープは共有しない。モデル・DB・LiveKitを共用することと、本番の動作設定を開発へ継承することを区別する。

見本は[共通資格情報](../../server/.env.shared.example)、[本番](../../server/.env.example)、[開発](../../server/.env.dev.example)。既存の設定へ見本を丸ごと上書きしない。ベンチマークは`.env.benchmark`を独立して読み、資格情報だけ共有する。`CIEL_BENCH_*`は評価器の制御用であり、本番・開発の変数名の別名ではない。

## 本番・開発で共通の変数名

両方の設定ファイルで次の名前を使う。

```dotenv
CIEL_LLM_BACKEND=local
CIEL_MODEL=pipeline
CIEL_INPUT=voice
CIEL_STT_BACKEND=
CIEL_LOCAL_LLM_URL=http://127.0.0.1:8094/v1
CIEL_LOCAL_TIMEOUT=90
CIEL_VOSK_MODELS_DIR=${HOME}/models/vosk
CIEL_VOSK_MODEL_PATH=/models/vosk-model-small-ja-0.22
CIEL_MINUTES_DISCORD_WEBHOOK=
```

`CIEL_LLM_BACKEND`は省略時openai。localの音声入力は共有LLM＋CPUのVosk＋Irodori、text入力なら音声認識を使わない。STT_BACKEND空はbackendに連動し、localからOpenAIへ自動で戻さない。画像認識は画像能力を確認したローカルAPIを使い、モデル送信前に既定256pxへ縮小する。[画像の契約](../services/vision-design-ja.md)を参照。Web検索・OpenAI埋め込みによる振り分けはlocalでは使わない。外部LiveKit等への接続は残るため、完全なオフライン化ではない。

`CIEL_LOCAL_LLM_MODEL`はAPIに送るモデルIDの任意の上書き。既定`local`を公開する共有APIでは設定不要。実際の重みは共有API側の`LOCAL_LLM_FILE`が選ぶ。`CIEL_LOCAL_ROLES`は役目別のローカル利用、`CIEL_LOCAL_LLM_CONTROL`は歌唱中のGPU解放先で、既定は`http://127.0.0.1:8095`。モデルの役目別設定やWebhookも環境ごとのファイルで設定できる。

Voskはホストのモデル親ディレクトリをコンテナの`/models`へ読み取り専用でマウントする。モデルの実行時取得・OpenAIへの代替接続で欠落を隠さない。人のマイク・停止・返答の品質は設定解決や起動確認とは別に測定する。[音声認識](../services/local-stt-ja.md)を参照する。

## 読み込みと優先順位

本番は`--env-file .env.shared --env-file .env`、開発は`--env-file ../../ciel-companion/server/.env.shared --env-file .env.dev`を使う。開発で本番の`.env`を重ねない。Composeの`env_file`も資格情報と対象環境のファイルだけを読み、その他の環境設定をコンテナへ渡さない。

明示的なシェル環境変数はComposeの補間値より優先される。コンテナの固定environment（agent名・ポート・記憶スコープなど）と、補間した推論設定はenv_fileの同名値より優先される。本番はmain、開発はdevの記憶スコープを固定し、設定ファイルの変更で共有人物のアクセス範囲を変えない。

## 既存設定からの移行

サーバー上で更新版の[移行ツール](../../server/environment.py)を使う。本番serverディレクトリから、本番と既存の開発設定をまとめて移行する例：

```sh
python3 environment.py --prod-dir "$PWD" --dev-dir ../../ciel-companion-dev/server --check
python3 environment.py --prod-dir "$PWD" --dev-dir ../../ciel-companion-dev/server
```

初回は旧`agent/.env`と本番`.env`から資格情報を分離し、既存の本番動作設定を維持する。旧`CIEL_DEV_*`は開発ファイル内で同じ意味の`CIEL_*`へ変換する。旧`CIEL_DEV_DISCORD_WEBHOOK`だけは`CIEL_MINUTES_DISCORD_WEBHOOK`に対応する。本番backendやWebhookを開発の初期値に使わない。変換前後の名前が異なる値で併存する場合や、共有資格情報が競合する場合は値を表示せず停止する。

変更前の設定は本番`data/config-backups/environment-*/`へ権限を制限して保存する。書き込み途中で失敗した場合は元に戻す。移行後の再実行では旧`agent/.env`を再取り込みせず、環境ごとのファイルを正本とする。旧ファイルは直接Python起動用として残すがComposeは使わない。`--check`は変更・バックアップ作成を行わない。移行だけでは稼働中コンテナへ反映されない。

新規導入では見本から`.env.shared`と環境別ファイルを作り、資格情報を設定する。既存環境は先に移行し、見本で秘密を置き換えない。`deploy-remote.sh`も起動前に移行を実行する。転送スクリプトは実際の`.env.shared`・`.env`・`.env.dev`とdataを送らない。

## 反映の単位

共有LLM API・TTS・DBとVoskモデルが配置済みであることを確認し、確認済みGitコミットを配布する。通常の[デプロイ](../development/build-ja.md)は環境に合うファイルを読み込む。対象agentだけを反映する場合、本番serverで：

```sh
docker compose --env-file .env.shared --env-file .env -f compose.yaml up -d --build --no-deps agent
```

開発serverで：

```sh
docker compose --env-file ../../ciel-companion/server/.env.shared --env-file .env.dev \
  -f compose.dev.yaml up -d --build --no-deps agent-dev
```

環境変数の編集後は対象コンテナを再作成する。単なるrestartや設定移行だけを反映済みとしない。ゲーム契約が変わる更新ではMCPの版も揃えるが、Minecraft本体・ワールドの再作成はbackend切替に含めない。共有LLMを環境ごとに追加起動しない。

## 文字入力と検証

開発`.env.dev`の`CIEL_INPUT=text`でagentを再作成し、LiveKit資格情報のある`server/agent`から`python local_chat.py --agent ciel-dev --game minecraft`を実行できる。端末は別の試験用の部屋を作る。通常の開発用DB・同意範囲を使い、永続記憶を無効化した[専用ベンチマーク](../games/minecraft/minecraft-benchmark-ja.md)とは区別する。

`scripts/server/check-compose-backends.py`は自宅サーバーのComposeで、架空の資格情報と一時ディレクトリだけを使って設定を検証する。本番から開発へのbackend・モデル・Webhookの漏れ、任意設定、readonlyマウントを確認し、サービスは起動・変更しない。移行・競合・復元のテストは通常回帰に含む。[回帰テスト](../testing/regression-tests-ja.md)と[確認状況](../testing/verification-status-ja.md)を参照する。
