# CPUで動くローカル音声認識（Vosk）

2026-11-10。Vosk 0.3.45と日本語小型モデル`vosk-model-small-ja-0.22`を自宅サーバーへ配置し、CPUだけの逐次認識を測定した。会話サーバーへの接続コードも実装し、実際のLiveKit SDKとの結合を隔離コンテナで確認した。通常の開発用・本番会話サービスはこの測定で再配置・再起動していない。人のマイク音声による会話全体の性能は未測定。

## 責務と入力の扱い

Unityから受け取る音声を、会話ホストのVosk STTアダプターがCPUで逐次認識する。LLMが選ぶMCPツールではなく、常時の入力経路。モデルは会話ワーカーのプロセス内で共有し、認識器は音声ストリームごとに分離する。GPUを割り当てず、モデルのロード・認識を別スレッドで行う。

途中結果はLiveKitのINTERIM_TRANSCRIPT、認識区間の確定結果はFINAL_TRANSCRIPTへ渡す。入力終了時には残りを確定し、途中結果を勝手に確定へ昇格させない。会話ホストの発話区切り・割り込み・話者識別・確定した依頼の受付は既存処理を使う。日本語トークン間の空白を整理し、停止の依頼が分断されないようにする。ASCII語句内の空白は保持する。

`CIEL_LLM_BACKEND=local`の音声入力はVoskが既定。OpenAI STTへ自動で戻さず、モデル未配置・不正設定は明示的なエラー。`CIEL_INPUT=text`なら音声モデルをロードしない。OpenAIのLLMとVoskの併用も可能だが、LLMの課金は別に発生する。Voskはpipeline＋Irodoriでのみ利用でき、Realtimeモードへの指定は起動時に拒否する。

## 設定する.envを区別する

| 起動方法 | 設定ファイル | 変数 |
|---|---|---|
| 本番Docker Compose | 自宅の`~/work/ciel-companion/server/.env` | `CIEL_LLM_BACKEND=local` |
| 開発用Docker Compose | 自宅の`~/work/ciel-companion-dev/server/.env.dev` | `CIEL_DEV_LLM_BACKEND=local` |
| Pythonの会話サーバーを直接起動 | `server/agent/.env` | `CIEL_LLM_BACKEND=local` |

`CIEL_DEV_*`はComposeがコンテナの`CIEL_*`へ変換する。`server/agent/.env`に`CIEL_DEV_LLM_BACKEND`を書くだけでは切り替わらない。コンテナのenvironmentはenv_fileの同名設定より優先される。

本番・開発の切替・反映単位は[共通の実行設定](local-runtime-ja.md)を参照する。本番にも同じVoskアダプターとモデルマウントを使える。

開発用の見本は[server/.env.dev.example](../server/.env.dev.example)。既存.env.devを上書きせず必要な行を編集する。

```dotenv
CIEL_DEV_LLM_BACKEND=local
CIEL_DEV_INPUT=voice
# 通常は空。LLM_BACKEND=localなら自動でvoskになる。
CIEL_DEV_STT_BACKEND=
CIEL_DEV_VOSK_MODELS_DIR=${HOME}/models/vosk
```

モデルはホスト側`~/models/vosk/vosk-model-small-ja-0.22`に置く。Composeは親ディレクトリを`/models`へ読み取り専用でマウントする。モデルはGitへ含めない。直接Pythonで動かす場合は`CIEL_MODEL=pipeline`、`CIEL_VOICE=irodori`、`CIEL_VOSK_MODEL_PATH`に実際のモデルディレクトリを指定する。

コードの開発用反映後、開発用serverディレクトリで再ビルド・再作成する。設定を編集しただけや単なるrestartでは既存コンテナへ反映されない。

```sh
docker compose --env-file ../../ciel-companion/server/.env --env-file .env.dev \
  -f compose.dev.yaml up -d --build agent-dev
```

共有LLM API、Irodori、LiveKitとDBは既存のものを使う。Minecraftベンチマークは従来どおり`CIEL_INPUT=text`を明示しており、この変更で音声評価へ変わらない。アプリは会話を接続し直して新しい設定を使う。

## 初期測定

自宅サーバーの隔離ディレクトリ`~/work/ciel-vosk-test`、CPU上限2論理CPU・メモリ上限3GiBの一時Dockerコンテナで測定。ホストは24論理CPUで、通常サービスを稼働させたまま。LLMの同時推論負荷を制御した試験ではない。GPUデバイスは渡していない。音声認識のためのGPU割当はないが、試験音声を作るIrodoriは既存のGPUサービスを使う。

試料はIrodoriに3文を読ませた合成音声。16kHz・モノラルPCM16、100ms刻みで逐次入力し、末尾に2秒の無音を追加。各文を非実時間1回と実時間1回ずつ測った。初回モデルロードは約0.264秒、プロセスの最大RSSは約335MiB。非実時間では無音込み6.44〜8.48秒の入力を約1.57〜2.75秒で処理した。

| 試料 | 元の音声長（末尾追加無音を除く） | 最初の途中結果 | 元音声の入力終了から最後の自然確定 | 合成要求文とのCER |
|---|---:|---:|---:|---:|
| 1 | 4.44秒 | 865ms | 390ms | 45.5% |
| 2 | 4.48秒 | 767ms | 736ms | 20.0% |
| 3 | 6.48秒 | 878ms | 765ms | 54.8% |

上記は音声を実時間で送った結果。初回モデルロードやネットワーク輸送は含まず、発話終了からシエルの返答開始までの時間ではない。確定待ちは人の発話終端を測った値ではなく、元WAVの末尾から計算した値。非実時間の結果出力時刻を、利用者が待つ遅延として扱わない。

**速度の成立は確認できたが、この小型モデルの認識精度は採用判断を保留する。** 合成要求文に対する合計CERは31/73文字＝約42.5%。例：原木→原爆、石のツルハシを正しく認識できない。合成音声自体の読み間違いも含み得るため、人の声に対するASRの誤り率とは断定しない。認識文をLLMで修正して測定値を良く見せる処理は行っていない。これらの認識結果から実際のゲーム操作は実行していない。

LiveKit SDK＋実Voskの別の結合確認では、入力終了前に途中結果9件・確定2件を受信。最初の途中結果は約875ms、20ms周期のイベントループ確認の最大間隔は約36ms。合成試料1文の確認であり、Unityマイク・実際のLiveKit接続・音声応答・割り込み全体の保証ではない。認識中にOpenAIは呼んでいない。

今後は実際のマイク録音、雑談、ゲーム固有名詞、短い停止依頼を同じ条件で測る。必要なら日本語大型モデルや別のCPU認識器を比較し、精度・途中結果・確定待ち・CPU/RAM・既存LLMへの影響を分けて評価する。音声認識で誤ったものを「ローカルLLMの実行失敗」と混同しない。

## 再実行と結果の保存

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/vosk-home.py stage
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/vosk-home.py run
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/vosk-home.py integration
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/vosk-home.py pull
```

stageは評価コードだけを専用ディレクトリへ送る。runは公式日本語モデルを初回だけ取得し、合成試料を生成して測定する。integrationは既存の開発用エージェントイメージを元にした一時コンテナにVoskを入れ、実際のSDKアダプターを検証する。稼働コンテナを変更する操作ではない。両コンテナは終了時に削除し、モデル・試料・測定値は残す。

初回測定の保存先はサーバーの`results/20261109T230534Z`（UTC、日本時間2026-11-10）。ローカル回収先はGit対象外の`server/benchmark/data/vosk-cpu/report.json`。モデルアーカイブのSHA-256、コード指紋、評価イメージIDと制限値を記録した。初回は計測後のメタデータ書込で所有権エラーになったが、完了済みの結果をそのまま回収した。GPU使用量の前後サンプルは保存できなかったため比較値を捏造していない。次回用helperは実行ユーザーを指定するよう修正済み。

オフライン回帰は`test_vosk_stt.py`。途中結果の先行、重複抑制、EOF確定、モデル不在、文字モード、OpenAIへのフォールバック拒否、実際のpipeline組み立て関数のVosk分岐を確認する。通常テスト641件合格。Composeの環境変数とモデルのマウント先も自宅サーバーのComposeで検証した。通常の会話サービスへの配布と人のマイク試験は未実施。

参考：[Vosk公式](https://alphacephei.com/vosk/)、[日本語モデル配布元](https://alphacephei.com/vosk/models)、[ローカルLLM](local-llm-ja.md)。
