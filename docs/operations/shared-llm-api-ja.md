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
