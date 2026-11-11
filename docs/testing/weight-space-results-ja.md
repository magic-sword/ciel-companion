# 人格と身体表現の指示の実測

> 責務：人格・身体表現の指示候補の採点条件、採用判断、残課題、生データ。

[評価の見取り図](benchmark-guide-ja.md#人格と身体表現の指示)と[課題・採点の方法](weight-space-benchmark-ja.md)から読む。自動採点と人による品質判断を区別する。

## 現在の判断

以下の7/7・6/7や12/12は実行・契約の観測値で、会話品質の総合点ではない。EOS1.05倍の7課題で差が出なかったことから、量子化WSP全般の失敗や改善余地のなさを結論しない。長い反復会話を再現できる課題と意味内容の採点が不足しているため、[段階1〜5の評価設計](weight-space-benchmark-ja.md#段階15の会話評価の全体設計)に沿って評価の感度を先に確認する。既存の会話応答は観点別指標で再集計済み。品質レビューと段階4〜5の対話suiteは未完了。

量子化35Bの直接編集も試行した。EOS出力行のスケールを1.05倍にした候補は、同一CPU条件の7課題で基準と同じ本文・ツール操作になり、改善は確認できなかった。候補は実験用として保存し、本番未採用。

## 量子化35BのEOS重み編集

2026-11-12、`gguf_eos_edit.py`で現行GGUFのコピーを作り、`output.weight`のEOS248046（`<|im_end|>`）行だけを編集した。Q6_Kの8個のFP16ブロックスケールを1.05倍。全ファイルの比較で変更8byte、その他のバイトは一致。逆量子化後の差分ノルム0.0427085、元行に対する比率0.0499786、理想的な1.05倍からの丸め誤差ノルム比0.00115282。2048要素に影響する。行のスケーリングであり、論文の内部ニューロン修正の再現ではない。

未編集SHA-256は`3b46d1066bc91cc2d613e3bc22ce691dd77e6f0d33c9060690d24ce6de494375`、候補は`22d9ccc7130b931ed0182b3244c3d58aa870ab430dd4a58b89881d449148b1b5`。解析はgguf0.19.0・numpy2.5.4。候補は自宅`~/work/ciel-weight-space-quant/eos105.gguf`、変更manifestは隣接`eos105.json`。

GPU空き約1140MiBのため、両版とも専用CPU8threads・40GiB制限・context8192・parallel1・loopback18099で順に測定。Docker imageは`sha256:e10aeca66870049b03257b0e5404e018bfea6f598cb9d1a61dd505a913fd48eb`。現行5prompt、温度0、seed1729、thinking無効、512token、課題180秒。会話4課題は8返答、既存3課題はJSON・計算・停止fixture。各1回の予備試験。前節の共有GPU測定とは条件が違うため直接比較しない。

| 指標 | 未編集 | EOS1.05倍 |
|---|---:|---:|
| 完走 | 7/7 | 7/7 |
| 自動check通過 | 6/7 | 6/7 |
| 会話8返答の文字数（課題順） | 33,202,31,57,77,125,37,44 | 同一 |
| 文字数目安超過 | 0 | 0 |
| 空返答・token上限・例外 | 0 | 0 |

全7課題の返答本文と構造化ツール名・引数・順序は一致。停止callのランダムIDだけ異なる。計算課題は両版とも20という正しい数を含むが、厳密出力に説明文を付けたため自動check失敗。6/7は自然さ・反復・人格の総合品質点ではない。余計な質問や訂正時の不要な謝罪も変わらない。5%のスケール変更では、この貪欲生成条件の選択トークンを変えなかった。

重みを変更して実行する経路は確認できたが、改善は未確認のため不採用。全dev・holdout・長い反復会話・2名の人手採点・実音声・より広い一般性能は未測定。強度を際限なく上げず、次は終了直前と継続中のlogit差・活性を観察して、文末だけに効く方向を選ぶ必要がある。高精度checkpointを用いた内部層の因果解析は未実施。

結果・ログは自宅`~/work/ciel-weight-space-quant/pilot-01/`。ローカルの`server/benchmark/data/gguf-eos-pilot-01.json`に両report・編集manifest・ソース・promptと終了確認を保存した。専用コンテナは削除済み。共有モデルはgpu/ready、推論プロセスgeneration `b668da4b0f25403ea308cb9b63ba3dee`を維持。通常モデルの重み・設定は変更していない。

段階1〜3の会話は2026-11-12に現行promptと`concise-dialogue-v1`を比較した。各12会話・28返答を完走。候補は短文化したが提案の欠落があり採用を見送る。以下の旧64課題suiteでの指示比較とは別測定。

## 段階1〜3の会話測定

共有Qwen3.5-35B-A3B-Q4_K_M、RTX A2000 12GB、GPU、context32768、parallel2。dev12会話を各1回、温度0、seed1729（後続ターンは加算）、thinking無効、各返答512token、会話全体180秒。固定5promptによる直接API試験。基準→候補の順で、共有負荷・キャッシュは制御していない。両版とも開始・終了gpu/ready。途中のモード切替は監視していない。反復・逆順実行・holdoutは未実施。

| 指標 | 基準 | 簡潔化候補 |
|---|---:|---:|
| 自動完走（品質合格ではない） | 12/12会話 | 12/12会話 |
| 段階1 / 2 / 3の完走 | 4/4、3/3、5/5 | 4/4、3/3、5/5 |
| 観測返答数 | 28 | 28 |
| 文字数 平均 / 中央値 / p95 | 77.1 / 68 / 134 | 61.6 / 47 / 124 |
| ターン別文字数目安超過 | 2/28 | 0/28 |
| 疑問符を含む返答 | 21/28 | 15/28 |
| 同一返答内の完全一致反復文 | 0 | 0 |
| 過去返答からの完全一致再利用文 | 2 | 1 |

再利用には両版とも依頼された再説明1件を含むため、不要反復率とは呼ばない。疑問符は必要な質問も含む記述統計。今回の短い会話では大量の反復ループは再現していない。

候補は`character.md`へ台詞だけの出力、最新発言への一つの反応、不要な再質問の抑制、短文化希望の維持、必要な詳説・再説明を追加した。残り4promptと重みは同一。候補は`server/benchmark/weight_space/prompt_candidates/concise-dialogue-v1/`に保存。

Codexによる非盲検の探索的レビューでは、事実質問の余計な質問と、聞き直しの余計な嗅覚演出が消え、曜日訂正後に正しく「土曜日」と回答した。短文化要求後の次の話題も一文になった。一方、`chat-s3-end-dev`の最初の返答は基準の具体的提案から、候補では質問だけになり「一つ考える」を満たさない。犬を連れた散歩を勝手に前提とする回答、質問の付け足し、口調・一人称の揺れも残る。自動完走はこれらの意味上の欠陥を検出しない。2名の人手採点は未実施で、品質の総合点は未確定。

`compare --change prompt`は同一条件確認を通過し`review_required`、新規自動失敗0。意味上の退行があるため候補を本番採用しない。旧64課題のツール・一般性能回帰、実ホスト、実音声は今回未測定。

生データは自宅`~/work/ciel-weight-space-benchmark/results/chat-baseline-dev-01/`と`chat-concise-dev-01/`。取得先は`server/benchmark/data/chat-baseline-dev-final/`と`chat-concise-dev-final/`。後者に`comparison.json`も保存。全返答・各ターンの指標・未入力の人手レビューを含む。

suite SHA-256 `1fd6d1c577287a33b457f0baf96e4f46f98d5372e177bc96ce85ead3fd54fc47`、runner `ee484239f4cce630a43d7777622f966559b8007fd736c4beeb4fe804dc6efb54`、基準prompt `b510822e248ea661bb595e91891e49da1f1b1b7f82fe19b29228308cec85e9d7`、候補prompt `b63c18d2ac92a5b28a20b24685ca53a330666162f6baf91785f2574486319348`。実GGUF hashは両版`3b46d1066bc91cc2d613e3bc22ce691dd77e6f0d33c9060690d24ce6de494375`。

WSP準備確認では、モデル置き場直下に現行GGUFはあるが元BF16/FP16 checkpointは確認できなかった。RAM空き約106GiB、ディスク空き370GiB。元重みの所在・revision対応と35B MoE用の解析hookが未確立のため、今回の介入はpromptのみ。重み編集の効果は未検証。

## 保存済み会話応答の改善量

2026-11-12、`server.benchmark.progress`（`conversation-progress-v1`）で上記の基準・簡潔化候補をオフライン再集計した。追加のモデル生成は行っていない。元reportとsuiteのhash一致、既存compareの条件照合を通過し、判定は`review_required`。各12会話・28返答を同じ課題・ターンで対応づけた。

| 指標（会話系列を等重みにした平均） | 基準 | 候補 | 候補−基準 |
|---|---:|---:|---:|
| 段階1・返答文字数 | 109.75 | 99.00 | −10.75 |
| 段階2・返答文字数 | 71.42 | 55.64 | −15.78 |
| 段階3・返答文字数 | 68.97 | 50.77 | −18.20 |
| 段階2・目安超過文字数 | 0.50 | 0.00 | −0.50 |
| 段階3・目安超過文字数 | 0.53 | 0.00 | −0.53 |

個別には`chat-s2-followup-dev`の第4返答で超過6文字→0、`chat-s3-already-heard-dev`の第3返答で8文字→0。合否が同じでも超過量の減少を測れる。文字数そのものの減少は品質改善とは判定しない。完全一致の返答内反復は両版0で、この指標では改善余地を検出できていない。内容充足・関連性・意味の反復・自然さ・指示追従の品質点は各28返答とも未入力のため、対応採点数0・欠測28。上記の内容欠落に関する探索的レビューを打ち消す結果ではない。

出力はGit対象外の`server/benchmark/data/progress-baseline-02/`、`progress-concise-02/`、`progress-comparison-02/`。前二者は元report・指標・採点用テンプレート、比較先の`progress.json`は全ペアの観測値・差分・改善方向・集計・欠測数を保持する。オフライン評価器32テスト成功。

## 既存64課題での判断

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
