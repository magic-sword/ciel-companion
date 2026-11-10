# CPUで動くローカル音声認識（Vosk）

> 責務：CPU音声認識のアダプター、途中/確定結果、モデル配置と評価方法。

2026-11-10。Vosk 0.3.45と日本語小型モデル`vosk-model-small-ja-0.22`を自宅サーバーへ配置し、CPUだけの逐次認識を測定した。会話サーバーへの接続コードも実装し、実際のLiveKit SDKとの結合を隔離コンテナで確認した。通常の開発用・本番会話サービスはこの測定で再配置・再起動していない。人のマイク音声による会話全体の性能は未測定。

## 責務と入力の扱い

Unityから受け取る音声を、会話ホストのVosk STTアダプターがCPUで逐次認識する。LLMが選ぶMCPツールではなく、常時の入力経路。モデルは会話ワーカーのプロセス内で共有し、認識器は音声ストリームごとに分離する。GPUを割り当てず、モデルのロード・認識を別スレッドで行う。

途中結果はLiveKitのINTERIM_TRANSCRIPT、認識区間の確定結果はFINAL_TRANSCRIPTへ渡す。入力終了時には残りを確定し、途中結果を勝手に確定へ昇格させない。会話ホストの発話区切り・割り込み・話者識別・確定した依頼の受付は既存処理を使う。日本語トークン間の空白を整理し、停止の依頼が分断されないようにする。ASCII語句内の空白は保持する。

`CIEL_LLM_BACKEND=local`の音声入力はVoskが既定。OpenAI STTへ自動で戻さず、モデル未配置・不正設定は明示的なエラー。`CIEL_INPUT=text`なら音声モデルをロードしない。OpenAIのLLMとVoskの併用も可能だが、LLMの課金は別に発生する。Voskはpipeline＋Irodoriでのみ利用でき、Realtimeモードへの指定は起動時に拒否する。

## 設定する.envを区別する

| 起動方法 | 設定ファイル | 変数 |
|---|---|---|
| 本番Docker Compose | 自宅の`~/work/ciel-companion/server/.env` | `CIEL_LLM_BACKEND=local` |
| 開発用Docker Compose | 自宅の`~/work/ciel-companion-dev/server/.env.dev` | `CIEL_LLM_BACKEND=local` |
| Pythonの会話サーバーを直接起動 | `server/agent/.env` | `CIEL_LLM_BACKEND=local` |

本番と開発は同じ変数名を使い、設定ファイルを分ける。共有資格情報は`.env.shared`に置き、開発は本番の動作設定を読み込まない。

本番・開発の切替・反映単位は[共通の実行設定](../operations/local-runtime-ja.md)を参照する。本番にも同じVoskアダプターとモデルマウントを使える。

開発用の見本は[server/.env.dev.example](../../server/.env.dev.example)。既存.env.devを上書きせず必要な行を編集する。

```dotenv
CIEL_LLM_BACKEND=local
CIEL_INPUT=voice
# 通常は空。LLM_BACKEND=localなら自動でvoskになる。
CIEL_STT_BACKEND=
CIEL_VOSK_MODELS_DIR=${HOME}/models/vosk
```

モデルはホスト側`~/models/vosk/vosk-model-small-ja-0.22`に置く。Composeは親ディレクトリを`/models`へ読み取り専用でマウントする。モデルはGitへ含めない。直接Pythonで動かす場合は`CIEL_MODEL=pipeline`、`CIEL_VOICE=irodori`、`CIEL_VOSK_MODEL_PATH`に実際のモデルディレクトリを指定する。

コードの開発用反映後、開発用serverディレクトリで再ビルド・再作成する。設定を編集しただけや単なるrestartでは既存コンテナへ反映されない。

```sh
docker compose --env-file ../../ciel-companion/server/.env.shared --env-file .env.dev \
  -f compose.dev.yaml up -d --build agent-dev
```

共有LLM API、Irodori、LiveKitとDBは既存のものを使う。Minecraftベンチマークは従来どおり`CIEL_INPUT=text`を明示しており、この変更で音声評価へ変わらない。アプリは会話を接続し直して新しい設定を使う。


## 性能を確認する

測定は`scripts/server/vosk-home.py stage/run/integration/pull`を順に使用する。自宅サーバーの専用評価ディレクトリへ配置し、公式モデルと合成試料を使って、非実時間の処理率と実時間入力の途中結果・確定待ちを分けて測る。integrationは実際のSDKアダプターを一時コンテナで確認し、通常の会話サービスを変更しない。

モデル・入力WAV・コードの指紋、CPU/RAMの制限、同時負荷、認識結果を保持する。人の声、雑音、固有名詞、短い停止依頼、会話全体は別に試す。ASRの誤認識をLLMで補正して認識精度の測定に混ぜない。

結果と現在の採用判断は[確認状況](../testing/verification-status-ja.md)へ記録する。Vosk小型モデルは合成音声の初期試験で精度に課題があり、速度だけで本番採用を決めない。
