# GPU共用・改修前の比較用一巡（2026-11-09）

会話7課題を配置11・各1回で実施し、3合格・4失敗、環境障害・未実施0。準備から片付けまで **6分2.918秒**、runnerは **5分27.495秒** で終了した。今後の改修と同条件で照合するための暫定記録で、複数配置・反復による性能基準や、GPU共有化だけの因果効果を示す対照実験ではない。

## 条件と識別情報

- 自宅サーバーの専用プロジェクト `ciel-minecraft-benchmark`、試験プレイヤー `Ciel_Debug`、Minecraft 1.21.11。
- conversation/local、practical-v1、全7課題、配置seed 11、各1回、全体600秒。全課題を見るため `--failure-streak 0` とし、課題別の期限・操作未発行・不進行などの早期終了は維持した。
- シエル共用API `127.0.0.1:8094/v1`、Qwen3.5-35B-A3B-Q4_K_M.gguf、GPU/CPU併用、1要求32,768トークン・2枠、RTX A2000 12GB。
- 通常の9サービスを稼働させたまま、追加の予備推論・合成負荷・キャッシュ消去・自動再試行は行っていない。サービスの起動状態を維持した条件であり、利用者が継続して会話する負荷を再現したものではない。
- コミット `1e8c530f0b629df98c45a949e296e2c55fd5b51d`、測定時dirty=false。実行中にアプリ・プロンプト・評価器を変更していない。

```text
実行ID: gpu-shared-reference-20261109T123442Z
source_sha256: 7bd833599875478a5d2d64300f8e2d1fbccfed19233c71f4b25d3036758b7b09
suite_sha256: 1af0134e443e5cbbdfcaa3e8b6138d715fd8875227b765694e72c592bb3a3687
```

runnerはPython 3.11.18、livekit 1.1.18、livekit-agents / plugins-openai 1.8.3、openai 2.54.0、mcp 1.30.0。GPUドライバー560.35.03。共有LLM・Irodori・通常agent・試験用各イメージのIDと、評価器各ファイルのSHAは `environment.json` に保存した。

## 結果

時間は秒。評価時間は依頼から採点終了まで、到達時間は実物の条件を初めて確認した時刻で、準備・切断は含まない。

| 課題 | 結果・終了理由 | 評価時間 | 初回操作 | 到達時間 | LLM / ゲーム要求 |
|---|---|---:|---:|---:|---:|
| 原木8個 | 成功 | 53.900 | 5.593 | 48.829 | 4 / 1 |
| 木のつるはし | 操作未発行で終了 | 30.068 | — | — | 2 / 0 |
| 石のつるはし | 不進行で終了 | 59.386 | 5.567 | — | 5 / 2 |
| 不足材料の補充 | 成功 | 44.126 | 8.098 | 39.042 | 5 / 7 |
| 遠くの原木の探索・採集 | 成功 | 55.202 | 6.061 | 50.148 | 5 / 2 |
| 材料なしの製作判断 | 操作未発行で終了 | 30.337 | — | — | 2 / 0 |
| 採集中の停止 | 採集開始前に操作未発行で終了 | 30.396 | — | — | 2 / 0 |

目的達成3件、適切な断念0件。成功3件とも条件成立後5秒以内の完了返答は未観測。停止課題は原木を取得できず、停止指示の段階まで進んでいないため、「停止指示を無視した試行」とは扱わない。3/7は現在の評価器による今回一巡の値で、ばらつきを推定できる反復数ではない。

評価時間合計は303.415秒。runnerの準備・終了処理等を含め327.495秒、ビルド・Minecraft起動・専用サービス停止を含むcontroller時間は362.918秒。終了コード1は課題失敗を含むためで、manifestはcomplete。cleanupは0、通常9サービスのコンテナIDが測定前後で同一、専用サービスのみ停止済み。

## GPUとキャッシュ

約1秒間隔の320回の観測ですべてGPUモード、観測エラー0。観測の間に短時間のモード変更がなかったことまでは保証しない。GPU使用量の最大10,768MiB、空き最小1,168MiB、使用率の最大100%、処理中の推論枠の最大2。

完了した利用量記録では、入力キャッシュが約96.6〜97.3%使われていた。前の利用からキャッシュを保持した測定であり、冷間の初回推論時間とは比較しない。途中で打ち切られた要求の利用量が欠けることもある。APIの利用者を識別していないため、2枠の使用を通常シエルと試験agentのどちらが占めたかは断定しない。

## 次の改修へ引き継ぐ観察

操作未発行の3課題は、いずれも `mind_output` があり `tools=[]`、実際のゲーム要求0回だった。木のつるはしと原木64個の課題では、生成テキストに作業を行って完了したという筋書きがある。材料なし課題では、存在しない近くの原木に言及し、道具呼び出しらしい文字列を本文へ出していた。これらは応答が一切返らなかったケースではなく、文章と実行の不一致として調べる。利用者に届いた発言の虚偽率を全件審査した集計ではない。

材料補充の成功例は `start_goal` で目的実行器へ委譲し、丸石が見つからない失敗を探索で修復して製作した。個別操作を返す場合との違いは調査候補だが、この一巡で委譲だけの効果を分離したとは言えない。

採点上の注意もある。石のつるはしでは原木を集めた後、作業台製作の成功通知があり、その約15秒後に不進行で終了した。現ポリシーは所持品の最高値と新規移動を進捗とするため、設置済みの作業台などを捉えきれない場合がある。30秒間まったく有用な操作がなかったとは断定しない。進捗oracleを変更するなら、旧アプリも新しい評価器で測り直して比較する必要がある。

また、次の試行の準備中にも前課題の原木採集完了snapshotを受信した記録がある。所持品は正しく0に初期化されているが、モデルの判断へ古い作業履歴が影響したかは未確定。試行間の状態分離も確認候補として残す。元の採点値・traceはこの調査のために書き換えていない。

## 次回の比較方法

まず同じ7課題・順序・配置11・1回・practical-v1で比較し、各課題の合否・終了理由・初回操作・到達時間・要求数を見る。成功試行だけが減って速く見える比較は避ける。今回成功した課題の悪化、報告・停止まで進めたかも確認する。

共有モデル・量子化・容量・枠数、通常サービスの負荷、追加予備推論なしという方針を揃え、キャッシュ利用率も確認する。共有キャッシュと負荷の揺らぎがあるため、単発の秒数差を性能改善の確証にはしない。評価器・課題・期限を変える場合は条件変更として扱う。旧CPU・900秒条件の54試行との成功率比較には使わない。

改修でsystemや道具定義の接頭辞が変わる場合は、キャッシュの効き方も変わる。温間同士の比較が必要なら両版に同じ予備実行を定義し、その条件で比較用の記録を取り直す。変更版だけを合格するまで温めて今回の記録と比較しない。

配置先 `~/work/ciel-companion-benchmark/server` で使ったrunner引数は以下。共有APIの確認と、試験用サービスの起動・ビルドは [実行手順](minecraft-benchmark-ja.md) に従う。

```sh
CIEL_BENCH_LLM_SERVICE=shared \
CIEL_BENCH_LLM_URL=http://127.0.0.1:8094/v1 \
CIEL_BENCH_LLM_CONTROL=http://127.0.0.1:8095 \
docker compose --env-file .env.benchmark -f compose.benchmark.yaml \
  --profile conversation --profile runner run --rm --no-deps benchmark-runner \
  --mode conversation --backend local --seed 11 --repeats 1 \
  --run-seconds 600 --failure-streak 0 \
  --output "/workspace/server/benchmark/data/results/after-change-$(date -u +%Y%m%dT%H%M%SZ)"
```

## 保存先

自宅サーバーの `~/work/ciel-companion-benchmark/server/benchmark/data/results/gpu-shared-reference-20261109T123442Z/`。controller・実行コマンド・環境・GPU観測・試験agent/bodyログ・試行別traceと採点を保存した。

同じディレクトリへ `comparison-reference.json`・`measurement-summary.md`・測定時ソース `source.tar.gz` も保存済み。手元とのハッシュ照合と、元の `conversation/report.json` が変更されていないことを確認した。

手元は `server/benchmark/data/home-import-1794228093657241600/results/gpu-shared-reference-20261109T123442Z/`：

- [採点結果](../server/benchmark/data/home-import-1794228093657241600/results/gpu-shared-reference-20261109T123442Z/conversation/report.json)
- [比較条件と照合用JSON](../server/benchmark/data/home-import-1794228093657241600/results/gpu-shared-reference-20261109T123442Z/comparison-reference.json)
- [自動集計](../server/benchmark/data/home-import-1794228093657241600/results/gpu-shared-reference-20261109T123442Z/measurement-summary.md)
- [環境・イメージ・評価器のSHA](../server/benchmark/data/home-import-1794228093657241600/results/gpu-shared-reference-20261109T123442Z/environment.json)
- [GPU・モード・推論枠の観測](../server/benchmark/data/home-import-1794228093657241600/results/gpu-shared-reference-20261109T123442Z/runtime.jsonl)
- [測定時のソース](../server/benchmark/data/gpu-shared-reference-1e8c530-source.tar.gz)。SHA256 `5647946f52419719d89f6d31066a6142aca3a037bd35464c67a5cc826dcfa368`。

生の結果とソースアーカイブはGit対象外。文書のコミットだけでこれらも保存されたとは扱わない。
