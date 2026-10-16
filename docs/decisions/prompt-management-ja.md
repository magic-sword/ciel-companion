# 会話プロンプトの管理方針

決定日：2026-10-13。対象：`server/agent` の GPT-Live / Realtime 会話プロンプト。

## 採用する構成と理由

本文は UTF-8 の Markdown、参照先は TOML、読み込み処理は Python で管理する。日本語の長文を設定ファイルの文字列として編集する負担を減らし、エディタの Markdown プレビューと Git の差分確認を使える構成にする。専用のプロンプト管理サービスは現時点では導入しない。

| ファイル | 責務 |
|---|---|
| `server/agent/config/persona.toml` | 本文ファイルの選択 |
| `server/agent/config/prompts/character.md` | 人物像・話し方・会話上のルール |
| `server/agent/config/prompts/greeting.md` | 初回あいさつを生成するための指示 |
| `server/agent/config/prompts/emotion.md` | Irodori 用の感情タグの指示 |
| `server/agent/config/prompts/touch.md` | 画面のタッチの知らせ（`[タッチ]` の行）への反応の仕方 |
| `server/agent/config/prompts/group.md` | 多人数（会議）のモードで足す、答える・黙る（`[silent]`）の決まり。処理は `mode.py` |
| `server/agent/config/prompts/group_turn.md` | 多人数のモードで、返事を作らせるたびに `generate_reply` の instructions として添える短い念押し。処理は `turns.py`（2026-10-16） |
| `server/agent/config/prompts/speakers.md` | 「[発言者：…]」の読み方、名前を聞く・同意を取る流れ、人についての道具の使い方（2 人でも多人数でも。`CIEL_VOICE=irodori` で Realtime API のとき）。処理は `speakers.py`・`tools/people.py` |
| `server/agent/config/prompts/notes.md` | 会話の裏でメモを書く記録係（別の文字のモデル）への指示。処理は `notes.py`。[メモの決定記録](person-notes-ja.md) |
| `server/agent/persona.py` | 設定の検証、ファイルの読み込み、本文一式のハッシュ計算 |
| `server/agent/agent.py` | 声の方式に応じた指示の組み合わせと会話への適用 |

Markdown は HTML に変換せず、そのソースをモデルへ渡す。見出し・箇条書きは利用できる。コメントや front matter を取り除く処理、変数展開、テンプレート処理はない。編集者向けの説明・出典は README やこの文書に置く。

既存のプロンプトは内容を変えずに移行した。人物像の元資料はリポジトリ外の `D:\CIEL\企画設計\キャラ\シエル\キャラクター設定資料_主人公_シエル.md`。会話用プロンプトは資料全文ではなく、会話に必要な設定をまとめたものとする。

## 読み込みと反映

- `CIEL_PERSONA_CONFIG` が未指定または空の場合、`server/agent/config/persona.toml` を使う。環境変数の相対パスは `server/agent/` 基準。
- TOML 内の `instructions_file`、`greeting_file`、`emotion_instructions_file`、`touch_instructions_file`、`group_instructions_file`、`group_turn_instructions_file`、`speaker_instructions_file`、`notes_instructions_file` は必須。相対パスは選んだ TOML のディレクトリ基準。絶対パスも利用できる。
- 会話開始時に七つのファイルを読み込み、その会話の指示と初回あいさつに同じ設定を使う。会話中の再読み込みはしない。
- 人物像とあいさつは共通。感情タグの指示は `CIEL_VOICE=irodori` の場合だけ人物像に追加する。タッチの指示はどの声の方式でも追加する。多人数の指示は、Unity が多人数のモードを知らせたときだけ最後に追加する（`CIEL_VOICE=irodori` のときだけ）。
- 設定・本文の欠落、不正な TOML、不正な UTF-8、空の本文はエラーにする。別のキャラクターへ自動で切り替えない。
- Docker は `config/` をイメージへコピーする。Compose は同じディレクトリを読み取り専用でマウントする。ホスト側の編集は次の会話から反映される。

複数ファイルの同時更新を保証する仕組みはない。関連する本文をまとめて更新するときは新規会話を止めて一式を更新するか、別ディレクトリに完成版を用意して設定を切り替える。進行中の会話は読み込み済みの内容を使い続ける。

## 変更・評価・公開の手順

1. 本文または参照先を変更し、Git の差分で意図しない変更や指示の矛盾がないか確認する。
2. `load_persona()` で読み込みを確認する。ローダー変更時は、起動ディレクトリに依存しないパス解決、別設定、欠落・空・不正なファイルも確認する。
3. 本文を変更した場合は、同じモデル・声の方式で代表的な会話を比較する。あいさつ、落ち込みへの返答、分からない質問、長い説明、口癖の頻度、割り込みへの反応を確認する。Irodori はタグの付与と読み上げからの除去も確認する。
4. 変更理由、使用モデル・声の方式、確認結果、未検証の項目を PR や作業記録に残す。読み込み確認と実際の会話品質の確認を区別する。
5. 確認済みの本文・TOML・必要なコードを同じ Git コミットで管理し、本番へ配布する。問題があれば以前の確認済みコミットの一式へ戻す。

現在の会話ケースは手動確認用であり、自動のモデル評価は未導入。開発時の即時反映は許容する。本番でも直接編集が技術的に可能だが、運用上は確認済みの一式を配布する。

会話開始ログには `persona_sha256`、会話モデルの選択、Realtime のモデル名、声の方式を記録する。ハッシュは読み込んだ七つの本文を順序固定で JSON 化し、UTF-8 の SHA-256 を求める。適用しない感情指示も含む、設定一式の識別子である。履歴の保存・復元は Git が担う。ハッシュだけで本文は復元できず、モデル出力の完全な再現を保証するものでもない。プロンプト本文や会話内容はこの識別用ログへ出さない。

## 返事の長さ（2026-10-16）

利用者から、2 人のときも返事が長くて話しにくいと言われた。`character.md` には「短めの文で」としかなく、1 回の返事の長さを決めていなかった。

- `character.md` の話し方に足した：ふだんは 1〜2 文、長くても 3 文まで。案をたくさん並べず、いちばん良いものを 1 つ言う。質問は 1 回の返事に 1 つまで。
- `greeting.md`：あいさつは全部で 2 文まで。
- 比べた結果（同じ合成した声の 2 人の会話 6 文、本番とは別のコンテナ、あいさつを含む 7 回の返事）：
  - 変える前：1 回の返事が平均 6.3 文・120 字（最大 9 文・185 字）。毎回質問を重ね、名前も何度も聞いた。
  - 変えた後：平均 2.9 文・66 字（最大 4 文・93 字）。
- 多人数（同じ 8 文）でも、呼ばれたときの返事は 3〜4 文・65〜109 字（変える前は 3〜4 文で 1 文が長かった）。
- 気づいたこと：1 回だけ「ひとつ提案して、次のステップをあなたに任せますね」と、決まりのことを口にした。

## 将来拡張する条件

編集者が増え、ブラウザからの共同編集、公開権限、段階的公開、A/B テストが必要になったら専用レジストリを検討する。その場合も履歴と本番採用版を分け、会話内のバージョン固定、評価結果との対応、ロールバックを維持する。

## 判断の参考にした公式資料

保存形式の統一標準ではなく、以下の資料にある管理方法を参考にしたプロジェクト内の決定である。

- [OpenAI: Prompting](https://developers.openai.com/api/docs/guides/prompting)：プロンプトをコードと同様に整理・レビュー・評価する。
- [OpenAI: Prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering)：Markdown の見出し・箇条書きで指示を構造化する。
- [OpenAI: Prompting GPT-Live](https://developers.openai.com/api/docs/guides/live-prompting)：会話用の指示を短く保ち、代表的な会話で確認する。
- [Google Genkit: Dotprompt](https://genkit.dev/docs/js/dotprompt/)：本文とモデルなどのメタ情報を分け、ファイルで管理する設計例。
- [Langfuse: Prompt Version Control](https://langfuse.com/docs/prompt-management/features/prompt-version-control)：履歴と本番採用版を分ける。
- [MLflow: Prompt Registry](https://mlflow.org/docs/latest/genai/prompt-registry/)：プロンプトの版とモデル設定を併せて追跡する。
