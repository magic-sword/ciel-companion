# シエルとベンチマークで共用するGPU推論API

> 責務：共用LLM APIの接続・容量設定・GPU/CPU制御と測定方法。

2026-11-09。自宅サーバーの既存 `ciel-local-llm-1` を共通のOpenAI互換APIとして使う。開発用シエルのローカル役目と、Minecraftベンチマークが同じ重み・推論枠を利用する。Minecraft・体・会話・記憶の分離は維持し、推論APIだけを共用する。

## 接続と容量

| 項目 | 設定 |
|---|---|
| GPU | NVIDIA RTX A2000 12GB |
| モデル | Qwen3.5-35B-A3B-Q4_K_M.gguf |
| 推論API | `http://127.0.0.1:8094/v1` |
| 状態確認 | `GET http://127.0.0.1:8094/health`、`GET http://127.0.0.1:8095/mode` |
| コンテキスト | 1要求32,768トークン、同時2枠 |
| GPU利用 | MoEの専門家の重みはCPU、残りはGPU。全モデルをGPUへ載せる設定ではない |
| 共存 | Irodori・Minecraft・本番/開発シエルは稼働を継続 |

`LOCAL_LLM_CTX` は1要求あたりの容量。明示した `--parallel` ではllama.cppが総容量を各枠へ分割するため、supervisorは `CTX × PARALLEL` を渡す。32,768×2なら `-c 65536 --parallel 2`。実容量は `/props` と `/slots` で確認する。上限は履歴・道具定義・出力を含む。

`/mode` は現在の `mode`、`ready`、モデル名、設定容量、同時枠を返す。歌の分析が始まると既存の制御でCPUへ切り替わり、終了後にGPUへ戻る。共有なので、ベンチマークのためにGPUへ強制固定しない。実験では前後のモード・キャッシュ・同時負荷も記録する。

同じサーバーのhost network上ではそのまま接続する。別ホストからは、既存のSSH認証を使って推論ポートだけを転送できる。

```sh
ssh -N -L 18094:127.0.0.1:8094 <自宅サーバーのSSH接続先>
# そのホストのクライアント
CIEL_LOCAL_LLM_URL=http://127.0.0.1:18094/v1
```

推論・モード変更ポートともループバック待受を維持する。別ホストへのモード変更ポートの転送は不要。現在のシエルクライアントはAPIキー `local` を送るが、これは認証用の秘密ではない。ホスト間の認証はSSHが担う。

## 自宅サーバーの操作

手元のリポジトリのPython環境で実行する。SSH設定は `scripts/server/.env.local` を共用する。

```powershell
.\.venv\Scripts\python.exe scripts/server/shared-llm-home.py status
# 共有LLMだけを更新。推論中・CPU切替中は拒否し、元設定を保存する
.\.venv\Scripts\python.exe scripts/server/shared-llm-home.py configure --context 32768 --parallel 2
# 短文・長文・長文2要求同時。ほかのサービスは稼働させたまま
.\.venv\Scripts\python.exe scripts/server/shared-llm-home.py probe --long-repeats 700
.\.venv\Scripts\python.exe scripts/server/shared-llm-home.py probe --long-repeats 1400
.\.venv\Scripts\python.exe scripts/server/shared-llm-home.py pull
```

`configure` は通常サービスのComposeのLLM容量項目と `.env` の `LOCAL_LLM_CTX`・`LOCAL_LLM_PARALLEL`・`LOCAL_LLM_MODE`、LLMのsupervisor/imageだけを更新する。会話エージェントは再配布しない。APIの短い再起動が発生する。起動失敗・実容量不一致なら元ファイルとイメージへ戻す。バックアップは自宅サーバーの `~/work/ciel-companion/server/local-llm/data/shared-gpu-*/backup/`。秘密を含むバックアップは `pull` の対象外。

以後は通常の `docker compose --env-file .env.shared --env-file .env --profile local-llm up -d --build local-llm` でも、保存した容量を使う。デフォルトはGPU併用。層の割り当てを検討する場合はsupervisorの `LOCAL_LLM_GPU_LAYERS`・`LOCAL_LLM_CPU_MOE_LAYERS` も使えるが、現時点の確認済み値は99・99。32k/2枠より大きい構成や追加の専門家GPU配置は未確認。

## ベンチマークとシエルの接続

ベンチマークは [実行手順](../games/minecraft/minecraft-benchmark-ja.md)の `conversation` が共有APIを使う。`--llm-service dedicated` を指定した場合だけ従来のCPU専用モデルを起動する。専用環境の `stop` は共有LLMを停止しない。

通常のシエルは `CIEL_LOCAL_LLM_URL=http://127.0.0.1:8094/v1` を使う。既存の開発用会話サーバーはこの接続先を設定済み。`CIEL_LOCAL_ROLES` に指定した役目が利用し、全処理をローカルへ切り替える場合は [ローカルモード](local-runtime-ja.md)を参照する。APIを共用する変更と、OpenAIを使う役目の変更は別の設定。


## 評価時の扱い

容量測定は`scripts/server/shared-llm-home.py probe`を使用し、冷間・キャッシュ済み、入力長、同時要求、モード、他サービス負荷を記録する。短いOKの生成で長い道具選択の品質を測定済みとはしない。歌唱によるCPU切替やIrodoriの作業メモリー増加を含む持続的な負荷は別に確認する。

現在の確認済み容量・測定条件・限界は[確認状況](../testing/verification-status-ja.md)に集約する。実行方法と構成を変更した場合も、過去の別条件の値を新しい構成の性能へ置き換えない。

## 画像入力と縮小設定

Qwen3.5-35B-A3B用のmmprojを読み込み、画像エンコーダーは`--no-mmproj-offload`でCPUに置く。言語側のGPU/CPU切替・32k×2枠・共有範囲は同じ。`LOCAL_LLM_MMPROJ`はモデル領域に配置した対応重みのコンテナ内パスで、既定は`/models/mmproj-F16-Qwen3.5-35B-A3B.gguf`。明示的な空値は画像機能を無効化し、指定したファイルがなければ起動を失敗させる。

公開するloopbackの8094は画像の検証・縮小を行う受信口。llama-server自体はloopbackの18094で動く。アプリ・ベンチマーク・他サーバーからは8094を使い、内部ポートへ直接送って前処理を迂回しない。制御は従来どおり8095。画像能力は8094の`/props`で確認する。画像以外の要求・SSEストリームも同じAPIを通し、切断時は上流の接続を閉じる。

本番`server/.env`で共有APIの設定を行う。開発の`.env.dev`で個別に変える設定ではない。

```dotenv
LOCAL_LLM_IMAGE_MAX_EDGE=256
# LOCAL_LLM_MMPROJ=/models/mmproj-F16-Qwen3.5-35B-A3B.gguf
```

画像上限は32～4096の整数で指定できる。既定は幅・高さとも256以内、縦横比維持、拡大なし。512等へ変更する場合も対象local-llmコンテナを再作成する。向き補正・入力制限・情報保持の契約は[画像サービス](../services/vision-design-ja.md#ローカルモデルとapi側の前処理)を参照する。応答ヘッダー`X-Ciel-Image-Max-Edge`が適用上限、`X-Ciel-Image-Count`が要求内の処理画像数を返す。画像内容は応答ヘッダーにもログにも出さない。

## 画像APIを隔離して検証する

常設の縮小処理を経由しないモデル単体の画像互換性・解像度別処理時間は、同じ重みと対応するmmprojを使う使い捨ての8098 APIで確認できる。事前に検証済みの`~/models/llm/mmproj-F16-Qwen3.5-35B-A3B.gguf`と取得元・SHA-256の隣接JSONを配置する。配布元、版、実測は[確認状況](../testing/verification-status-ja.md#ローカルqwenの画像入力)を参照する。

```powershell
.\.venv\Scripts\python.exe scripts/server/probe-local-vision.py cpu
.\.venv\Scripts\python.exe scripts/server/probe-local-vision.py gpu --max-size 1024
```

cpuは共有APIを変更しない。gpuは開始時に共有APIがGPU・準備完了・処理中スロットなしであることを要求し、一時的に共有APIをCPUへ切り替えてGPUを空ける。試験中は通常の文字推論もCPUで遅くなる。終了・失敗時は試験コンテナを削除して元のGPUモードへ戻す。CPUモードを使用中の歌唱処理を強制解除して始めない。

試験は合成画像の色・形・位置・白紙の正解と、最初のトークン・完了時間、キャッシュ、全GPUメモリー、コンテナのcgroup会計を保存する。GPU側の画像処理を無理に追加せず、画像エンコーダーはCPUに置く。256pxだけの結果を大きな添付画像の速度へ一般化しない。利用者の写真やゲーム操作は試験に含めない。共有APIや会話ホストの画像対応設定を恒久的に有効化する手順とは区別する。

## 会話を優先する入場制御の設計

以下は[音声会話の低遅延化](../conversation/conversation-pipeline-ja.md#音声会話の低遅延化)の設計。`gateway.Admission`に有界キューと分類別の同時数制御を実装した。通常サービスへの反映と専用評価の結果は[確認状況](../testing/verification-status-ja.md)を参照する。起動時に準備しても、背景要求が共有枠とキャッシュを使用するため、会話中の待ち時間を別に制御する。

ローカルの`POST /v1/chat/completions`要求を`X-Ciel-Work-Class: foreground|background`で分類する。他のAPIはこの入場制御の対象外。未指定は通常のOpenAI互換クライアントの前景要求、不正な値は400。`models.options`は要約・内なる考え・記憶保守・議事録を背景に分類し、会話・依頼確認等は前景にする。実行中の最大数は構成のparallel、背景は最大1。前景待機があれば背景待機より先に受け入れる。枠はストリーム終了/例外で解放し、待機期限30秒・全体64要求の上限を持つ。待機超過は429、上流タイムアウトは503。`X-Ciel-Admission-Ms`へ待機時間を返す。実行中の背景生成の強制取消は行わない。

新supervisorの`/mode`は`generation`と`generation_scope=inference_process`を持ち、モデルプロセス起動ごとに世代を変える。準備処理は世代識別がない制御先を準備済みとして扱わない。専用評価の`evaluation_gateway.py`は8096/8097で動き、既存8095/8094を読み取り・推論要求の転送に使うだけで通常サービスを更新しない。この世代は専用受信口を指し、上流モデルの再起動世代とは異なる。専用経路を通らない通常クライアントの背景要求まで制御できたとは扱わない。

- 制御は全クライアントが使う8094の受信口へ置く。agent内だけのSemaphoreでは本番・開発・ゲーム等をまとめて調停できない。要求を発言/ジョブ・会話・モデル世代へ結び付け、前景の返答と、延期できる要約・内なる考え等の背景を区別する。分類はホストが付け、利用者の発言本文では決めない。未分類の既存クライアントも黙って制限対象外にしない。
- 2枠構成では、まず背景の同時実行を最大1に制限する案を比較する。前景は必要に応じて2枠を使い、会話間は公平に扱う。これは固定のslot IDを占有する案ではなく、入場する要求数の制御である。推論中にロックを保持して全要求を直列化しない。
- 利用者の発声開始で新しい背景推論を保留し、未開始の同種要約は最新へまとめる。実行中の背景LLMは取消可能な純粋な生成だけを対象とし、打ち切りで道具・記憶保存等の処理を成功扱いにしない。HTTPを閉じただけで上流の計算が即時停止したとは仮定せず、取消完了・枠解放まで計測する。保留中の必要な保守処理は失わず、会話の合間に再開する。
- キュー待ち、実際の推論開始、最初の出力、終了/取消、入力トークン数、再利用した先頭部分を観測する。通常のTTFTだけからキュー待ちと入力前処理を切り分けたと断定しない。要求数と待機時間に上限を持たせ、失効した古い返答を後から再生しない。
- モード変更・再起動で利用可能な枠と準備世代を更新する。歌のためのCPU切替を優先制御で無効化せず、切替中・CPU中を別の性能条件として扱う。追加GPUモデルや、未検証の枠数増加は初期案に含めない。

最初の比較は通常会話、背景要約あり、複数会話、ゲームと共存、CPU切替の条件を分ける。実際の稼働版のllama.cppで取消・キャッシュ・枠の動作を確認してから共通の要求形式と実装を変更する。本節の記述は新しい要求形式の配布済み契約ではない。
