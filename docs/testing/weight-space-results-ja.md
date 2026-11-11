# 人格と身体表現の指示の実測

> 責務：人格・身体表現の指示候補の採点条件、採用判断、残課題、生データ。

[評価の見取り図](benchmark-guide-ja.md#人格と身体表現の指示)と[課題・採点の方法](weight-space-benchmark-ja.md)から読む。自動採点と人による品質判断を区別する。

## 現在の判断

同一のdev32課題で基準26/32、候補29/32の自動通過を確認した。ただし候補には引数失敗1件が残り、人手評価27件と未使用課題の確認が終わっていないため不採用とした。通常の人格指示とモデル重みは維持している。自動形式の改善を人格品質の改善とは判定しない。

## Weight-Space Programmingの評価基準

[評価仕様](weight-space-benchmark-ja.md)と[研究・実施方針](../operations/weight-space-programming-ja.md)に従い、同じ重みでプロンプト候補を比較した。重み編集・本番モデルの置換は実施していない。GCAの理論提案と外部記憶への適用範囲も整理した。音声とMinecraftの既存実測を今回の成果として扱わない。

2026-11-10、`scripts/server/weight-space-home.py`で `~/work/ciel-weight-space-benchmark`へ評価器・課題・5promptを配置し、共有8094を使用。Qwen3.5-35B-A3B-Q4_K_M、RTX A2000 12GB、GPUモード、context32768、parallel2。温度0、seed1729、上限512token、thinking無効、課題期限60秒、dev32課題各1回。開始・終了modeはgpu/ready。通常共有先の同時負荷・途中の切替は制御していない。

ゲーム課題に実契約との不一致（`count`と空の制約）があったため、正式な`CAPABILITIES`から`quantity`・`quantity_mode`・制約を生成するチェックを追加し、基準も再測定した。旧suiteの基準27/32・候補1の28/32は正式比較から除外。採点を緩めず、両版を同一suite・runnerで比較した。

| 条件 | 自動通過 | fixtureが拒否した引数失敗 | 基準からの新規自動退行 |
|---|---:|---:|---:|
| 基準（`8c33866`のprompt） | 26/32 | 1 | — |
| 候補2（身体・感覚の根拠、指定形式） | 28/32 | 2 | 0 |
| 候補3（さらにサービスIDと解釈規則を明記） | 29/32 | 1 | 0 |

候補3の改善は`gesture-dev`（描写だけからload→実call）、`extract-dev`（コードフェンスなしJSON）、`logic-dev`（正しいCのみ）。残る失敗は`submit-dev`（採集のgainをinventory_targetに誤解）、`math-dev`（正解20に対し12）、`multi-name-dev`（敬称・語尾の付加）。引数失敗はモデル出力に由来する`ValueError: Unexpected tool or arguments; fixture refused`であり、接続障害ではない。実際のゲーム・app操作は行っていない。

目視では未接続の右手操作への虚偽の完了報告がなくなった一方、慰める返答では長い演技描写や「心の匂い」という表現が残る。各版27件の人手採点が未完了で、身体性・人格の自動通過は意味内容の合格を表さない。`compare --change prompt`は新規退行0でも引数失敗が残るため`reject`。候補3は`server/benchmark/weight_space/prompt_candidates/grounded-body-v1/`へ別保存し、通常promptは基準版へ戻した。本番未反映。採用条件を満たしていないためholdoutは未実施。

固定promptの文字数は2998→3712（token数ではない）。人格6課題の完了p50は2.48→2.56秒、ツール7課題のうち観測完了6件のp50は3.55→3.81秒。うなずきでは新たに実callが入るため処理内容も異なる。各1回で共有負荷・キャッシュを制御しておらず、高速化の根拠にはしない。実音声・Voskの誤認識・MCP疎通は今回未測定。

測定時のソースは基準commit `8c33866`に未コミット変更を含み、再実行コード・suite・候補3は`61ac247`でコミットした。専用配置はGitなしでreportのcommit=null。runner SHA-256 `b0bc0bcf9859c3307b34d2694e49ec66b198e68de1e63f4899a1f2f5560c37b5`、suite `1814c3c9b68a9c6c3e1b846227347a74cffee1e6f8e2b79344e4614198b1b2bd`。promptは基準`2b24572d756120d9b9e768c4762ec344676e05f7189d928355cdf0a9d1dc1c52`、候補2 `2de46fbe922633162aed533276bf70792c69eb122c91c420dcd42ee43fc25bdb`、候補3 `58dc9cba876b0704c1b0c114739d17f01c7b1d98f75e922a147532df7c9d6c39`。実GGUF SHA-256は全条件`3b46d1066bc91cc2d613e3bc22ce691dd77e6f0d33c9060690d24ce6de494375`。

生データは自宅`~/work/ciel-weight-space-benchmark/results/`の`contract-base-dev`・`contract-candidate-dev`・`contract-candidate3-dev`。取得先はGit対象外の`server/benchmark/data/wsp-<同名>/`にある`report.json`と`human-review.json`。基準・候補3とrunner・suiteのスナップショットは`server/benchmark/data/wsp-prompt-sources/`にも保持する。旧suiteの予備試験は`wsp-prompt-base-dev`・`wsp-prompt-candidate-dev`。通常回帰685件成功（`server/benchmark/data/wsp-prompt-regression/report.json`、DB非選択）、独立評価器20件成功、契約同期チェック成功。重み編集器と高精度checkpointの準備、未使用系列・反復、人手評価、実ホスト全promptでの比較は残る。
