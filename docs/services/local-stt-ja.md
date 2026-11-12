# CPUで動くローカル音声認識

> 責務：CPU音声認識のアダプター、途中/確定結果、モデル配置と評価方法。

Voskの逐次認識と、faster-whisperのCPU int8認識を選択できる。現在の採用・配布範囲、条件・性能値・生データは[確認状況](../testing/verification-status-ja.md)を参照する。合成音声の比較と、人のマイクでの品質は区別する。

## 責務と入力の扱い

人の録音を使う精度・遅延の継続比較は[音声会話ベンチマーク](../testing/voice-benchmark-ja.md)を使う。同一録音のCER・自然確定・RTFと、LiveKit経由の相づち/本返答の受信遅延を分けて測定する。以下の合成3文の実測だけで人の聞き取り精度を判断しない。

Unityから受け取る音声を、会話ホストのVosk STTアダプターがCPUで逐次認識する。LLMが選ぶMCPツールではなく、常時の入力経路。モデルは会話ワーカーのプロセス内で共有し、認識器は音声ストリームごとに分離する。GPUを割り当てず、モデルのロード・認識を別スレッドで行う。

途中結果はLiveKitのINTERIM_TRANSCRIPT、認識区間の確定結果はFINAL_TRANSCRIPTへ渡す。入力終了時には残りを確定し、途中結果を勝手に確定へ昇格させない。会話ホストの発話区切り・割り込み・話者識別・確定した依頼の受付は既存処理を使う。日本語トークン間の空白を整理し、停止の依頼が分断されないようにする。ASCII語句内の空白は保持する。

`CIEL_LLM_BACKEND=local`でSTT_BACKENDが空ならVosk。`CIEL_STT_BACKEND=whisper`でCPU Whisperを選ぶ。OpenAI STTへ自動で戻さず、モデル未配置・不正設定は明示的なエラー。`CIEL_INPUT=text`なら音声モデルをロードしない。ローカルSTTはpipeline＋Irodoriでのみ利用でき、Realtimeモードへの指定は起動時に拒否する。

### Whisperの発話認識

`whisper_engine.py`がfaster-whisper 1.2.1のsmallモデルをCPU int8、4スレッド、beam_size=1、日本語固定で処理する。モデルはプロセス内で共有し、ロードと推論は会話イベントループ外で行う。実行時のモデル取得・GPU利用はしない。モデルは`Systran/faster-whisper-small`から事前配置し、重み指紋を記録する。[公式実装](https://github.com/SYSTRAN/faster-whisper)のCPU推論とinitial_promptを使用する。

会話では既存のVADとLiveKitの`StreamAdapter`で発話区間を選び、Whisperへ渡す。短い発話が二重に除去されないよう、認識器内のVADは無効にする。途中文字列は配信せず、確定結果だけを渡す。単体録音評価では外側のVADがないのでWhisper内のVADを有効にし、会話全体の確定遅延とは分けて測る。無音・短い発話・途中の間の実経路は別途確認する。

語彙ヒントは`persona.toml`の`stt_vocabulary_file`（既定`prompts/stt_vocabulary.md`）と、ホストが取得した名前を使う。認識後の「シール→シエル」の文字置換は行わない。返答側の`voice_first_sentence.md`では、呼びかけの表記揺れを理由に名前の訂正を始めず、判断に必要な数字・否定・操作対象が曖昧なら確認する。

Whisperには、リンクが有効なゲームのprofileから取得した`speech_vocabulary`も追加する。[語彙の契約](../games/game-environment-mcp-design-ja.md#作業体出来事を混同しない)に従って型・件数・長さを検証し、不正・未提供・切断時は基本ヒントだけを使う。通常の固定語彙から「マインクラフト」を外し、ゲーム側へ移した。音声区間の認識開始時にヒントを固定し、認識中の接続変更を次の処理へ反映する。接続中の語彙を文字起こし後の置換には使わない。実音声での認識精度・遅延の改善は別測定が必要。

1秒以下の入力から長い語彙ヒントの全文が返る誤認識を抑止する。NFKC・空白・句読点を除いた比較で、ヒント全体または一行と完全一致し、そのヒントが10文字以上の場合だけ空の認識結果にする。短い名前だけの一致、一般語の部分一致、1秒を超える発言は除去しない。雑音全般の検出器ではなく、設定ヒントの反復に限定した対策。議事録の開始は別途、会話モデルの能力ロードと操作結果を通じて扱う。

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

Whisperを選ぶ環境の設定は次のとおり。ホストの`~/models/faster-whisper/small`に`model.bin`、`config.json`、`tokenizer.json`、`vocabulary.txt`を事前配置する。Composeは親を`/models-whisper`へ読み取り専用でマウントする。モデルを含むディレクトリ全体と取得元の版・SHA-256を保持する。

```dotenv
CIEL_STT_BACKEND=whisper
CIEL_WHISPER_MODELS_DIR=${HOME}/models/faster-whisper
CIEL_WHISPER_MODEL_PATH=/models-whisper/small
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
