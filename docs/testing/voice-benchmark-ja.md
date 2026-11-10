# 音声会話のベンチマーク

> 責務：音声認識精度と応答時間の評価根拠、録音コーパス、再生・集計・比較の方法。

入口は `scripts/server/benchmark-voice.py`。同じ正解付きWAVをCPU Vosk単体（`stt`）と名前付き試験ワーカー（`live`）へ再生し、`report.json`へ試行と集計を保存する。通常会話の設定や認識モデルは変更しない。実測済みの範囲は[確認状況](verification-status-ja.md)、音声入力の契約は[CPU音声認識](../services/local-stt-ja.md)。

エージェントの作業手順は[共有評価スキル](../../.claude/skills/ciel-voice-benchmark/SKILL.md)。Codexは[参照用入口](../../.agents/skills/ciel-voice-benchmark/SKILL.md)から同じ正本を読む。コマンド・採点仕様はこの文書で管理する。

## 評価の根拠

| 一次資料 | この評価で採用すること・限界 |
|---|---|
| Radford et al., [Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356), 2022 | 認識器を正解付き音声で評価し、条件と正規化を固定する。モデル名だけから実際の利用者の精度を推定しない。本実装の正規化は独自の固定仕様で、Whisperの公開値と直接比較しない。 |
| Karita et al., [Lenient Evaluation of Japanese Speech Recognition](https://arxiv.org/abs/2306.04530), CAWL 2023 | 日本語の妥当な別表記もCERでは誤りになる。生の認識文を残し、表記差と意味の誤りを別に目視確認する。本実装は論文のラティスによる寛容評価を実装していない。 |
| Stivers et al., [Universals and cultural variation in turn-taking in conversation](https://pmc.ncbi.nlm.nih.gov/articles/PMC2705608/), PNAS 2009 | 人同士の会話は間と重なりを小さくする傾向がある。実際の発話末尾から返答を測る。人の応答間隔をそのままローカルAIの合格基準にしない。 |
| Arora et al., [Talking Turns](https://arxiv.org/abs/2503.01174), ICLR 2025 | 応答速度に加え、不必要な割り込み・相づち・交替を評価する。本実装は相づちトラックを分け、入力終了前の本返答音声を警告値として記録する。論文の学習済み判定器や総合スコアは再現していない。 |

採用する指標は以下。速さと精度を一つの点数に混ぜない。

| 指標 | 定義 |
|---|---|
| CER | 正解・認識文のLevenshtein距離 / 正解文字数。コーパス集計は誤り数の合計 / 正解文字数の合計。挿入が多ければ1を超える。 |
| 完全一致率 | 固定した正規化後の一致割合。発話なしの試料も含む。 |
| 無音誤認識率 | 正解が空文字の試料で、空でない認識が出た割合。無音のCERはnull、発話CERの分母へ入れない。 |
| compute RTF | feedとEOF確定の計算時間 / 入力長（追加無音込み）。モデルロード・実時間の待機を除外。1未満でも会話全体が速いとは限らない。 |
| 最初の途中結果 | 再生開始から最初の空でない途中結果まで。 |
| natural_final_ms | 注釈した発話末尾から、末尾をカバーする最後の自然確定まで。EOFに文字が残ればnull。非実時間入力でもnull。 |
| first_any_audio_ms | 注釈した発話末尾以後に観測した最初の音声開始まで。相づちを含む。 |
| first_reply_audio_ms | 同上、`ciel-aizuchi`トラックを除く。内容の適切さ・実際に質問への回答かは目視確認する。 |
| 失敗数 | 例外と本返答のタイムアウト。遅延のpercentileは観測された試行のみなので、必ず失敗数と一緒に読む。 |

遅延とRTFには件数・p50・p95・最大を出し、話者・雑音条件・人/合成別にも集計する。percentileはnearest rank。少数試料のp95は粗いので、初期は最大値も確認する。

正規化IDは `ja-nfkc-casefold-no-space-punctuation-v1`。NFKC、casefold、空白・Unicode句読点の除去のみ。漢字/かな、三/3、固有名詞、否定を同一視しない。通常の日本語に空白分割WERは使わない。表記揺れを直す場合は結果を見て片側だけ書き換えず、正解コーパスを版管理して両モデルを測り直す。

## 録音を用意する

実行器`scripts/server/benchmark-voice.py`、採点器`server/agent/voice_benchmark.py`、テスト`server/agent/tests/test_voice_benchmark.py`、`server/benchmark/voice/`の台本・条件テンプレート、この手順書はGitで管理する。外部からダウンロードする評価コードではなく、このリポジトリの実装である。再利用する補助コードも`scripts/server/`等へ置き、Git対象外の結果フォルダへ置かない。

録音・実際の条件ファイル・実行結果・モデル重み・認証情報はGitへ含めない。同一の性能値まで比較する参加者には、保存同意・ライセンスに従って同一録音とモデルの取得元・指紋を別途共有する。テンプレートだけで実測値は再現できない。

`server/benchmark/voice/corpus.example.jsonl`は7条件の台本と形式の見本。音声は付属しない。`speech_end_seconds`の値も例なので、録音に合わせて必ず置き換える。

1. 録音と正解文をGit対象外の専用ディレクトリ（例 `.local/voice-corpus/v1/`）へ用意する。本人が評価保存に同意した録音だけを使い、氏名・私的な会話や音声をGitへ入れない。
2. 16kHz・モノラル・非圧縮PCM16 WAVへ変換する。例：`ffmpeg -i input.wav -ar 16000 -ac 1 -c:a pcm_s16le output.wav`。1ファイル1ターンとし、複数ターンを結合しない。
3. 人が実際に言った文字列を`reference`へ転記する。言い淀みも保存する。台本を読み間違えた場合は台本を正解にしない。`speech_end_seconds`はWAV先頭から最後の発話音までの秒数で、末尾無音を含めない。無音試料はWAV末尾を指定する。
4. 短い挨拶、名前、数字、否定、長文、0.3/0.6/1秒の途中の間、距離・小声・生活雑音、無音・物音を用意する。初期基準は人の発話30件以上、無音/物音10件以上、可能なら複数話者で始める。これはプロジェクトの運用目安で、論文の規定ではない。
5. `source`は`human`/`synthetic`、`speaker`は匿名ID、`condition`は条件名。合成音声は疎通・回帰用とし、人の精度とは別集計にする。調整用と未使用の評価用録音を分け、同じ録音だけへ過適合させない。

JSONLの`audio`はmanifestのあるディレクトリから解決する。各音声のSHA-256、正解、条件、長さを結果へ保存する。録音を差し替えれば別の試験になる。

## 実行

`conditions.example.json`を複製し、実際のSTT/LLM/TTSの版・モデル指紋、CPU/GPU・割当、共有負荷、設定と配布コミットへ置き換える。単体STTではLLM/TTSを`not used`にできる。資格情報は書かない。モデルディレクトリは名前だけでなく取得元・重みのチェックサムを条件へ記録する。

リポジトリルートで実行する。既存の出力ディレクトリは上書きしない。

```powershell
# CPU単体：既存のVoskをインストールしたPythonと配置済みモデルを使う
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/benchmark-voice.py stt `
  --corpus .local/voice-corpus/v1/corpus.jsonl `
  --conditions .local/voice-corpus/v1/conditions.json `
  --model C:/models/vosk-model-small-ja-0.22 `
  --output .local/voice-results/baseline-stt --rounds 3

# 最大速度の処理能力だけを調べる場合。確定遅延とは別実行にする
# 同じ引数に --unpaced を追加し、新しい --output を指定する
```

`stt`は本番と同じ`vosk_engine.Decoder`を使う。既定20ms刻みの実時間入力、2秒の追加無音、最後にEOF確定。モデル全ファイルのSHA-256と、プロセス内初回ロード時間を別に記録する（OSキャッシュまで冷えた起動時間ではない）。非実時間では途中結果・自然確定の遅延をnullにする。既存の[合成3文試験](../services/local-stt-ja.md)は入力・刻み・正解が異なるため直接比較しない。

`live`はLiveKitを使う。ローカルSTT/共有LLM/Irodoriに設定した**名前付きの試験用worker**を明示し、そのworkerの実際の設定をconditionsに記録する。ワーカーは起動済みで、試験専用DB/記憶スコープにする。毎回新規の部屋に参加するが、永続記憶は自動初期化しない。道具を呼ぶ指示やゲーム操作は別の専用評価へ分ける。

```powershell
# LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRETをプロセス環境へ設定済み
# .envは自動で読み込まない。既存サービスのbackendも変更しない
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/benchmark-voice.py live `
  --corpus .local/voice-corpus/v1/corpus.jsonl `
  --conditions .local/voice-corpus/v1/conditions-live.json `
  --agent ciel-voice-bench --output .local/voice-results/baseline-live --rounds 3
```

既定は音声トラックを30秒待ち、挨拶待ち10秒後に再生、追加無音を含む入力完了後30秒間を観測する。挨拶が長い構成は`--settle-seconds`を増やす。毎試行後、接続と部屋を閉じる。終了コードは全試行が観測完了なら0、エラー・本返答タイムアウトがあれば1。認識品質の合否閾値はまだ設定していない。

LiveKitの利用環境やworkerのbackend次第では課金されるため、[外部API試験](paid-checks-ja.md)の対象を確認する。スクリプトはクラウドへ自動切替せず、TTS合成の追加要求も出さない。OpenAIのワーカーを指定した場合の料金は別に発生する。

## 結果の読み方と次の改善

`report.json`はGitコミット・dirty状態、実行器/採点器/デコーダーのSHA-256、コーパス指紋、条件、反復ごとの結果を持つ。例外が起きても試行ごとに保存し、失敗を集計する。同一コーパス・端末・モデル・負荷・設定で前後各3回以上測り、一度にSTTモデル、発話区切り、LLM、TTSのいずれか一つを変更する。反復再生は独立した話者数を増やすものではない。

CERが悪くRTFが低ければ、まず雑音条件・固有名詞・否定・数字の誤りを確認し、大きいVoskモデル等を同一録音で比較する。自然確定が遅い/EOFが多ければ音声区切りを調べる。単体STTが速く会話が遅い場合は、試験workerの既存デバッグログの`latency`（文字起こし、返事を頼んだ、最初の文字、文、声）も確認する。このログの起点はホストの発話終了判定であり、録音の発話末尾とは違う。別試行の値を引き算しない。共有GPUの待機・CPU切替、話者確認・記憶取得も条件に含める。

音声受信は20msフレームのRMSが閾値（既定0.01）を超えた開始を検出する。トラック内の短い無音でも別の開始になるため、途中終了前の本返答や相づちとの重なりは生音声・ログで確認する。`pre_end_reply_audio`は割り込みの候補で、適切な相づちかどうかの自動採点ではない。

LiveKitが試験参加者の確定文字起こしを配信しない場合、`transcript_available=false`とし、CERは集計しない。無音試料でも配信がないことを「認識が空だった」とは扱わない。認識の比較には単体STTの結果を用いる。

受信遅延は再生開始の単調時計＋手動注釈を起点とする。ネットワーク・AudioSourceのキュー誤差を含み、実マイクの捕捉やUnityのスピーカー再生までは測らない。挨拶が計測中まで続く構成では待機時間を調整して再測定する。発話内容の妥当性・自然さ、音質、真の割り込みによる停止時間、多ターン文脈の理解は自動測定の対象外。代表録音で認識の意味保持と回答の適切さを人が評価し、最終的には実アプリのマイク会話で確認する。
