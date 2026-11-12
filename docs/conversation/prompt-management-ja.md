# 会話プロンプトの管理

> 責務：Markdown/TOMLの指示管理、ロード・指紋・編集・評価の契約。

この資料は指示本文・TOML・読み込み・変更時の評価の契約を所有する。実際のキャラクター本文は`server/agent/config/prompts/`に置き、説明文書へ複製しない。

## 採用する構成と理由

外部実行APIの出力形式は`server/agent/config/prompts/execution_api.md`をCoreHostが読み込む。人格・記憶は共通だが、音声の表情タグを行動命令へ混ぜない。Minecraftの目標解釈は`server/minecraft/src/mindcraft/prompts/goal.md`、行動判断は同じディレクトリの`action.md`をbrain.jsが読み込む。最終成果物と次の行動を区別し、Mindcraftのレシピ分析も観測に添える。これらを変更した場合も実モデルで依頼解釈と目的達成を別々に確認する。

本文は UTF-8 の Markdown、参照先は TOML、読み込み処理は Python で管理する。日本語の長文を設定ファイルの文字列として編集する負担を減らし、エディタの Markdown プレビューと Git の差分確認を使える構成にする。専用のプロンプト管理サービスは現時点では導入しない。

| ファイル | 責務 |
|---|---|
| `server/agent/config/persona.toml` | 本文ファイルの選択 |
| `server/agent/config/prompts/stt_vocabulary.md` | CPU Whisperへ渡す固有名詞の語彙ヒント。会話本文や認識後の置換規則ではない |
| `server/agent/config/prompts/character.md` | 人物像・話し方・会話上のルール |
| `server/agent/config/prompts/ciel_self.md` | シエル自身の好み・苦手・こだわり（企画の設定資料から、好みと癖だけを選んだもの。物語の人や場所は入れない）。会話モデル（心・小脳）と内なる考えの両方に渡す。[内なる考え](conversation-pipeline-ja.md) |
| `server/agent/config/prompts/ciel_growth.md` | 会話の終わりに、本当にあった出来事からシエルの好みが育つかを決める係への指示。処理は `growth.py`。[好みの育ち方](../services/shared-memory-ja.md) |
| `server/agent/config/prompts/greeting.md` | 初回あいさつを生成するための指示（前に「[今：…]」の 1 行が付く。[今の日時](conversation-pipeline-ja.md)） |
| `server/agent/config/prompts/greeting_owner.md` | 端末の持ち主が分かっているとき（ひとり・身近な人）の初回あいさつ。`{name}` を持ち主の名前に置き換える（`agent.py` の `greeting`）。[話者の識別](../services/shared-memory-ja.md) |
| `server/agent/config/prompts/enroll_done.md` | アプリの「声を登録する」で登録できたときのひとこと。`{name}` を登録した人の名前に置き換える（`agent.py` の `enrolled`） |
| `server/agent/config/prompts/emotion.md` | Irodori 用の感情タグの指示 |
| `server/agent/config/prompts/touch.md` | 画面のタッチの知らせ（`[タッチ]` の行）への反応の仕方 |
| `server/agent/config/prompts/talk_quiet.md` | おしゃべり度「ひかえめ」で足す、答える・黙る（`[silent]`）の決まり。処理は `mode.py`（2026-10-17 に `group.md` から） |
| `server/agent/config/prompts/talk_quiet_turn.md` | ひかえめのとき、返事を作らせるたびに `generate_reply` の instructions として添える短い念押し。処理は `turns.py`（2026-10-17 に `group_turn.md` から） |
| `server/agent/config/prompts/talk_chatty.md` | おしゃべり度「おしゃべり」で足す、自分から話しかけるときの決まり |
| `server/agent/config/prompts/talk_chatty_nudge.md` | おしゃべりのとき、話したい考えがあれば `generate_reply` の instructions として渡す合図。処理は `initiative.py` |
| `server/agent/config/prompts/inner_thoughts.md`・`talk_correction_nudge.md`・`talk_inner_state.md`・`inner_thoughts_voice.md` | シエルの内なる考え（会話の裏で考えを作り、話したい気持ちを決める係への指示）と、ふつうのときの言い直しの合図。処理は `initiative.py`。[内なる考え](conversation-pipeline-ja.md) |
| `server/agent/config/prompts/presence_solo.md`・`presence_close.md`・`presence_public.md` | その場にいる人（ひとり・身近な人・人前）ごとの、覚えている人のメモの使い方。処理は `mode.py`・`speakers.py` |
| `server/agent/config/prompts/speakers.md` | 「[発言者：…]」の読み方、名前を聞く・同意を取る流れ、人についての道具の使い方（2 人でも多人数でも。`CIEL_VOICE=irodori` で Realtime API のとき）。処理は `speakers.py`・`tools/people.py` |
| `server/agent/config/prompts/notes.md` | 会話の裏でメモを書く記録係（別の文字のモデル）への指示。処理は `notes.py`。[メモの決定記録](../services/shared-memory-ja.md) |
| `server/agent/config/prompts/conversation.md` | 接続中の共通履歴を検索する道具の使い方。[共通会話履歴](conversation-pipeline-ja.md)。今の日時（「[今：…]」と道具 `current_time`）の使い方。[今の日時](conversation-pipeline-ja.md) |
| `server/agent/config/prompts/relationship.md` | 会話の終わりに、シエルがその人をどう思っているか（関係）を書き直す係への指示。処理は `relationship.py`。[関係の決定記録](../services/shared-memory-ja.md) |
| `server/agent/config/prompts/minutes.md`・`minutes_live.md`・`minutes_voice.md` | 会話のまとめ（議事録など）の清書・ライブの差分・声での頼まれ方。処理は `minutes.py`・`summaries/`。[議事録の決定記録](../services/meeting-minutes-ja.md) |
| `server/agent/config/summaries/*.toml`・`*.md` | まとめのテンプレート。TOML は見出しと種類（モデルへの本文ではない）、Markdown は書き方の指示（モデルへそのまま渡す） |
| `server/agent/config/prompts/talker.md`・`mind_brief.md`・`listener.md`・`tasks.md` | `CIEL_MODEL=pipeline`の共通会話指示（会話と必要な道具の選択）、背景の短いまとめ、付箋と依頼の印の読み方。`listener.md`は独立モジュール用に残すが、通常pipelineの途中文字起こしには接続しない。処理は`mind.py`・`board.py`。[会話の処理構造](conversation-pipeline-ja.md) |
| `server/agent/persona.py` | 設定の検証、ファイルの読み込み、本文一式のハッシュ計算 |
| `server/agent/config/prompts/game_select.md`・`game_intake.md`・`game_draft.md` | ゲーム受付の能力選択・選択済み能力の引数生成・確認への補足。draftのある選択時だけ補足用本文を追加し、通常の指示を維持する |
| `server/agent/agent.py` | 声の方式に応じた指示の組み合わせと会話への適用 |

Markdown は HTML に変換せず、そのソースをモデルへ渡す。見出し・箇条書きは利用できる。コメントや front matter を取り除く処理、テンプレート処理はない。変数展開は `greeting_owner.md`・`enroll_done.md` の `{name}` だけ（名前を別の行のデータとして渡すだけでは、名前を呼ばないことがあったため）。編集者向けの説明・出典は README やこの文書に置く。

既存のプロンプトは内容を変えずに移行した。人物像の元資料はリポジトリ外の `D:\CIEL\企画設計\キャラ\シエル\キャラクター設定資料_主人公_シエル.md`。会話用プロンプトは資料全文ではなく、会話に必要な設定をまとめたものとする。

## 読み込みと反映

- `CIEL_PERSONA_CONFIG` が未指定または空の場合、`server/agent/config/persona.toml` を使う。環境変数の相対パスは `server/agent/` 基準。
- 必須の本文参照は`persona.py`と`config/persona.toml`を正本とする。相対パスは選択したTOMLのディレクトリ基準、絶対パスも利用できる。
- 会話開始時に設定された本文ファイル一式を読み込み、その会話の指示と初回あいさつに同じ設定を使う。会話中の再読み込みはしない。
- 人物像とあいさつは共通。感情タグの指示は `CIEL_VOICE=irodori` の場合だけ人物像に追加する。タッチの指示はどの声の方式でも追加する。その場にいる人の指示（話者の識別を使うとき）と、おしゃべり度の指示（ひかえめは `CIEL_VOICE=irodori` のときだけ。ふつうは足さない）を最後に追加する。
- 設定・本文の欠落、不正な TOML、不正な UTF-8、空の本文はエラーにする。別のキャラクターへ自動で切り替えない。
- Docker は `config/` をイメージへコピーする。Compose は同じディレクトリを読み取り専用でマウントする。ホスト側の編集は次の会話から反映される。

複数ファイルの同時更新を保証する仕組みはない。関連する本文をまとめて更新するときは新規会話を止めて一式を更新するか、別ディレクトリに完成版を用意して設定を切り替える。進行中の会話は読み込み済みの内容を使い続ける。

## 変更・評価・公開の手順

1. 本文または参照先を変更し、Git の差分で意図しない変更や指示の矛盾がないか確認する。
2. `load_persona()` で読み込みを確認する。ローダー変更時は、起動ディレクトリに依存しないパス解決、別設定、欠落・空・不正なファイルも確認する。
3. 本文を変更した場合は、同じモデル・声の方式で代表的な会話を比較する。あいさつ、落ち込みへの返答、分からない質問、長い説明、口癖の頻度、割り込みへの反応を確認する。Irodori はタグの付与と読み上げからの除去も確認する。
4. 変更理由、使用モデル・声の方式、確認結果、未検証の項目を PR や作業記録に残す。読み込み確認と実際の会話品質の確認を区別する。
5. 確認済みの本文・TOML・必要なコードを同じ Git コミットで管理し、本番へ配布する。問題があれば以前の確認済みコミットの一式へ戻す。

代表的な人格・身体性・指示・ツールの比較は[WSPベンチマーク](../testing/weight-space-benchmark-ja.md)でも実行できる。これは5promptの固定probeであり、会話ホスト全体や音声を再現する試験ではない。人格の自然さは人手確認を残す。開発時の即時反映は許容する。本番でも直接編集が技術的に可能だが、運用上は確認済みの一式を配布する。

人物像と指定形式の競合、未接続での動作描写、サービスIDの誤りを減らす実験候補は`server/benchmark/weight_space/prompt_candidates/grounded-body-v1/`に保存した。`character.md`と`tool_discovery.md`を変更した固定5promptの比較用スナップショットで、本番用の正本ではない。自動採用条件を満たしていないため、通常の`server/agent/config/prompts/`は基準版を維持する。候補を再利用するときは現行の正本との差分を確認する。

会話開始ログには `persona_sha256`、会話モデルの選択、Realtime のモデル名、声の方式を記録する。ハッシュは読み込んだ本文一式を順序固定で JSON 化し、UTF-8 の SHA-256 を求める。適用しない感情指示も含む、設定一式の識別子である。履歴の保存・復元は Git が担う。ハッシュだけで本文は復元できず、モデル出力の完全な再現を保証するものでもない。プロンプト本文や会話内容はこの識別用ログへ出さない。
## 能力の段階的ロード

音声の準備と最初の文には`voice_warmup_file`・`voice_first_sentence_file`を必須設定として読み込む。前者は準備時だけLLM/TTSへ渡し、会話の履歴へ保存しない。後者はローカルの高速音声設定で共通会話指示へ追加し、人物像や操作の確認を省略せずに最初の一文を短くする。どちらも人物設定の指紋へ含め、比較時には実際に適用した高速設定も記録する。

`tool_discovery_instructions_file`を必須設定とし、会話開始時に読み込んで指紋へ含める。pipelineはサービスの詳細な使い方を能力ロードのtool結果へ返し、固定systemへ後から追加しない。名前の仮受付・保存状態照会と、取得した定義をexecute_capabilityで使う短い規則は常時保持する。人物像、本人確認・保存同意・公開範囲も維持する。[能力カタログ](capability-runtime-ja.md)を参照する。

指示の内容・話し方の個別変更は本文のGit差分と評価に残す。過去の変更理由や試験の逐次追記はこのファイルへ置かない。結果の現状は[確認状況](../testing/verification-status-ja.md)を更新する。
