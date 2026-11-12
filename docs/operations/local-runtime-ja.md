# 本番・開発でローカル推論を選ぶ

> 責務：本番・開発の推論設定、設定ファイルの優先順位、切替・反映単位。

同じ会話ホストを本番・開発で使い、環境の違いは設定ファイルで表す。変数名に環境名を付けない。配布コミット・稼働設定と確認範囲は[確認状況](../testing/verification-status-ja.md)で管理する。

## 開発の推論再現ログ

開発agentの`CIEL_INFERENCE_TRACE=1`と`CIEL_AGENT_NAME=ciel-dev`の両方が揃う場合だけ、ローカルの会話返答LLMをHTTP境界で記録する。通常debugログの開始も必要。`agent/data/debug/traces/<会話名>.jsonl`に、SDK変換後のmessages/toolsと生成条件、要求ID・発話ID・HTTP試行ID、SSEの内容・tool断片・finish_reason・usage、DONE有無、TTSへ渡す文・TTS要求IDを保存する。再生結果は通常debugのitem/speech_doneと照合する。音声波形や実際に聞こえたことの証明ではない。ゲーム受付や背景推論等の別クライアントはこのHTTP記録の対象外。

HTTPヘッダー・認証情報を記録せず、既知のsecret/password/API key/tokenキー、環境変数の秘密値、Bearer形式は秘匿化する。JSON文字列内部も対象。画像等のdata URIは省略する。文章内の未知の秘密値まで自動判定できるものではない。入力が変更された記録はredacted=trueとなり、完全リプレイには使わない。通常debugのdataイベント等にも同じ秘匿化を適用する。送信する要求や音声合成内容自体は変更しない。

1イベント2MiB、1会話16MiB、trace全体256MiBを上限に、上限到達時はtrace_incompleteを残して当該プロセスの記録を止める。会話は継続する。ファイル600・ディレクトリ700で保存する。保持日数は通常debugと共通の`CIEL_DEBUG_LOG_DAYS`（既定7日）で、新しい会話開始時に期限切れを削除する。traceの上限は通常debugやWAVの容量上限ではない。

`CIEL_TRACE_RUNTIME_MANIFEST`は配布時に保存したモデル実ファイルのhash等のmanifest識別子。各要求には共有APIのmode・propsと取得時刻も付ける（最大60秒キャッシュ）。省略されたsampling値はpropsから確認する。重みファイルの外部変更や要求中のGPU/CPU切替は別途検証が必要で、manifestだけで固定条件を保証しない。情報取得失敗はunavailableとして会話を継続する。

サーバーのagentディレクトリで`python inference_trace.py --trace <traceファイル> --http-id <HTTP試行ID> --output <新規JSON>`により、実際の要求bodyをJSONへ書き出せる。秘匿化済み入力や不完全マーカー以降の記録は拒否する。書き出すだけでモデルや道具は実行しない。応答が途中終了しても、受信済みSSEは再現・反復採点用の部分証拠になる。

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

Voskはホストのモデル親ディレクトリをコンテナの`/models`へ読み取り専用でマウントする。CPU Whisperを使う環境は`CIEL_STT_BACKEND=whisper`、`CIEL_WHISPER_MODELS_DIR=${HOME}/models/faster-whisper`、`CIEL_WHISPER_MODEL_PATH=/models-whisper/small`を指定する。STT_BACKEND空の既定は変えず、環境ごとに明示選択する。モデルの実行時取得・OpenAIへの代替接続で欠落を隠さない。人のマイク・停止・返答の品質は設定解決や起動確認とは別に測定する。[音声認識](../services/local-stt-ja.md)を参照する。

## 待ち時間の大きい役目だけOpenAIへ送る

`CIEL_OPENAI_ROLES`で明示した文字推論の役目は、`CIEL_LLM_BACKEND=local`と`CIEL_LOCAL_ROLES`より優先してOpenAIへ送る。空なら従来どおり。失敗時に別backendへ自動で切り替えない。モデル名は既存の役目別変数を使う。

返答生成とゲーム受付を切り替える例：

```dotenv
CIEL_LLM_BACKEND=local
CIEL_OPENAI_ROLES=mind
CIEL_MIND_MODEL=gpt-5.4-mini
CIEL_MIND_REASONING=none
```

本番は本番の`server/.env`、開発は開発の`server/.env.dev`だけを変更し、対象agentを再作成する。APIキーは既存の`.env.shared`を使い、動作設定へ複製しない。設定例ファイルは切替を有効にしていない。

2026-11-11の実API疎通は残高不足（429・`credit_balance_exhausted`）で停止したため、現在は両環境とも切替指定を空に戻している。キーが設定されていることと、利用可能なAPI残高があることは別。残高追加後に単発から比較し、エラー時は元の設定へ戻す。自動フォールバックで比較条件を変えない。[疎通と復旧の証拠](../testing/voice-results-ja.md#openai部分切替の疎通と復旧)を参照する。

`mind`は通常の返答と`game_intake.py`の能力選択・引数生成が共用する。選択だけ・引数だけを個別backendへ分ける設定ではない。`listener / brief / thought / minutes_live / minutes / notes / relationship / growth / eyes`も指定可能。`talk / stt / research`や未知の名前は起動時に拒否する。音声入力は既存の`CIEL_STT_BACKEND`とlocal時の規則を保ち、読み上げはIrodoriを継続する。検索や埋め込み等のlocal時の制約も変わらない。

ローカルLLMの会話prefixと1tokenのウォームアップは、mindがローカルの場合だけ実行する。mindをOpenAIへ切り替えた場合はSTT・TTS等の準備だけを行い、ローカル用のモデルIDやQwen用引数をOpenAIへ送らない。会話開始のデバッグ記録の`role_models`で役目別の実モデルを確認する。`backend=local`は基本方針であり、全役目がローカルという意味ではない。

比較時は同じ発言と準備条件で、最初の文字・本返答音声・ゲームの初回操作・失敗・API使用量を測る。`model_response.seconds`は生成終了まで、`voice_first_delta.ms`は最初の本文までで、音声の聞こえ始めとは別。背景負荷・キャッシュ・入力の長さが異なる通常ログ同士だけで速度改善率を出さない。戻すときは`CIEL_OPENAI_ROLES=`に戻し、対象agentを再作成する。

既存のgpt-5.4-miniは[OpenAI公式のモデル資料](https://developers.openai.com/api/docs/models/gpt-5.4-mini)でChat Completionsと`reasoning.effort=none`への対応を確認した。APIへの切替だけで高速化を保証せず、[公式の遅延最適化ガイド](https://developers.openai.com/api/docs/guides/latency-optimization)と同様に、呼び出し回数・入力・出力と実測も確認する。実測は[音声と返答速度](../testing/voice-results-ja.md)、配布範囲は[確認状況](../testing/verification-status-ja.md)に記録する。

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

### 開発専用のMinecraftの体

通常の開発agentも本番と同じ`127.0.0.1:8771/mcp`の`Ciel`へ接続する。開発の会話・操作結果は従来どおり開発agentの`data/debug`へ保存する（CIEL_DEBUG_LOG=1、保持7日）。同じ体を受け持てる会話は一つだけで、本番と開発が同時に操作権を取得することはできない。切替時は先の会話のゲーム接続を終了する。体のコードは共用であり、開発agentの更新だけでは体の実装は更新されない。

別の体を入れて検証するときだけ、Git Bashから`scripts/server/deploy-server.sh --dev --minecraft`を明示する。`Ciel_Debug`を起動し、その配布では開発agentを8775へ接続する（body 8774、目3009、ループバック限定）。通常の`--dev`で8771のCielへ戻り、検証用の体を停止する。Composeを直接使う場合だけ`CIEL_DEV_MINECRAFT_URL=http://127.0.0.1:8775/mcp`を指定する。初回は`minecraft/dev-setup.py`が既存のEULA同意・持ち主・offline mode・whitelistを検査し、既存登録を保持してCiel_Debugのoffline UUIDを追加する。変更前のwhitelistは通常Minecraftの`ciel-config-backups/`へ保存し、whitelist reloadだけを実行する。Minecraft本体・本番の体の再作成やワールド復元は行わない。専用ベンチマークや現場debugで同名の体を使っている間は重複起動しない。

反映前後の証拠は[照合helper](../../scripts/server/verify-minecraft-dev.py)で残せる。ルートで`.venv/Scripts/python.exe -X utf8 scripts/server/verify-minecraft-dev.py before --evidence <一意の名前>`、配布後に同じ名前で`after`を実行する。検証用の体へ配布した場合は`--debug-body`を付ける。既存記録の上書きは拒否する。通常は開発agentのソース・指示・worker登録、8771のMCP契約、Cielの参加、本番コンテナ不変を確認する。共用の体は手元の開発ソースとの一致判定対象外。`--debug-body`では8775のCiel_Debugと体のソースも照合する。証拠は`~/work/ciel-companion-dev/server/data/deployments/<名前>/`へ保存する。MCPの体の取得やゲーム操作は行わず、資格情報は出力しない。

`.env.minecraft`は体のホスト・持ち主の設定に使い、本番の会話用`.env`は開発へ重ねない。開発からの通常ワールド検証と、専用アリーナを復元するベンチマークは別に扱う。

## Minecraftの指差し機能を導入する構成

`server/compose.pointing.yaml`は通常のMinecraftへPaper 1.21.11 build 132と指差しプラグインを追加する明示的な上書き構成。標準デプロイだけではVanillaから切り替わらない。専用ベンチマークで確認した後、通常ワールドを停止してバックアップし、Paper移行として適用する。会話サーバーだけの再配布と同じ扱いにしない。

`.env.minecraft`の`MC_OWNER`をプラグインの`CIEL_POINTING_OWNER`へ渡す。体には`CIEL_POINTING_FILE=/app/pointing/selection.json`を渡し、`minecraft/data/ciel-pointing/`だけを読取専用で共有する。`pointing-init`がこの専用ディレクトリの所有者をMinecraftの既定UID 1000へ揃える。別UIDを使う構成では両方を合わせる。資格情報や任意の外部受信口は追加しない。

serverディレクトリでの適用コマンドは次のとおり。実行前に配布対象のコミットとワールドのバックアップを確認する。

```sh
docker compose --env-file .env.shared --env-file .env --env-file .env.minecraft \
  -f compose.yaml -f compose.pointing.yaml --profile minecraft \
  up -d --build minecraft minecraft-body
```

以降、このMinecraft構成を更新するときも両方のComposeを指定する。Paper移行後のワールドをVanillaへ戻す操作は自動化していない。操作方法は[Minecraftサービス](../games/minecraft/minecraft-design-ja.md#指示棒と目線による対象指定)、配布済みかどうかは[確認状況](../testing/verification-status-ja.md)で確認する。

## 文字入力と検証

開発`.env.dev`の`CIEL_INPUT=text`でagentを再作成し、LiveKit資格情報のある`server/agent`から`python local_chat.py --agent ciel-dev --game minecraft`を実行できる。端末は別の試験用の部屋を作る。通常の開発用DB・同意範囲を使い、永続記憶を無効化した[専用ベンチマーク](../games/minecraft/minecraft-benchmark-ja.md)とは区別する。

`scripts/server/check-compose-backends.py`は自宅サーバーのComposeで、架空の資格情報と一時ディレクトリだけを使って設定を検証する。本番から開発へのbackend・モデル・Webhookの漏れ、任意設定、readonlyマウントを確認し、サービスは起動・変更しない。移行・競合・復元のテストは通常回帰に含む。[回帰テスト](../testing/regression-tests-ja.md)と[確認状況](../testing/verification-status-ja.md)を参照する。
