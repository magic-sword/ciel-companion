# 音声会話のベンチマーク

> 責務：音声認識精度と応答時間の評価根拠、録音コーパス、再生・集計・比較の方法。

入口は `scripts/server/benchmark-voice.py`。同じ正解付きWAVをCPU Vosk単体（`stt`）と名前付き試験ワーカー（`live`）へ再生し、`report.json`へ試行と集計を保存する。通常会話の設定や認識モデルは変更しない。実測済みの条件・結果は[音声の実測](voice-results-ja.md)、現在の配布範囲は[確認状況](verification-status-ja.md)、音声入力の契約は[CPU音声認識](../services/local-stt-ja.md)。

エージェントの作業手順は[共有評価スキル](../../.claude/skills/ciel-voice-benchmark/SKILL.md)。Codexは[参照用入口](../../.agents/skills/ciel-voice-benchmark/SKILL.md)から同じ正本を読む。コマンド・採点仕様はこの文書で管理する。

## 認識モデルと呼びかけの比較

`server/benchmark/voice/conversation-corpus.json`は「シエル」と一般語の「シール」「シェル」、数字・否定・訂正・途中の間を含む合成用台本。準備時に一度生成したWAVと注釈を固定し、全モデルで再利用する。人の発音や雑音の評価には別の正解付き録音が必要。

```powershell
python scripts/server/voice-home.py stage
python scripts/server/voice-home.py prepare --corpus-spec server/benchmark/voice/conversation-corpus.json
python scripts/server/voice-home.py stt --stt-model vosk-model-small-ja-0.22 --smoke
python scripts/server/voice-home.py stt --stt-model vosk-model-small-ja-0.22 --rounds 3
python scripts/server/voice-home.py stt --stt-model vosk-model-ja-0.22 --smoke
python scripts/server/voice-home.py stt --stt-model vosk-model-ja-0.22 --rounds 3
```

Whisper単体は配置済みモデルと同じコーパスを`benchmark-whisper.py --model <モデルdir> --corpus <corpus.jsonl> --prompt <stt_vocabulary.md> --output <新規JSON> --rounds 3`へ渡す。最初は`--smoke --rounds 1`。faster-whisperを含む会話イメージでCPU4・RAM4GiBに制限して実行する。認識処理時間は録音全体が揃った後の処理であり、逐次Voskの発話確定時間やLiveKit往復時間とは直接比較しない。単体ではWhisper内VAD、会話ではホストVADを使用する。CERの正規化は既存定義のままで、漢数字と算用数字の差も誤りとして残す。

`voice-fast-home.py start --variant fast --stt-backend whisper --image <評価用イメージ>`で新しい依存関係を含む分離ワーカーを指定できる。`live --variant fast --smoke --rounds 3 --tag <識別子>`は同じWAV、準備完了と初回挨拶終了、既定の観測期限で比較する。使用前に`reuse --corpus-run <保存済みrun>`で比較元を明示する。評価後は`stop --variant fast`と、起動した評価受信口の`proxy-stop`を実施する。

返答側の名前訂正は`benchmark-voice-text.py`と`server/benchmark/voice/text-cases.json`で別に検証する。`--prompt-dir`、`--voice-prompt`、`--cases`、`--output`、`--rounds`を指定し、同じ共有8094へ文字を送る。変更前後の本文指紋と返答を保存し、各rubricを確認する。これはASR精度でも音声遅延でもなく、自動の合格判定も行わない。

`benchmark-prefix-cache.py`は固定promptと変化する末尾で入力キャッシュを診断する。1枠を明示指定する診断なので通常会話の遅延値にはしない。キャッシュが使えない原因を推測だけでモデル設定へ反映しない。

`benchmark-role-cache.py --prompt-dir <prompts> --output <新規JSON> --rounds 3`は同じ共有8094で「会話のみ」「先頭の担当指示を変える」「共通部分の後ろに担当指示を足す」を比較する。各反復で順序を交代し、固有の評価IDで前の条件とのキャッシュ共有を避ける。会話→メモ→内省→会話という合成の座標抽出課題で、JSON Schemaによる出力制約と正解値を全条件で揃える。推論前後の世代、最初の文字、完了時間、キャッシュ量、誤答を保存する。これは実際の内省品質・記憶の保存・音声応答や、異なる道具定義を持つ担当間の互換性の評価ではない。既存会話のキャッシュは消さず、通常サービスの負荷は制御しない。

`benchmark-conversation-tools.py --catalog-position trailing`は能力一覧を変動する補足の後ろへ戻して、`fixed`（既定）の配置と同じ実pipeline・本文・道具で比較する。初期能力選択と、能力ロード後の続きの時間を分けて読む。速さだけで権限・同意・操作の正確さを合格にしない。

## ゲーム語彙の比較

`server/stt/game_vocabulary_probe.py`は、保存した同一WAVをゲーム語彙なし・旧21語・現在の語彙で認識する小規模な合成音声試験。自宅サーバーの既存開発agent内でCPU Whisperを実行し、条件の順序を文ごとに回す。Irodoriで生成した音声をスピーカーへ流すことはなく、ゲーム操作も行わない。基本ヒントは実行中のpersona設定から取得する。実行器、語彙、基本ヒント、モデル、音声の指紋を保存して比較し、条件が変わった結果は分ける。

```powershell
python scripts/server/game-vocabulary-home.py --label vocabulary-new --baseline-ref '30722b8^'
python scripts/server/game-vocabulary-home.py --label vocabulary-repeat --baseline-ref '30722b8^' --reuse-audio vocabulary-new
```

`--baseline-ref`は旧21語が入ったコミットを明示する（省略時HEAD）。`--reuse-audio`はサーバー上に残した測定のWAVを使い、新規合成を避ける。ラベルは毎回新規にする。結果と録音は`server/benchmark/data/<label>/`へ回収される。対象語の一致と全文CERを併記し、漢数字と算用数字の差を隠さない。雑談・否定3文を対照にするが、人のマイク・雑音・発話確定・会話応答の評価を代替しない。ヒントが現在のWhisperの223token枠を超える場合は測定を失敗させる。この検査は評価器のものであり、実行時のヒント切り詰め処理ではない。

## 評価の根拠

ローカルLLMの重み変更を比べる場合は[人格・身体性・ツール・一般性能の評価](weight-space-benchmark-ja.md)も併用する。正解テキストとSTT認識文を分けてLLMへ入力し、CERの変化と意味の保持、推論遅延と本返答音声遅延を区別する。

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

既定は準備・音声トラックを180秒の接続期限で待ち、挨拶待ち10秒後に再生、追加無音を含む入力完了後30秒間を観測する。挨拶が長い構成では`--greeting-timeout 60`を指定すると、最小待機後に挨拶の音声を観測し、2.5秒間の静音を確認してから入力する。60秒以内に条件が成立しなければ試行エラーとなり、返答の観測期限は延長しない。毎試行後、接続と部屋を閉じる。終了コードは全試行が観測完了なら0、エラー・本返答タイムアウトがあれば1。認識品質の合否閾値はまだ設定していない。

LiveKitの利用環境やworkerのbackend次第では課金されるため、[外部API試験](paid-checks-ja.md)の対象を確認する。スクリプトはクラウドへ自動切替せず、TTS合成の追加要求も出さない。OpenAIのワーカーを指定した場合の料金は別に発生する。

起動中に準備を済ませる[低遅延化の設計](../conversation/conversation-pipeline-ja.md#音声会話の低遅延化)では、準備時間・成功率と、準備後の会話遅延を別に評価する。現行の`--greeting-timeout`は挨拶音声の終了確認であり、モデル・音声経路すべての準備完了を通知する仕組みではない。準備世代や同一部屋での連続ターンの評価は今後の拡張で、現在の`live`は1試料ごとに新しい部屋を作る。準備後に再起動やCPU切替が起きた試行も残し、遅い結果だけを除外しない。

### アプリ設定と推論取り消しの比較

conditionsの`app_profile`に`style`と`hello`を指定すると、`live`は準備完了の通知後に`ciel.style`・`ciel.app`を送り、初回挨拶が落ち着いてから音声を再生する。`style`はtalk/presence/meeting、`hello`はapp.hello v1の能力一覧。本人認証や実端末の動作は模擬しない。アプリ設定なしの旧測定や、挨拶後に設定を変更した試行と混ぜず、前後とも同じ送信タイミングを使う。

`voice-home.py stage --agent-revision <commit>`は会話実装・promptを指定コミットから配置し、測定器は作業ツリーの同じ版を使う。通常のstageは改修候補を配置する。試験workerを止めてから実装を入れ替え、配置した各ファイルの指紋をsource-provenanceへ記録する。試料・期限・反復数を両版で揃え、遅かった中間候補の結果も保持する。

`scripts/server/benchmark-conversation-tools.py --output <new.json>`は実pipelineで組み立てた指示と道具をローカル実モデルへ渡す。能力ロード以外のツールを実行せず、挨拶・否定・議事録・名前・保存状態・会話検索の選択を記録する。モデルの選択とMCPの実処理は別評価。状態照会を先に選んだ場合も記録し、実行完了と見なさない。

`scripts/server/benchmark-inference-cancel.py --gateway <gateway.py> --output <new.json>`は既存の推論プロセスのnativeポート（既定18094）へ専用の入口を作り、入力処理中に切断して推論枠が解放されるまでを測る。枠が使用中なら開始しない。追加モデルは起動せず、通常APIの再配置もしない。各試行の先頭を変えてキャッシュの持ち越しを避け、取り消し後40秒を上限にする。通常の音声ベンチマークは8094経由を維持し、この測定値を音声全体の短縮率に換算しない。

### 自宅サーバーでの合成音声による基準測定

`scripts/server/voice-home.py`はSSH設定を既存の`benchmark-home.py`から読み、自宅の`~/work/ciel-voice-evaluation`だけに測定コードを配置する。稼働中の`ciel-dev`がlocal・pipeline・voice・Irodori・devスコープであることを確認し、本番・開発ワーカーの再配置は行わない。試験クライアントとSTTは既存の開発イメージを使う一時コンテナ（2CPU・3GiB）で動かし、モデルを読み取り専用でマウントする。専用のLLMは起動しない。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-home.py stage
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-home.py prepare
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-home.py stt --smoke --rounds 1
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-home.py live --settled --smoke --rounds 1
# 単発の保存・認識・音声受信を確認してから反復する
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-home.py stt --rounds 3
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-home.py live --settled --rounds 3
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-home.py pull
```

`prepare`はローカルIrodoriで中立な合成4発話（短文・数字・否定・途中の0.6秒の間）と3秒の無音を作る。合成要求文を参照文字列にし、発話末尾はRMS 0.005以上の最後の20msフレームで自動推定する。人による正解・末尾の注釈を用いたコーパスとは区別し、CERには合成自体の読み違いも含み得ると明示する。通常のゲームや道具への指示は送らない。

結果はサーバーの`results/<実行ID>/`、回収先はGit対象外の`server/benchmark/data/voice-home/results/<実行ID>/`。各実行のソースアーカイブ、モデル・イメージ・コード指紋、前後のサービス状態、2秒ごとのGPU/CPUモード・処理中枠数・負荷、該当部屋のデバッグログを保持する。既存サービスの同時要求やキャッシュは制御しない。`prepare`で毎回新しい実行IDを作り、既存結果は上書きしない。

Gitのないコンテナでは`--source-provenance`に配置元のGit識別・dirty状態・ソースSHA-256を持つJSONを指定する。実行器・採点器・デコーダーの実ファイルとの一致を検証し、偽のクリーンなGit状態を作って代用しない。helperは配置時にこのJSONを生成し、測定ごとのソースアーカイブにも含める。

### 高速化の専用比較環境

`voice-fast-home.py`は通常ワーカーを変更せず、起動中の開発イメージに評価用のソース・設定を読み取り専用でマウントする。`baseline`は`CIEL_VOICE_FAST=0`、`fast`は`1`。モデル重み・Vosk・音声・観測時間は共通にする。`reuse`は以前の実行IDの録音と注釈を複製し、TTSで作り直さない。

専用受信口は8097、制御先は8096。既存8094/8095を参照するだけで、通常の共有APIを再起動せず、追加モデルもロードしない。推論世代は専用受信口を指すため、ネイティブモデルの再起動を検証したとは説明しない。この経路を通らない既存クライアントの背景処理まで優先制御できたという保証もない。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-home.py stage
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-fast-home.py reuse --corpus-run 20261110T020907Z
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-fast-home.py proxy-start
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-fast-home.py start --variant baseline
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-fast-home.py live --variant baseline --rounds 3
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-fast-home.py stop --variant baseline
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-fast-home.py start --variant fast
# 単発を確認してから反復。tagを変えると既存結果を残して別の実行を保存できる
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-fast-home.py live --variant fast --tag final --smoke --rounds 1
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-fast-home.py live --variant fast --tag final --rounds 3
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-fast-home.py stop --variant fast
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-fast-home.py proxy-stop
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/voice-home.py pull
```

改修版では`--require-ready`相当が自動で有効になる。`voice.ready` v1を要求・検証し、未配信・異なる版・失敗を準備完了へ変換しない。準備済み通知の到着は`startup_ready_ms`、準備そのものは`readiness.elapsed_ms`に保存する。接続/初期化は180秒の別期限、発話入力後の観測は30秒のまま。最初の挨拶と2.5秒の静音も確認する。現行の測定器は試料ごとに部屋を作るため、長時間の同一部屋での品質・履歴増加は別の確認が必要。

競合時の入場制御だけを検証する場合は、ワーカーの試験を終えてから`contention --variant baseline`と`contention --variant fast`を専用受信口の稼働中に実行する。各1回、背景2件×最大128トークンと前景1件×最大4トークンで、フィクスチャは`server/benchmark/voice/contention.json`。準備済みGPU・処理中要求なしを確認してから始める。これは短いLLM出力までの時間と入場待ちの比較で、音声会話の応答時間には混ぜない。

## 能力追加時の入力計算を比較する

音声全体とは別に、`benchmark-conversation-tools.py`で実pipelineから入力と許可済みツールを生成し、実モデルの選択まで測定する。実行する道具は`load_capabilities`だけで、登録・議事録開始などの副作用は実行しない。関数名に加え、元のJSON Schemaで引数の形式を検証する。これは引数の意味、実サービスでの完了、人格、本人確認の全条件を保証する試験ではない。

`--variant baseline`は現在の入力、`compact`はツール説明の改行後を省略する探索候補（名前・型・制約は保持）、`prepared`は各要求の直前に固定指示と同一ツール定義を1tokenだけ準備する条件。`compact-prepared`は両者を組み合わせる。準備時は動的な状態・実際の発言・tool resultを含めず、出力は破棄する。`requests[].preparation.seconds`と本要求の`seconds`を分け、trial全体の`seconds`は準備も含む。準備費用を除いた値を現在の利用者の待ち時間とは呼ばない。この方式は常駐キャッシュ銀行や永続キャッシュの実装ではない。

`specialist`は能力ロード後だけ、固定指示を評価用`server/benchmark/voice/capability-selector.md`へ置換する。動的system情報、会話、tool call/result、公開ツールと権限制限を保持する。通常サービスのプロンプトは変更しない。専門処理から会話へ結果を返す製品実装や、実操作後の音声応答はこの試験に含まない。

専用の使い捨てコンテナで反復し、共有モデルの再起動・キャッシュ消去をせず、条件の順序を反復ごとに循環させる。準備で他条件のキャッシュが温まる影響も残るため、完全なcold比較とは扱わない。既存開発イメージを使い、接続先は共有8094。共有モード・処理中枠のサンプル、ソースアーカイブ、各要求の入力token/cache利用を保存する。

```powershell
.\.venv\Scripts\python.exe scripts/server/voice-home.py stage
.\.venv\Scripts\python.exe scripts/server/benchmark-capability-cache-home.py --rounds 3
.\.venv\Scripts\python.exe scripts/server/voice-home.py pull
```

既定は能力追加の4課題（議事録開始、自己紹介、保存状態、履歴検索）をbaseline/prepared/specialistで各3回。`--variants`と`--cases`で範囲を指定できる。結果は`results/capability-cache-<UTC>/`に作り、失敗・タイムアウトも残す。

`--fresh-loaded-prefix`は能力追加後の固定指示の先頭に試行固有の評価IDを付け、未準備の固定入力を作る診断条件。準備要求と本要求には同じIDを付ける。既存利用者のキャッシュは消さない。ツール定義などIDより前の共通部分は再利用され得るため、完全なcold起動とは呼ばない。実利用者の会話で同じ失効頻度になる保証はない。準備状態の保存・復元や複数能力の組合せは、別途対応機能とチェックポイントの再利用を確認してから評価する。

### 能力ごとの準備を依頼前にまとめる

`benchmark-capability-bank.py`は、合成課題のpipeline入力を保存したcaptureから固定指示と公開ツールだけを抽出し、重複する記憶能力を統合して事前準備する。全準備が終わるまで利用者の依頼の再生を始めず、その後は再準備しない。準備には利用者の発言・動的状態・tool結果を渡さず、1tokenの出力は破棄する。保存・復元APIや重みの変更は使わない。

評価コンテナ内の実行例（接続先は共有8094、出力先は毎回新規）：

```sh
python scripts/server/benchmark-conversation-tools.py --variant specialist --capture-requests --cases minutes name status history --output results/new-run/capture.json
python scripts/server/benchmark-capability-bank.py --capture results/new-run/capture.json --rounds 3 --output results/new-run/bank.json
```

捕捉するのは評価器自身の合成入力だけとし、実利用者の会話ログをこの形式へ出力しない。能力順は議事録→記憶の仮登録→履歴検索→記憶の状態照会。準備なし／全能力を準備の順番を反復ごとに交代し、各条件に新しい固定入力IDを付ける。最初の能力選択も再生してから具体的な道具を選ぶ。元のcaptureと関数名・引数値が違えばその試行を失敗とし、古いtool結果へ進まない。道具を実行せず、固定された合成会話の再生に限定するため、実操作後の返答や任意の新しい会話へ一般化しない。

`preparations`は開始前の時間・使用量、`trials`は依頼後の時間・cache利用・引数を記録する。準備費用をゼロ扱いせず、準備の途中失敗、他能力を使った後の失効、保存された出力の指紋も確認する。既知の3能力の準備であり、全能力の組合せ・別権限・接続端末の変更にも対応した製品のキャッシュ管理機構ではない。

### 個別スキーマの段階的公開と固定入口を比較する

`benchmark-tool-discovery.py`は、実pipelineの合成captureから記憶・議事録・履歴検索の正規スキーマを抽出し、次の2条件を同じ会話系列で比較する。通常サービスの処理は変更しない。

- `native`：最初はdiscoverだけを公開し、選んだサービスの個別関数を完全なスキーマ付きで`tools`へ追加する。探索結果には公開した名前だけを返し、スキーマ本文の二重投入を避ける。
- `fixed`：discoverとexecuteの2入口を固定し、探索結果のtoolメッセージへ完全なスキーマ・tool_id・版を返す。executeにはそのID・版・引数を渡す。実行器は正規スキーマ、既知ID、版、探索済みの公開範囲を検証する。名前や版を推測して拒否された要求は、後で修正できてもその試行を合格にしない。
- `hybrid`：discover/executeに加え、register_participant_nameとget_speaker_statusだけを個別定義として常時公開する。計4定義は探索後も不変。個別入口の2操作だけ探索を省けるが、同じ記憶サービスの他の操作やexecute経由の未探索呼び出しは許可しない。常時公開する2つは今回の比較対象の候補であり、実利用の頻度分析から最適集合を確定したものではない。

両条件に同じ短い道具選択指示を与え、呼び方だけ別ファイルで説明する。system本文は会話内で固定し、探索結果・呼び出し・検証結果・次の依頼は末尾へ追加する。記憶→履歴検索→記憶→履歴検索の再利用、議事録開始と否定、挨拶の計8ターンを各3回測り、条件順を交代する。初期の固定入力IDは試行ごとに変え、他の利用者のキャッシュは消去しない。

```sh
python scripts/server/benchmark-tool-discovery.py --capture results/capture-run/capture.json --rounds 3 --output results/new-run/comparison.json
python scripts/server/benchmark-tool-discovery.py --capture results/capture-run/capture.json --modes native fixed hybrid --rounds 3 --output results/new-hybrid-run/comparison.json
```

`requests`に入力token/cache利用/ツール定義の指紋、`discoveries`に探索回数、`invalid`に拒否された生成、`calls`に検証済みの関数と引数を保存する。合格条件は期待した関数・引数値との一致、不正要求・通信エラーなし。挨拶と否定では探索も操作もしないことを要求する。速度は依頼から検証済みの呼び出し生成までで、実サービスの完了・音声・本来の本人確認を含まない。道具の結果は`validated_only/executed=false`であり、実操作済みの会話ではない。

共有キャッシュ・モデル内のチェックポイントは別に影響する。固定入口で送信メッセージを追記だけにできても、モデルのcache再利用が常に完全になるとは判定しない。判定器のテストでは、個別公開時の定義変更、固定入口の定義不変と履歴のprefix不変、未知ID・未公開・古い版・欠けた/型違い/余分な引数の拒否を確認する。

## 結果の読み方と次の改善

`report.json`はGitコミット・dirty状態、実行器/採点器/デコーダーのSHA-256、コーパス指紋、条件、反復ごとの結果を持つ。例外が起きても試行ごとに保存し、失敗を集計する。同一コーパス・端末・モデル・負荷・設定で前後各3回以上測り、一度にSTTモデル、発話区切り、LLM、TTSのいずれか一つを変更する。反復再生は独立した話者数を増やすものではない。

CERが悪くRTFが低ければ、まず雑音条件・固有名詞・否定・数字の誤りを確認し、大きいVoskモデル等を同一録音で比較する。自然確定が遅い/EOFが多ければ音声区切りを調べる。単体STTが速く会話が遅い場合は、試験workerの既存デバッグログの`latency`（文字起こし、返事を頼んだ、最初の文字、文、声）も確認する。このログの起点はホストの発話終了判定であり、録音の発話末尾とは違う。別試行の値を引き算しない。共有GPUの待機・CPU切替、話者確認・記憶取得も条件に含める。

音声受信は20msフレームのRMSが閾値（既定0.01）を超えた開始を検出する。トラック内の短い無音でも別の開始になるため、途中終了前の本返答や相づちとの重なりは生音声・ログで確認する。`pre_end_reply_audio`は割り込みの候補で、適切な相づちかどうかの自動採点ではない。

LiveKitが試験参加者の確定文字起こしを配信しない場合、`transcript_available=false`とし、CERは集計しない。無音試料でも配信がないことを「認識が空だった」とは扱わない。認識の比較には単体STTの結果を用いる。

受信遅延は再生開始の単調時計＋手動注釈を起点とする。ネットワーク・AudioSourceのキュー誤差を含み、実マイクの捕捉やUnityのスピーカー再生までは測らない。挨拶が計測中まで続く構成では待機時間を調整して再測定する。発話内容の妥当性・自然さ、音質、真の割り込みによる停止時間、多ターン文脈の理解は自動測定の対象外。代表録音で認識の意味保持と回答の適切さを人が評価し、最終的には実アプリのマイク会話で確認する。
