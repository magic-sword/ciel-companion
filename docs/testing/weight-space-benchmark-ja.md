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

### 会話状態の判定と返答選択の切り分け

`topic_state.py`と`weight_space/topic-state-suite.json`は、回答済み・話題の終了/変更を判定する課題と、同じ履歴から自然に返答する課題を別の要求で測る。配信由来の未編集GPU応答から固定した4文脈と、ゲーム不要の話題変更・就寝挨拶、必要な質問・再説明・明示再開の5対照を使う。生成した判定を会話へ戻さず、全条件・反復で履歴を固定する。元ログは実配信の逐語履歴ではなく、既存の合成再現課題の測定結果。生成元・suiteのhashはfixture内へ保存する。

条件は通常返答、状態判定、正しい会話状態を補足した返答、古いメモ付き返答、古いメモ付き判定の5つ。古いメモは過去の情報と明記した合成条件で、本番の内部思考や付箋を完全再現したものではない。正しい状態の補足は人が作った診断用の介入であり、そのまま本番に実装した改善ではない。

判定は、以前の質問が回答済みか、旧作業状態、最新発言の意図、以前の質問が今必要か、旧作業の再開を依頼されているか、の5項目。項目別の正否・欠落と`5×正しい項目数/5`を保存する。型も厳密に比較し、JSONの形式違反と意味の正誤を分ける。コードフェンスだけは診断用に取り除けるが形式失敗を残す。解析不能・途中終了・エラーは意味点を欠測にし、0点や満点へ置き換えない。

返答は根拠付きレビューで、不要な同じ質問・旧計画再開・最新依頼の充足を判定する。必要な範囲確認、依頼された再説明や再開は失敗にしない。判定の正答と返答の失敗が同じ文脈で共存する件数、古いメモ有無での対応差、正しい状態を補足したときの変化を分ける。判定課題は別の指示を含むため、正答から通常返答時の内部理解を証明したり、重み・システムの原因を断定したりしない。

共有GPU、既存5prompt、未編集重みで9文脈×5条件×2反復の90要求を上限とする。温度0、seed1729＋反復、thinking無効、384token、要求90秒、実行全体1800秒。要求順は反復ごとに固定seedで並べ替える。温度0の反復は独立な発症率標本ではない。開始・終了のGPU/ready・generationと重みhashを保存する。

```powershell
.\.venv\Scripts\python.exe -B -m server.benchmark.topic_state validate
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py stage
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py run --topic-state --rounds 2 --label topic-state-base-01
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py pull --label topic-state-base-01 --output server/benchmark/data/topic-state-base-01
```

`--topic-state`は固定した全9文脈を実行し、通常suite用の`--limit`による絞り込みは行わない。通常のベンチマークreportとは別schemaで、判定点はreport内の`judgment`へ保存する。fixtureを再生成する`build_topic_state_suite.py`は、元の`data/stream-replay-base-01/report.json`を必要とする。配布・再実行には生成済みの追跡対象JSONを使える。

通常人格の状態判定が解析不能だった場合の追加試験は、`run --topic-state --assessment-only --rounds 2 --label topic-state-assess-01`。同じ9文脈を、人格指示を外した評価者へJSONの会話記録として渡し、古いメモ有無の2条件×2反復＝36要求で測る。正解・oracleは入力しない。これは初回結果を見て追加した探索的な読解課題で、通常の会話生成と同条件とは扱わない。reportの`prompt_sha256`は共通5promptの参照hashであり、この追加試験の実指示は保存した`topic_state.py`の`branch`が生成する。初回と追加のソースをrunごとに保存する。

実測の返答レビューはreportと各応答のhashに結び付ける。同じ質問の再提示と、再開を求めていない旧作業の準備質問を別ラベルにする。今回の非反復軸は、最新依頼へ応じつつそれらを再提示する返答を2/4、該当しない返答を4/4として5点へ換算した限定指標である。総合品質・実行達成の満点ではなく、細かな重症度の連続尺度の校正は今後の課題。測定値と限界は[会話状態の判定と返答選択の検証](weight-space-results-ja.md#会話状態の判定と返答選択の検証)を参照する。

### 入力要因の切り分け

`topic_ablation.py`は同じ9文脈を8条件×2反復＝最大144要求で比較する探索試験。`weight-space-home.py run --topic-state --ablation --rounds 2 --label topic-ablation-base-01`で実行する。通常設定は上書きせず、既存5promptを読み取り、要求ごとに入力を変更する。初回に全条件を固定し、温度0・384token・要求90秒・全体1800秒、要求順の並べ替え・重みhash・共有GPU確認は状態試験と同じ。判定課題ではなく通常返答を比較する。

| 条件 | 変更する要素 | 残る交絡・対照の意味 |
|---|---|---|
| base | 変更なし | 過去runを流用せず同じ実行内で基準を測る |
| remove_traits | 先回り・過去の話の続きを聞く・待てが苦手、の3行を除去 | 行の意味と長さが変わる |
| remove_neutral | 無関係な好み・外見の行を除去 | 上の削除量に最も近い文字数を出力を見る前に選択。token数・位置まで同一ではない |
| compact_self | 自己設定を圧縮。疑わしい傾向も残す | 要約で表現・情報の強調も変わり、純粋な長さの実験ではない |
| remove_questions | 過去assistantの疑問符で終わる文だけを除去 | 利用者発言・回答済み情報・失敗・作業状態を保持。長さと履歴の型が変わる |
| neutral_failure | 引数確認の失敗を「採集未実行」に置換 | 失敗の表現を弱めても未達成情報は残す。利用者の「難しいなら」までは消さない |
| state_hint | 事実として正しい会話状態を補足 | 人が用意した状態の介入であり自動状態管理の実証ではない |
| question_gate | 必要情報不足か質問依頼時だけ尋ねる、という返答選択の指示を追加 | 状態の正解は与えない。モデル単独の改善や重み修正とは別 |

各要求の実system・補足・履歴をreportへ保存し、ソースとfixtureのhashを保持する。採点では履歴から質問を消した条件を機械的に「反復なし」としない。元の文脈で不要だった用途・準備・次作業の質問を再生成したかを全条件で同じ基準で読む。必要な質問・再説明・明示再開の3対照は別集計する。不要な質問数と該当箇所の文字数、旧作業への不要な復帰、最新依頼の内容保持を分け、短さだけを改善としない。原因調査用の開発文脈であり、独立holdout・実作業・内部活性の因果局所化を代替しない。

`topic_ablation_review.py prepare <report> <新しいreviewディレクトリ>`で条件名を隠した応答カードを作り、同じ文脈・本文・statusはまとめる。`cards.json`の質問箇所・不要な実行再開・内容点・根拠を記入後、`score`で全件の対応とreport/応答本文を照合する。内容点は0=最新依頼に応じない/矛盾、1=大部分欠落、2=一部充足、3=軽微な欠落、4=必要内容を保持。実ツール実行や人格全般の品質はこの点へ含めない。質問の不要性は別軸で、原文の該当箇所を保存する。条件名を隠しても文体から推測できることがあり、独立評価者による盲検試験とは呼ばない。

### 共通の測定項目

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

## 段階1〜5の会話評価の全体設計

段階は難しさと観測する範囲を増やす区分であり、完走率だけの合否階段にはしない。段階1〜3の小規模テキストsuiteと観点別のオフライン採点を実装済み。段階4は失敗・固着からの回復と12往復の雑談の限定プローブを追加した。全系列・24往復・文脈容量別負荷と段階5の対話suiteは未実装。段階5の一部指標には既存の音声評価器を再利用できるが、多ターンの音声品質まで実装済みとは扱わない。

| 段階 | 課題と負荷 | 観測する弱さ | 現在地 |
|---|---|---|---|
| 1 一往復 | 挨拶・事実・共感・詳説。短い回答と必要な長い説明を対にする | 不要な質問・演技描写、説明不足、人格の過剰適用 | 4系列×2分割を実装、dev各1回測定 |
| 2 短い継続 | 3〜5往復、相づち・追加質問・数量/曜日訂正 | 質問の連発、自己/相手の混同、訂正の忘却、毎回の再説明 | 3系列×2分割を実装、dev各1回測定 |
| 3 会話の修正 | 短文化・説明停止・話題変更・終了・再説明依頼 | 直後だけ従って元へ戻る、聞き直しまで抑制、終わった話の再開 | 5系列×2分割を実装、dev各1回測定 |
| 4 長い文脈 | 各12/24往復、履歴token量を別軸で段階化 | 意味の反復蓄積、遠い訂正・希望の忘却、話題復帰時の取り違え | 失敗回復4課題・12往復雑談2課題の限定プローブ。全負荷点は未実装 |
| 5 音声での対話 | 実時間の連続会話、相づち・間・割り込み・言い直し | 話し続ける、相づちを新依頼と誤解、古い返答の再生、STT誤りからの暴走 | 既存STT/live評価は部分再利用可。対話suiteは未実装・未測定 |

### 段階4の課題系列

初期設計は次の6系列。各系列に短い版と長い版を用意し、往復数と入力token数を別々に記録する。長い入力を一度渡すだけでなく、モデルが生成した返答を履歴へ戻す。

1. **相づちの蓄積**：日常の話に短い相づちを挟む。毎回の質問・感想の言い換え・返答長の増加を追う。
2. **離れた訂正**：予定・人数・個数を訂正し、別話題を数ターン挟んで確認する。初期値と最新値の混同を測る。
3. **説明済みの話題への復帰**：説明後に別話題へ移り、戻った際に新しい一点だけ尋ねる。全説明の再演と必要な文脈補足を区別する。
4. **希望の維持と解除**：「短く」「助言せず聞いて」を保持させ、後で「今は詳しく教えて」と解除する。保持と更新の両方を測る。
5. **失敗からの回復**：「違う」「同じことを言っている」への修正と、その後の維持を測る。謝罪・要約の反復を別に記録する。
6. **状態の変化**：体の接続/切断、未完了/完了/取消の固定イベントを挟む。昔の状態での報告と、会話内容の保持を同時に測る。実操作はfixtureと実機を区別する。

入力token量は利用する文脈容量に対する25%/50%/75%等の設計点で負荷を揃え、出力予約分を確保する。閾値は測定前に確定し、途中の履歴切詰め・要約も保存する。会話の途中で突然回答が長くなる時点、最初の不要反復までのターン数、終盤と序盤の品質差を観測する。未発生は観測期間内での右打切りとして扱い、無限の反復耐性とはしない。

### 段階5の課題系列

初期設計は6系列：通常の会話、短い相づち、考えている途中の間、発話中の割り込み停止、否定/数量の言い直し、雑音/無音/小声からの回復。人の録音と合成音声を分け、同じ正解文を用いたテキスト入力との対応を取る。録音・発話末尾・イベント時刻の注釈が揃うまで準備完了としない。

既存の[音声仕様](voice-benchmark-ja.md)のCER・自然確定・本返答音声開始に加え、返答の実音声秒数、割り込みから出力音声停止まで、割り込み後の古い返答の再生秒数、不要な話者重なり時間、利用者が再度話せるまでの時間を設計する。意図的な相づちと不要な重なりを注釈で区別する。文字数から発話時間を推定して実測値と混ぜない。既存`live`はUnityの物理再生まで測らないため、受信トラックと実再生の観測点を区別する。

一つの録音を無関係に独立再生する試験だけでは継続会話にならない。固定の入力音声列とイベント順序を会話単位で再生し、モデル返答を保持する。返答開始に合わせた割り込み等は、固定した相対時刻の規則で送る。実際の送信/受信/再生時刻を保存する。タイムアウトや欠けた音声を0秒として採点しない。

### 課題の難しさと測定感度の確認

モデル名だけからQwen固有の弱さと断定しない。まず実際の長文・反復の発生場面を、個人情報を除いた最小課題へ戻す。別モデルとの同条件比較は、原因をモデルへ帰属するときの追加試験とする。

初期の言い換えholdoutは同系列なので、新しい評価では場面・話題系列・話者単位でdev/holdoutを分ける。固定ユーザー台本を全モデルに共通化する。回答に応じて分岐する課題では分岐規則と経路も記録し、別経路の長さや速度を直接比較しない。

採点器の感度は、適切な短答、必要な詳説、同文反復、意味だけ同じ反復、無関係な追質問、空返答、重要情報を欠く短答、正当な再説明の対照応答で確認する。長さだけで順位が決まらず、各劣化の追加量に応じて該当観点が下がることを確認してからモデルを比較する。上位/下位への点数集中率と人手のペア選好一致率を記録する。難易度を上げる目的は低得点を作ることではなく、観測した欠陥を再現して測れること。

## 達成度と改善量の採点

`server/benchmark/progress.py`は既存64課題と段階1〜3の会話reportをオフライン再採点する。合否は契約確認として維持し、同じ課題・反復・ターンの観測値と品質点の差を追加する。微分可能性は要件にしない。

| 既存の評価対象 | 追加する測定 | 意味・限界 |
|---|---|---|
| 会話の長さ | 実文字数、目安の超過文字数、目安遵守点 | 目安以内は5点、超過e・目安bなら5/(1+e/b)。短いほど品質が高いとはしない |
| 反復 | 一返答内の同一文の余分な回数、過去の同文再利用回数 | 再利用は必要な再説明を含むので増減だけ示す。意味の反復はレビュー |
| 質問 | 疑問符数の差 | 必要な質問も含むため改善方向を決めない |
| 厳密出力・計算・抽出文字列 | 正解文字列との編集距離 | 形式上の近さ。誤答19が正答20に近いから内容まで正しいとはしない |
| JSON | 型も含む末端項目の一致点、誤り項目数 | 正しい項目数/期待と実出力の項目パスの和集合×5。余計な項目も減点。不正JSONは項目採点不能 |
| ツール | 操作順・名前・引数の構造一致点、誤り項目数、不要呼出し数 | JSONと同じパス単位で比較。拒否されたcallも観測済みの出力として診断する。後続未発行や実機成功の証明にはしない |
| 会話品質 | 内容充足・関連性・不要反復の少なさ・自然さ・指示追従の各点 | 根拠付きレビューの0〜4点を0〜5点へ換算。未採点はnull |

会話品質の基準は0=満たさない/矛盾、1=大きな欠陥、2=一部満たす、3=自然に満たす、4=場面によく合い一貫して満たす。課題のrubric、会話履歴、採点対象の返答を見て各観点を判断する。評点を換算するだけで分解能が増えるわけではない。短文化だけで内容欠落や温かさの低下を相殺する総合点は作らない。

`score`は新規出力ディレクトリに`progress.json`と`review-template.json`を生成する。後者へ`evaluator`（評価者と評価手順の識別）、各項目の`ratings`と観点別`evidence`を入力し、同じreportへ`--reviews`で取り込む。reportのhashと対象応答hashが一致しない採点、範囲外の点数、根拠なし、重複/未知キーを拒否する。複数の独立評価者は評価者ごとに別出力で比較し、評価者間の集約は現行実装の対象外。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.progress score --report server/benchmark/data/chat-baseline-dev-final/report.json --suite server/benchmark/weight_space/conversation-suite.json --output server/benchmark/data/progress-baseline-01
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.progress score --report server/benchmark/data/chat-concise-dev-final/report.json --suite server/benchmark/weight_space/conversation-suite.json --output server/benchmark/data/progress-concise-01
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.progress compare --baseline server/benchmark/data/progress-baseline-01/progress.json --candidate server/benchmark/data/progress-concise-01/progress.json --change prompt --output server/benchmark/data/progress-comparison-01
```

出力が既存なら新しい名前を選ぶ。64課題のreportには測定時と同じ`suite.json`を使う。suiteのファイルhash一致を要求するため、変更済みなら測定時のスナップショットを使う。元reportを改変せず採点結果から参照できる形で保持する。

比較は既存compareのsuite・runner・prompt/重み・実行条件・完走の照合を利用する。形式上の合否が両方同じでも、各指標のbaseline/candidate/delta/improvementを出す。低いほど良い誤差は減少を正の改善量にする。意味づけできない生の文字数・疑問符・再利用数はdeltaだけを表示する。カテゴリ別の平均は会話系列を等重みにし、長い会話の多数のターンが集計を支配しない。

タイムアウト・途中終了の文章は長さ改善に数えず、同じ指標が両版で観測できた対応ペアだけを比較する。missingとpaired、改善/悪化した観測数を併記する。ツール拒否時の構造点は観測済みcallの部分診断で、拒否や未完走を合格に変更しない。内容・自然さが未採点なら、数値が揃った形式指標だけから品質改善を断定しない。

段階4は下記の限定プローブ、段階5の対話suiteは未実装。固定文を正解にできない雑談へ編集距離を流用しない。ログ確率の診断は必要に応じた追加観測で、達成度採点の必須条件ではない。

### 作業失敗・雑談での話題固着を検出する

既存の段階1〜3には、失敗した作業の目的・使い道を、回答や話題変更を無視して質問し続ける課題がない。完全一致再利用は記述統計で、必要な再説明との区別や言い換えた質問を判定しない。従来の高い完走率を、この弱さがない証拠にはしない。

`failure-loop-suite.json`は段階4の回復系列の限定版で、dev4課題・18返答。原木集め失敗後の話題変更、同じ台本の成功対照、固定履歴で3回質問した後の回復、必要な用途確認と再質問の対照を分ける。ユーザー報告をもとにした合成履歴で、実プレイログの再生ではない。失敗結果はユーザーの報告として渡し、ツール通知や本番の記憶・未完了状態の再提示は含めない。

`topic-loop-suite.json`はMinecraft不要のdev2課題・各12返答。家で読書という回答済みの予定から、雨・猫・事実質問・飲み物・疲労・片付けへ移る。同じ入力台本で通常履歴と固定ループ履歴を比較し、質問停止の維持と、利用者が求めた週末の話への復帰も確認する。どちらもholdoutは未整備の探索セット。実際に生成した返答を次の履歴へ戻す。固定履歴中の反復をモデルが新たに起こした反復には数えない。

配信記録からの再現課題では、明示的な終了・取消と、未達成作業を残したままの称賛・別イベントを分ける。古い作業への言及を一律に失敗とせず、最新発言への応答に不要な採集宣言・用途質問・過去の補足がどれだけ再登場するかを測る。質問一文に加え、複数の意味単位が同じ順序で再生される長い説明も対象にする。作業状態は発話から推定せず、観測できない場合は不明と記録する。音声のASR誤認、実行主体の取り違え、内部状態の再提示は別の原因候補として保持する。

`stream-replay-suite.json`にこの分析を落とし込んだ。dev4課題・15返答。原木10個の依頼、拠点作りという用途回答、引数確認失敗を共通履歴とし、未達成・取消済みの状態だけを変えた対照を設ける。さらに過去の長い誤答を固定履歴へ入れた回復条件と、計画の再説明を求める正当な反復の対照を置く。前3課題は同じ4発言（整地への変更、条件付き代替と用途回答済みの指摘、ゾンビ撃退への感謝、説明停止）を使う。配信音声を正規化した合成課題で、元のSTTや内部状態の完全な再生ではない。取消済み状態も対照としての仮定である。固定履歴中の誤答を新たな生成の失敗数に加えない。

このsuiteの`loop_probe.units`は採集計画、木の種類・本数、用途質問、木の成長の補足の4観点。正規表現で一致した文と文字割合は**候補の記述統計**にとどめ、改善方向を付けない。否定・引用・依頼された再説明でも一致するためである。レビュー用テンプレートには実際に与えた`context`（作業状態）も保存する。

レビューは各`unnecessary_units`を0=不要な再出現なし／1=ありとし、各`unit_evidence`へ根拠を書く。4観点が全て採点された場合だけ`review_unnecessary_unit_count`（0〜4）と`review_plan_focus=5×(1−不要単位数/4)`を出す。例えば1観点が残る返答は3.75点、4観点全てを不要に再生すれば0点。これは旧計画への固着だけの点で、内容充足や自然さの総合点ではない。観点未採点は欠測。必要な再説明は候補に一致しても不要単位0とする。

対象に固定した原木の話へ戻らなくても、整地の後の準備確認など、新しい質問を反復する可能性がある。`loop_reasked_question_candidates`と根拠付き`unwanted_question`・`non_repetition`で別に測る。話題に応じる一文があることと、余計な旧作業の再開がないことは別評価にする。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.weight_space validate --suite server/benchmark/weight_space/stream-replay-suite.json
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py stage
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py run --stream-replay --label stream-replay-base-01 --limit 4
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py pull --label stream-replay-base-01 --output server/benchmark/data/stream-replay-base-01
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.progress score --report server/benchmark/data/stream-replay-base-01/report.json --suite server/benchmark/weight_space/stream-replay-suite.json --output server/benchmark/data/stream-replay-base-01-scored
```

既存出力は上書きせず別label・出力先を使う。`review-template.json`へ評価者・評点・根拠を入れ、同じreportとsuiteへ`score --reviews <採点JSON> --output <新規出力先>`で取り込む。将来の候補は同一suite・条件で測り、`progress compare`で対応する観点の差を比較する。初回は各1回・課題120秒以内、最大480秒の生成予算。holdoutと反復測定は別途必要。

`loop_probe.py`と`progress.py`は次を記録する。

- 各ターンの旧質問候補、旧話題への言及、固定履歴の質問との一致。`loop_probe=allowed`の必要な確認・再説明は悪化に数えない。
- 対象話題の正規表現に依存しない、生成済み質問の完全一致再出現。`loop_reasked_question_candidates`はターン内の再質問数、`loop_reasked_turns`は再質問したターン数。質問が未回答の場合も候補に入るため、不要かどうかは根拠付きレビューで区別する。
- 会話全体の不要質問**候補**ターン数と最長連続数。未完走は全体値を欠測にする。正規表現の候補検出は否定・引用・言い換えに誤検出／見逃しがあり、意味判定の代替ではない。
- 根拠付きの`loop_labels`：`unwanted_question`（不要な旧質問）、`stale_task_continuation`（終了済みの旧話題・作業を勝手に継続）、`current_request_met`（最新依頼に応答）の各0/1。`loop_evidence`を各ラベルに付ける。単発の有無を対応するターンで集計し、回数・率・改善量を比較する。一般の0〜4品質評点も併用できる。

ラベルは`review-template.json`へ評価者と根拠を入れ、通常の`score --reviews`で取り込む。未入力はnull。家の話を終えたのに「家のイメージを聞かせて」と続けた場合、用途の再質問が0でも旧話題継続は1になる。自動候補0をそのまま反復なしと断定せず、全生成返答を確認する。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.weight_space validate --suite server/benchmark/weight_space/failure-loop-suite.json
.\.venv\Scripts\python.exe -B -X utf8 -m server.benchmark.weight_space validate --suite server/benchmark/weight_space/topic-loop-suite.json
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py stage
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py run --failure-loop --label failure-loop-base-01 --limit 4
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-home.py run --topic-loop --label topic-loop-base-01 --limit 2
```

既存の結果名なら新しいlabelを選ぶ。各課題120秒・1回を既定とし、共有GPU APIで実行する。通常モデル・promptを変更せず、`stage`は専用評価領域への配置だけを行う。`pull --label <名前> --output <新規保存先>`で取得し、対応するsuiteを指定して再採点する。未編集モデルで発症しない場合、検出器の模擬テスト成功と実症状の再現成功を分けて報告する。次は観測ログに基づく文脈・状態・履歴更新の差を調べ、再現しないままWSP候補の優劣を決めない。

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

## 減衰重み候補の隔離比較

`server/benchmark/gguf_decay_experiment.py`と`scripts/server/weight-space-decay-home.py`は、登録した未編集base・decay010・decay025・eos110を同じ自宅CPU環境で比較する。共有GPUの基準値とは直接比較しない。実行ごとにソース・suite・5promptを保存し、重みhashを再確認する。原本または候補1ファイルをread-onlyで専用コンテナへ渡し、CPU8threads・40GiB上限・context8192・parallel1・loopback18099で起動。終了時は専用`ciel-wsp-decay-test`だけを削除する。

探索予算・採用ゲートは`server/benchmark/weight_space/decay-plan.json`を結果を見る前に固定する。screenは配信由来4課題各1回・課題120秒、改善候補1個だけをrepeat（同課題各3回）とguard（既存32＋会話12のdev）で比較する。選定後のholdoutは既存32＋会話12の未使用側。guard/holdoutは課題180秒。各返答512token・温度0・thinking無効で、欠測・途中終了を改善と数えない。同じ温度0での反復は独立した発症率の標本ではない。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-decay-home.py stage
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-decay-home.py edit
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-decay-home.py run --model base --phase screen --label decay-screen-base
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-decay-home.py pull --label decay-screen-base --output server/benchmark/data/decay-screen-base
```

候補は`--model decay010`、`decay025`、`eos110`で新しいlabelを指定する。既存候補がある場合の追加作成は`edit --model eos110`のように対象を指定する。既存の重み・結果を上書きせず、実験中にstageしない。生成した各結果の`suite.json`と`report.json`は通常の`progress score/compare`で採点する。意味判定・不要反復・内容充足と、決定的な形式/ツールの退行を分ける。実音声・画像・実Minecraftはこの比較の範囲外であり、本番採用は自動で行わない。

この隔離実験helperのrun終了コード0は予定課題の測定終了を示す。品質・自動checkの合格ではない。各試行の`automatic_pass`と通常比較器の新規退行一覧を確認する。終了後は`status`で専用コンテナの残存と全runの完了を確認できる。

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
