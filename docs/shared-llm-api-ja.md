# シエルとベンチマークで共用するGPU推論API

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

以後は通常の `docker compose --profile local-llm up -d --build local-llm` でも、保存した容量を使う。デフォルトはGPU併用。層の割り当てを検討する場合はsupervisorの `LOCAL_LLM_GPU_LAYERS`・`LOCAL_LLM_CPU_MOE_LAYERS` も使えるが、現時点の確認済み値は99・99。32k/2枠より大きい構成や追加の専門家GPU配置は未確認。

## ベンチマークとシエルの接続

ベンチマークは [実行手順](minecraft-benchmark-ja.md)の `conversation` が共有APIを使う。`--llm-service dedicated` を指定した場合だけ従来のCPU専用モデルを起動する。専用環境の `stop` は共有LLMを停止しない。

通常のシエルは `CIEL_LOCAL_LLM_URL=http://127.0.0.1:8094/v1` を使う。既存の開発用会話サーバーはこの接続先を設定済み。`CIEL_LOCAL_ROLES` に指定した役目が利用し、全処理をローカルへ切り替える場合は [ローカルモード](local-llm-ja.md)を参照する。APIを共用する変更と、OpenAIを使う役目の変更は別の設定。

## 測定条件と限界

容量試験は合成した持ち物情報を使い、短文・長文1要求・長文2要求同時の順に送る。キャッシュは保持し `cached_tokens` を記録する。現在のhelperは実行IDも先頭へ入れて過去の実行との共通接頭辞を避ける。下記の29k測定時には前回と同じ要求識別子を再利用しており、約14.2kトークンのキャッシュを含む。返答は最大32トークンの「OK」。これで長い道具選択の品質や持続的な生成速度を評価したとは扱わない。

要求時間・最初の文字までの時間・入力/出力トークン・サーバーのtimingsと、約0.5秒間隔のGPUメモリ使用量を保存する。通常サービスは稼働させているが、常に利用者の会話が流れているという条件ではない。共有枠が埋まると他クライアントに待ち時間が生じる。Irodoriの作業メモリ増加、歌の分析、要求集中を含む長時間の負荷保証は別途必要。

CPUで行った [各54試行の基準測定](minecraft-benchmark-baseline-2026-11-09-ja.md)は、その条件のまま保持する。今回のAPI容量試験と単発のMinecraft確認から、全課題の成功率改善は結論づけない。

## 実測結果（2026-11-09）

GPU併用・32,768トークン/要求・2枠で以下を完了した。通常サービスは停止していない。29.4k×2要求までの処理を確認したもので、最大可能容量を探索し尽くした結果ではない。

| 合成API要求 | 入力トークン/要求 | キャッシュ/要求 | 応答完了まで |
|---|---:|---:|---:|
| 短文1要求 | 455 | 0 | 1.753秒 |
| 長文1要求 | 14,736 | 0 | 35.288秒 |
| 長文2要求同時 | 各14,738 | 各15 | 50.065秒・72.124秒 |
| 長文1要求 | 29,436 | 14,220 | 37.928秒 |
| 長文2要求同時 | 各29,438 | 各14,222 | 57.302秒・77.758秒 |

API容量試験のGPU使用量ピークは10,748MiB、空き最小1,188MiB。約14.7k入力の単独要求でサーバーが記録した入力処理は約419トークン/秒。ただし2トークンしか生成していないため、持続的な出力速度の基準にはしない。同時処理では入力処理と生成の競合・待ち時間が観測される。

本番シエルのコンテナ `ciel-agent-1` からも同じAPIへの直接要求を確認した。Minecraftの推論と重ねた短文16入力トークンは応答42.197秒。接続できることと、共有時に短文も待たされることを確認した。通常シエルの役目別ルーティングをこの検証のために変更してはいない。

Minecraftは共有GPUで `gather_logs`・配置11・1回、上限180秒を実行し成功。原木8個の取得113.388秒、完了観測込み143.717秒、LLM要求4回・ゲーム要求1回。完了後30秒以内の返答観測はfalse。試行の後半約37秒のGPU観測はGPUモードを維持し、ピーク10,768MiB・空き最小1,168MiBだった。全試行期間をGPU監視した記録ではない。

試行は `manifest.completion=complete`・終了0。終了時にLiveKit転送とMCP切断の警告が出ており、終了処理の雑音は残る。専用のMinecraft・体・試験agentは停止済み。共有LLMと通常の8サービスは稼働を維持している。568件の通常回帰と、配置メタデータ追加後の関連5テストが成功した。

保存先：

- 自宅サーバー：`~/work/ciel-companion/server/local-llm/data/` の `shared-gpu-20261109T110628Z/configuration.json`、`capacity-20261109T110643Z/report.json`、`capacity-20261109T110924Z/report.json`、`client-verification.json`、`minecraft-shared-gpu.json`。
- 手元：[14.7k API測定](../server/benchmark/data/shared-api-import-1794223022247818000/data/capacity-20261109T110643Z/report.json)、[29.4k API測定](../server/benchmark/data/shared-api-import-1794223022247818000/data/capacity-20261109T110924Z/report.json)、[本番コンテナからの確認](../server/benchmark/data/shared-api-import-1794223022247818000/data/client-verification.json)、[Minecraft試行](../server/benchmark/data/home-import-1794222996390851800/results/smoke-conversation-1794222790908107426/report.json)。生データはGit対象外。

Minecraft試行のsource SHAは `9546e1a332559d8235a015b1af16615ec10713c7b9c65ebc96ed45e4168a0ce2`。配置元は `aa41407bf85e5d5346071fa4f1cf0acf6d46aa55` と作業差分で、共有LLMの設定記録にファイルSHAも保存した。試行manifestのGitラベルには古い `de23213...` が残っていた。配置情報のtar時刻が0固定で、Dockerが同じ長さの古い配置情報を再利用していたため、現在時刻を付けるようhelperを修正した。再ビルド後にGitラベルaa41407と同じsource SHAを確認済み。元の試行manifestは書き換えていない。
