# 本番・開発でローカル推論を選ぶ

> 責務：本番・開発の推論設定、設定ファイルの優先順位、切替・反映単位。

2026-11-10。本番Compose・開発用Composeの両方で、LLMとCPU音声認識を設定から選べる。構成対応をソースに実装し、LinuxサーバーのDocker Composeで設定の解決を確認した。稼働中の本番・開発サービスの設定変更、配布、再起動はこの整備では行っていない。

## 同じ処理を使い、設定を分離する

環境ごとに推論実装を分岐させない。同じ会話ホストで以下を切り替える。

| 設定 | LLM | 音声認識 | 読み上げ |
|---|---|---|---|
| backend=openai、音声入力 | OpenAI | 既定OpenAI | Irodori |
| backend=local、音声入力 | 共有ローカルAPI | 既定CPUのVosk | Irodori |
| backend=local、文字入力 | 共有ローカルAPI | 使用しない | Irodori |

本番は`CIEL_LLM_BACKEND`、開発は`CIEL_DEV_LLM_BACKEND`を使う。両方とも省略時の既定はopenaiであり、本番をlocalにしても開発側を自動で変えない。localではOpenAIへの自動フォールバックをせず、画像認識・Web検索・OpenAI埋め込みによる振り分けは既存のローカルモードと同じ制限を維持する。LiveKit・DB・ゲームサービスは既存の接続を使うため、完全なオフライン化とは異なる。

## 設定ファイル

| 用途 | 自宅サーバーのファイル | 変更する変数 |
|---|---|---|
| 本番Docker Compose | `~/work/ciel-companion/server/.env` | `CIEL_LLM_BACKEND=local` |
| 開発Docker Compose | `~/work/ciel-companion-dev/server/.env.dev` | `CIEL_DEV_LLM_BACKEND=local` |
| Pythonを直接起動 | 各コードの`server/agent/.env` | `CIEL_LLM_BACKEND=local` |

本番の見本は[server/.env.example](../server/.env.example)、開発用は[server/.env.dev.example](../server/.env.dev.example)。既存ファイル全体を置き換えず、既存のDBパスワード・Webhookなどを維持して必要な設定を編集する。

本番で将来切り替えるときの設定：

```dotenv
CIEL_LLM_BACKEND=local
CIEL_INPUT=voice
CIEL_STT_BACKEND=
CIEL_LOCAL_LLM_URL=http://127.0.0.1:8094/v1
CIEL_LOCAL_LLM_MODEL=local
CIEL_LOCAL_TIMEOUT=90
CIEL_VOSK_MODELS_DIR=${HOME}/models/vosk
CIEL_VOSK_MODEL_PATH=/models/vosk-model-small-ja-0.22
```

STT_BACKENDが空ならLLM_BACKENDに連動する。localの音声ではvoskのみを受け付け、OpenAIへ戻さない。文字だけなら`CIEL_INPUT=text`。Voskモデルの親ディレクトリを読み取り専用で`/models`へマウントし、MODEL_PATHはそのコンテナ内のパス。別の日本語モデルを評価する場合もこのパスを指定できる。開発側には対応する`CIEL_DEV_*`があり、独立したモデルも選べる。

Dockerの`environment`は`agent/.env`の同名設定より優先される。以前`agent/.env`に置いた本番のbackend/input/STT/Voskパス/local URL/model/timeoutを使い続ける場合は、本番の`server/.env`へ同じ値を移す。LiveKit・OpenAI等の資格情報、その他の会話設定は従来の`agent/.env`を使う。役目別の`CIEL_LOCAL_ROLES`と歌唱時の`CIEL_LOCAL_LLM_CONTROL`も従来の設定を維持し、この変更で上書きしない。

## 本番へ切り替える前と反映の単位

1. 開発環境で人のマイク・会話の返答・停止依頼・道具の呼び出しを確認する。[Voskの初期測定](local-stt-ja.md)では小型日本語モデルの精度に課題があり、現時点で本番の品質を保証しない。
2. [共有LLM API](shared-llm-api-ja.md)のモデル・準備状態と容量を確認する。既存の8094を共用し、backendの変更だけで新たなモデルサービスを増やさない。サービスが未起動なら先に既存のlocal-llmプロファイルのサービスを起動する。環境ごとに別のモデルを無条件に立ち上げない。
3. Voskモデルが指定先にあることを確認する。モデルの実行時ダウンロード・OpenAIへの代替接続で欠落を隠さない。パス不在は音声pipelineの組み立て時にエラーとなる。
4. 歌唱時のGPU解放も使う場合は、会話サーバーの`CIEL_LOCAL_LLM_CONTROL=http://127.0.0.1:8095`が従来どおり設定されていることを確認する。LLM、Irodori、歌の共有容量・CPUへの切替条件を維持する。Vosk自体はCPUで動く。
5. 確認済みGitコミットを配布し、対象のagentコンテナだけを再ビルド・再作成する。起動済みの会話は再接続し、新しい設定・コードを使う。設定編集や単なるrestartだけでは反映済みとしない。

本番コードの反映後、本番serverディレクトリでの対象を限定したコマンド：

```sh
docker compose --env-file .env -f compose.yaml up -d --build --no-deps agent
```

開発は開発serverディレクトリで：

```sh
docker compose --env-file ../../ciel-companion/server/.env --env-file .env.dev \
  -f compose.dev.yaml up -d --build --no-deps agent-dev
```

これらは将来の反映手順であり、今回実行したコマンドではない。モデル・DB・TTS等の依存先は事前に稼働していることが前提。OpenAIへ戻す場合は対象のLLM_BACKENDをopenaiへ戻し、STT_BACKENDが空であることを確認して対象agentを再作成する。

## 文字入力で確認する

`CIEL_DEV_INPUT=text`を指定して開発用agentを再作成し、LiveKit設定のある`server/agent`で`python local_chat.py --agent ciel-dev --game minecraft`を実行する。端末は試験用の別の部屋を作るため、Unityの既存の会話へそのまま入力するものではない。返答と操作の完了を待って次を送り、`/quit`で終了する。接続先の推論設定は端末自身では変更しない。

通常の開発用DB・同意範囲を使うことと、永続記憶を無効にした専用ベンチマークを区別する。手順・採点を伴う評価は[ベンチマーク](minecraft-benchmark-ja.md)を使う。

## 設定の検証

`scripts/server/check-compose-backends.py`は手元の本番・開発Composeを自宅サーバーのComposeで読み取り専用検証する。秘密を含む解決結果は表示・保存せず、サービスを起動・再作成しない。確認済みの構成と未確認範囲は[確認状況](verification-status-ja.md)に集約する。
