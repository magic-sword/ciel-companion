# シエルの重み編集ベンチマーク

> 責務：人格・身体性・ツール・一般性能を比較する課題、採点、実行条件、音声・実機評価への接続。

研究と編集手順は[WSP実施方針](../operations/weight-space-programming-ja.md)。評価器は `server/benchmark/weight_space.py`、課題と条件テンプレートは `server/benchmark/weight_space/`。Python標準ライブラリだけで動く。実際の重み編集は行わない。現在の実測は[確認状況](verification-status-ja.md)を参照する。

## 評価根拠

| 一次資料 | 採用する観点と限界 |
|---|---|
| Wang et al., [RoleLLM / RoleBench](https://arxiv.org/abs/2310.00746), 2023/2024 | 人物固有の知識と話し方を分ける。本環境の日本語シエル課題は独自作成でありRoleBenchの公式スコアではない。 |
| Tu et al., [CharacterEval](https://arxiv.org/abs/2401.01275), 2024 | 複数ターンと複数観点で人格を評価する。中国語向けの評価モデルを日本語の判定器として無検証で流用しない。 |
| Meng et al., [ROME](https://rome.baulab.info/), 2022 | 対象の改善、言い換え汎化、対象外への干渉を別に測る。自分の外観知識と他者の知識を混同しない。 |
| Patil et al., [BFCL](https://gorilla.cs.berkeley.edu/leaderboard.html), ICML 2025 | ツール名だけでなく引数、複数段階、ツール不要の判断を測る。fixtureでの成功は実MCP接続・物理動作の成功ではない。 |
| Zhou et al., [IFEval](https://arxiv.org/abs/2311.07911), 2023 | 検証可能な指示を決定的に採点。JSON・厳密出力・数量・否定の独自課題を採る。IFEval公式スコアとは呼ばない。 |
| [音声評価の一次資料と固定仕様](voice-benchmark-ja.md) | 日本語CER、無音誤認識、自然確定、本返答音声を別測定。同じ録音・正規化・注釈・共有負荷を固定する。 |

## 測定項目

| 領域 | 指標・判定 | 測り方 |
|---|---|---|
| シエルの人格 | 丁寧語・一人称、温かさ、共感、好奇心、押しつけなさ、自然さ | 人手0〜4点。犬の語尾の頻度だけでは判定しない。 |
| 自分の姿 | 耳・尾・髪・目・プリズムの正しさ、他者との取り違え | 独自質問の人手採点。画像の自己同定は別途画像入力で測る。テキスト知識だけで視覚認識成功とは言わない。 |
| 身体性 | 接続中の体を使う判断、未接続時の限界、観測根拠、停止追従 | `app_gesture`・ゲーム受付・状態・停止fixtureと人手確認。最後は実機の状態で検証する。 |
| ツール維持 | 完全な名前・引数・順序、読込後の実呼出し、不要呼出し率 | SSEの構造化`tool_calls`を採点。本文に名前を書くだけでは失敗。想定外呼出しはfixtureを実行せず失敗とする。 |
| 一般性能 | JSON、厳密指示、計算、論理、抽出の正解率 | 決定的採点。コードフェンスや語尾の混入はJSONでは失敗。 |
| 音声の意味保持 | 訂正・否定・数量の保持、曖昧入力での確認 | 正解文字と認識文字を別入力し、勝手な補完・誤操作を採点。現在の2課題はテキスト試験。CER改善の証拠にはしない。 |
| LLM遅延 | 最初の出力イベント、最初の可視文字、推論全体 | 単一要求のmonotonic時計でms。推論reasoningと可視本文を分離。tool-onlyの可視文字はnull。 |
| 生成異常 | 例外・期限切れ・token上限、反復・未完結、出力token | 上限は失敗。usageとサーバーtimingsは提供された値を保存。反復・意味不明は人手レビュー。 |
| 音声体験 | CER、無音誤認識率、自然確定、本返答音声p50/p95、失敗率 | 既存の`benchmark-voice.py stt/live`。相づちを本返答に含めない。 |
| 実作業 | 目的達成、誤完了、停止確認、所要時間 | 既存Minecraft practical-v1。ゲーム側の実状態を採点し、受付文は達成証拠にしない。 |

### 人手評価

`human-review.json`には質問、生成応答、課題別rubric、未入力の`ratings/evidence`を出す。共通の0〜4点は、0=矛盾・捏造・不適切、1=大きな欠陥、2=一部満たす、3=自然に満たす、4=状況に合った人物像が一貫して表れる。口調、共感、設定整合、身体の根拠、自然さを個別に記録し、課題に不要な観点はNAとする。好意的な感想だけで満点にしない。

比較時はモデル名を隠してA/Bをランダム順に並べ、最低2名が独立採点。根拠となる発言箇所と不一致を残す。評価者が1名なら探索用と明示する。固定したLLM judgeを補助に使う場合も、モデル版・prompt・温度を保存し、人手との一致を確認する。現行コードはjudgeを呼ばず、人手採点の取込み・統計判定も自動化していない。

## 課題と分割

初期suiteは64課題、dev32・holdout32。人格、身体性、ツール、指示、推論、音声意味保持を含む軽量の疎通・回帰セットであり、これだけで一般性能の非劣化を証明しない。ホストの道具schemaは `capabilities.py`、`tools/goals.py`、Unityの `CielConversation.App.cs` に照合したfixture。

ゲーム作業の2課題は、`scripts/server/sync-weight-space-contracts.py`でゲーム実装 `server/minecraft/src/ciel/tasks.js` のexportされた能力定義と照合する（開発端末にNode.jsが必要）。`--write`で能力本文・正式引数・制約を更新する。`quantity`・`quantity_mode`、英語item ID、`resource_scope`・`failure_policy`を省略しない。更新後は両版を同じsuiteで測り直す。通常の評価実行は引き続きPython標準ライブラリのみ。

holdoutは公開された初期評価用の言い換えセットで、秘密のテストではない。同じ課題系列が両側にあるため近い言い換えへの汎化までが測定範囲。最終採用には、編集担当が選定に使わない新しい場面・会話系列と未使用の録音・Minecraft配置を追加し、質問系列単位で分割する。編集用の対照例にsuiteの質問を転用しない。

多ターン一貫性を測るときは、同じケースの`messages`にuser/assistant履歴を明示し、最後を新しいuserのprobeにする。名前保持、停止維持、自己と他者の外観、数量訂正、共感の希望保持、能力切断の6系列×2分割を収録した。固定履歴に対する最終応答を測るもので、前のターンも実モデルが生成する対話試験ではない。最終採用時は独立した場面を追加する。画像自己同定も、許諾済みの自画像・他者・不明画像の組を別suiteで用意する。

## ローカルで検証・実行

### 段階1〜3の会話課題

`server/benchmark/weight_space/conversation-suite.json`は独立した24課題（dev12・holdout12）。既存64課題の回帰セットと併用する。段階1は挨拶・短い事実質問・共感・詳しい説明の4系列、段階2は相づち・追加質問・訂正の3系列、段階3は短文化・既出説明の停止・話題変更・会話終了・求められた再説明の5系列。各系列のdev/holdoutは近い言い換えであり、独立した未知場面への汎化保証にはしない。

`dialogue`に固定したユーザー発言を順に送り、各ターンの実モデルの返答を次の履歴へ戻す。前の返答に依存する追加質問も含む。ユーザー発言を生成する対話相手モデルは使わない。`stage`は1〜3、`max_chars`はターン別の長さの注意閾値、`rubric`は人手判定基準。閾値は暫定値で、超過だけでは自動不合格にしない。詳しい説明と聞き直しを対照課題に含め、一律の短文化・反復抑制で内容を失っていないか確認する。

各ターンに文字数・文数・同じ文の重複数・過去の返答と同じ文の出現数・文字数超過を保存する。文は句点・疑問符・感嘆符・改行で区切り、空白を除いて8文字以上の完全一致だけを反復信号に数える。短い相づちは対象外。言い換えによる反復や説明の必要性は検出できず、再説明を求められたターンの一致も失敗扱いにはしない。カテゴリ集計と比較結果に観測ターン数・文字数p50/p95・超過ターン数・反復数を出す。失敗ターンも保存し、途中で打ち切られた会話を全ターン完走と扱わない。

`human-review.json`の`turns`で内容充足、長さの適切さ、不要な反復、自然さを各0〜4点で採点し、段階3では修正への追従と後続ターンでの維持も採点する。0=満たさない、1=大きな欠陥、2=一部満たす、3=自然に満たす、4=状況に特によく合う。根拠発言を`evidence`へ記録する。段階別に全ターン完走と各必要観点3点以上を確認するのを初期受入条件とし、下位段階の退行も確認する。自動成功は生成完走・空返答なし・ツール呼出しなしを示すだけで、人手未採点は会話品質合格ではない。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.weight_space validate --suite server/benchmark/weight_space/conversation-suite.json
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.weight_space run --suite server/benchmark/weight_space/conversation-suite.json --conditions .local/wsp/conditions.json --output .local/wsp/conversation-dev --rounds 1 --timeout 180
```

`--timeout`は会話全体の期限、`--max-tokens`は各返答の上限。初回疎通は`--limit 1`、段階指定は`--case chat-s3-shorten-dev`等で課題IDを選ぶ。全devは12会話・28返答。候補と基準で同一条件を固定し、前述の`compare`を使う。本試験は固定5promptによるLLM単体評価で、音声・割り込み・本番の動的記憶は別評価。実モデルでの基準値と閾値の妥当性は未確認。

作業起点はリポジトリのルート。既存`.venv`を使う。Linuxでは`python3`へ読み替える。`.env`やクラウド資格情報は自動読込しない。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s server/benchmark/tests -v
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.weight_space validate
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.weight_space preflight
```

APIは自宅のloopback 8094、制御は8095。手元PCに推論器がなければ、認証済みSSHで両方転送する。既存共有先の設定は変更しない。

```powershell
ssh -N -L 18094:127.0.0.1:8094 -L 18095:127.0.0.1:8095 <自宅サーバーのSSH接続先>
.\.venv\Scripts\python.exe -B -m server.benchmark.weight_space preflight --base-url http://127.0.0.1:18094/v1 --control-url http://127.0.0.1:18095
```

`conditions.example.json`をGit対象外の`.local/wsp/conditions.json`へコピーし、モデルの正式識別・重みhash・hardware・runtime・shared_loadを実値へ置き換える。未編集と候補でモデル識別だけを変え、その他の条件は揃える。

```powershell
.\.venv\Scripts\python.exe -B -m server.benchmark.weight_space run --conditions .local/wsp/conditions.json --output .local/wsp/baseline-dev --rounds 3
.\.venv\Scripts\python.exe -B -m server.benchmark.weight_space run --conditions .local/wsp/candidate-conditions.json --output .local/wsp/candidate-dev --rounds 3
.\.venv\Scripts\python.exe -B -m server.benchmark.weight_space compare --baseline .local/wsp/baseline-dev/report.json --candidate .local/wsp/candidate-dev/report.json
```

転送利用時はrunにも`--base-url`と`--control-url`を指定。候補APIは評価者が別に準備する。runnerは起動・切替・重み書換えをしない。最初は`--limit 1 --rounds 1`。特定課題は`--case json-dev --case gesture-dev --limit 2`のように選べる。既定はdev・3反復・温度0・seed1729・512token・1課題60秒（ツール継続を含む）。順番をseedでシャッフル。reasoningが512tokenで上限へ達する場合は開発段階で上限を決め直し、両モデルを同じ値で再測定する。変更版だけ延長しない。

`--prompt-mode deployed`は既存の人格・自己認識・app・discovery・gameの5promptを使う固定probeで、本番の動的履歴・本人情報・全prompt構築の完全再現ではない。`minimal`は重みへの定着を調べる補助条件。異なるprompt条件は直接比較しない。

`chat_template_kwargs.enable_thinking=false`を既定で明示し、現行の `server/agent/models.py` に揃える。`--thinking`は推論モードの別試験にする。設定を省略するとサーバー既定でreasoningが有効になり、本文が出る前に512tokenへ達することがある。モデル編集の効果と混同しない。

### 自宅サーバーで直接測る

不採用の改善候補は`server/benchmark/weight_space/prompt_candidates/grounded-body-v1/`に固定5promptのスナップショットとして保存する。通常の会話設定からは参照しない。再試験にはrunnerの`--prompt-dir`、またはhome helperの`stage --prompt-dir server/benchmark/weight_space/prompt_candidates/grounded-body-v1`を明示する。`--prompt-revision`とは併用不可。基準と同じsuite・runnerで測定し、`compare --change prompt`で比較する。候補は既定へ自動採用されず、人手・実音声・実MCPの合格も意味しない。

既存の `scripts/server/.env.local` のSSH設定だけを利用し、`~/work/ciel-weight-space-benchmark`へ評価器とfixtureだけを配置するhelperを用意している。モデルの新規起動・GPU切替・本番サービス更新は行わない。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py inspect
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py stage
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py run --label baseline-smoke --rounds 1 --limit 3
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py pull --label baseline-smoke --output server/benchmark/data/wsp-baseline-smoke
```

helperの既定runは1課題1回。全devなら`--limit 32 --rounds 3`、最終holdoutなら`--split holdout`も指定する。出力は新しいlabelを指定し既存結果を上書きしない。runは実GGUFをストリームでhashし、モデル名・CPU/GPU情報・`/props`を条件へ保存する。約22GBのhashには時間が必要。共有先の他の利用者は制御しないので、負荷が一定だった保証はない。helperは現在の共有モデル専用で、別候補APIの評価には通常のrunnerを使う。

### 出力と終了コード

`report.json`はsuite/runner/promptのSHA-256、ソースcommit/dirty、条件、開始終了mode、全応答・reasoning・構造化call・要求別計時・usage、決定的check、人手未採点、カテゴリ集計を保存。各試行後に保存する。`completion=complete`は予定試行の終了で、性能合格ではない。Git情報がない専用配置ではcommit=nullとなり、runner/prompt/suiteのhashと元ソースの未コミット差分を引き継ぐ。

runの終了コード0は自動check通過、1は自動失敗、引数エラーは2。compareは不一致・欠測・自動劣化で非0。自動劣化が見つからなくても`review_required`であり、最終合格は出さない。人手評価・音声・実機を終えるまで採用しない。latency集計は観測された成功処理のみの件数・p50/p95であり、同時にerrorsと全試行数を読む。token上限・タイムアウトを除外して高速化率を算出しない。

## 比較条件と採用基準

比較は同一suite/runner/prompt/sampling/seed/反復/課題/timeout/hardware/runtime/shared_loadを要求。開始・終了modeが不一致なら比較不能とする。途中の歌唱CPU切替・共有競合までは自動監視しないため、発生時は混合条件とし、時系列ログを追加して両版を取り直す。キャッシュ・warm/cold・起動準備は区別し、A→BだけでなくA/B順序を入れ替えて測る。

上記は既定の`compare --change weights`。システムのプロンプト改修は`compare --change prompt`を明示し、prompt hashの違いを許容する代わりにモデル識別と重みhashの一致を要求する。他の条件は緩めない。`run --prompt-dir <ディレクトリ>`で固定した本文一式を選べる。home helperの`stage --prompt-revision <GitコミットID>`は5promptだけを指定commitから取り出し、評価器は現在のソースを置く。これにより両版を同じ採点器で測り直せる。実行中にstageで本文を入れ替えず、各runの終了後に切り替える。

`prompt_chars`はsystem本文の文字数で、token数ではない。APIが返す`measurements[].usage`の入力・出力tokenと、カテゴリ別の要求単位first_content_msも保存する。形式修正で出力が短くなった効果と、操作が実際に発行されて継続推論が増えた時間を分けて読む。未実行の短い完了文を高速な操作として評価しない。

採用の基準は研究論文の閾値ではなく、このプロジェクトでの事前登録案。開発基準を見て次の値を確定し、holdout結果を見て緩めない。

- 人格：主要な対象観点で平均+0.5/4以上、95%区間の下限が0超。人物像以外の自然さが下がらない。
- ツール・指示・一般性能：基準版が通ったケースの新規失敗は初期ゲートで0。最終試験では正解率差の片側95%区間下限が−2ポイント以上となる非劣性を確認。重要な停止・否定・誤完了・権限・JSONは新規失敗0。
- 音声：人の録音でCER・無音誤認識・否定/数量/名前の意味保持が悪化しない。LLM単独変更でSTTのCER改善を主張しない。
- 速度：同じ品質条件で本返答音声p95を20%以上短縮するのを初期目標とし、p50と失敗率も悪化しない。LLMのTTFTを音声応答時間へ読み替えない。

64課題・各3反復は疎通と大きな退行の発見用。温度0の同じ質問の反復は独立な知識サンプルを増やさず、−2ポイントの非劣性を保証できない。最終比較では数百の独立した質問系列・複数話者/録音・実機配置を準備し、系列単位のpaired bootstrap（固定seed・10,000回）等で区間を計算。必要試料数は基準正解率と許容幅から事前設計する。区間の幅が広ければ「差が検出されない」で止め、非劣化と断定しない。

## 音声と実機をつなぐ

同じIDの正解音声・正解文で、(1) Voskのみ、(2)正解テキスト→LLM、(3)Vosk認識テキスト→LLM、(4)live音声を測る。人/合成・話者・雑音・距離・小声・途中の間・無音を分ける。既存コーパスには否定・名前・数量が含まれる。録音と注釈がない台本だけでは音声評価準備完了とは扱わない。

音声の実行は[音声仕様](voice-benchmark-ja.md)と[音声スキル](../../.claude/skills/ciel-voice-benchmark/SKILL.md)、実Minecraftは[practical-v1](../games/minecraft/minecraft-benchmark-ja.md)を使う。appの実動作・画像による自己同定・追加の人の録音は初期suiteの測定範囲外。全ターンの応答生成は前述の会話suiteで別に測る。未実施を自動合格に含めない。
