# 記憶の想起の評価

> 責務：会話の1ターンで、関係する記憶が会話モデルへ届くかを測る課題・指標・今の方式の再現範囲・実行と比較の方法。

[関連性で思い出す記憶の設計案](../services/associative-memory-ja.md)の段階0の評価器です。結果は[能力・会話の実測](capability-results-ja.md#記憶の想起の基準値)に置きます。

## 測るもの

1ターンの会話の前に、どの記憶が会話モデルの前に置かれるか（検索の層）だけを測ります。LLM・DB・ゲームを使わず、決まった結果になります。

- **測らないこと：** シエルが思い出したことを実際に話すか、その自然さ、ゲームに今もあるかの確認。これらは段階1以降に、返答の評価として別に測ります。
- **前提：** 話している人は声で本人と分かり、メモの保存に同意済みとします。今の方式にとって一番有利な条件です。

## 課題

追跡する課題定義は`server/benchmark/memory_recall_cases.json`（版`memory-recall-v1`）です。人物・メモ・出来事はすべて作った例で、実際の会話や個人のメモは入れません。

| 段階 | 難しさ | 課題 |
|---|---|---|
| 1 | 最近の記憶で、言葉が重なる | 最近のメモ、好み、きのうの日記 |
| 2 | 言葉が重ならず、使い道・意味でつながる。古めの記憶。公開範囲 | 休む話と拠点、村、新しいメモが25件ある古いメモ、新しい日記が12件ある出来事、関係のない雑談、人前、別の人のメモ |
| 3 | 保存の上限、事実の更新、複数の記憶、時間の範囲、覚えていないこと | 上限を超えたメモ、壊れた拠点、作り直す前のワールドの拠点、家と畑、きのうの出来事、覚えていない海の話 |

能力の分類はLongMemEvalの5つ（取り出し`extraction`、会話をまたぐ`multi_session`、時間`temporal`、更新`update`、知らないと答える`abstention`）に、公開範囲`privacy`と対照`control`を足したものです。

- **埋め草：** 対象の記憶より新しい・古い記憶を、課題と関係のない話題で決まった数だけ足します（例：好きな果物、クモを倒した）。対象が何件目にあるかで難しさを作ります。
- **正解：** 課題ごとに、届くべき記憶（`relevant`）、届くなら過去として扱うべき記憶（`past`）、届いてはいけない記憶（`forbidden`）を決めます。

## 今の方式の再現

`CurrentMethod`は、今の会話サーバーの動きをそのまま写します。上限の数は、会話サーバーのソースから読みます。

| 記憶 | 今の会話サーバー | 評価器での扱い |
|---|---|---|
| 話している人のメモ | 保存は新しい50件（`speaker_store.MAX_NOTES`）。ひとり・身近な人のときは、新しい15件を発言に添える（`speakers.PUSH_NOTES`）。人前では添えない。全件は`recall_about_speaker`で読める | 15件を「届く」、残りを「道具でだけ届く」 |
| ほかの人のメモ | その人の発言にしか添えない | 届かない |
| シエルの好み | 全件を指示に入れる | 届く |
| シエルの日記 | 保存はするが、会話には渡さない。好みを育てる処理だけが新しい40件を読む | 届かない |
| 拠点・名前を付けた場所 | 体の中にあり、会話からは見えない | 届かない |
| 家を建てた・村を見つけたなど | 記録しない | 届かない |

あいさつに添える持ち主のメモ（新しい5件）は、15件に含まれるので別に数えません。この`current`は段階0の基準で、関連性で思い出す前の会話サーバーです。

## 関連性で思い出す方式

`RecallMethod`（`--retriever recall`）は、`current`の渡し方に、会話サーバーの`recall.eligible`・`recall.rank`で選んだ記憶を足します。公開範囲・本人・ワールドの判定と順位づけは会話サーバーと同じコードです。

- **問い：** 課題の相手の発言。
- **鍵：** `write-keys`で、会話サーバーと同じ指示（`prompts/memory_keys.md`）から書いたもの。OpenAI互換の窓口（共有GPU APIなど）へ温度0で送り、指示のハッシュとモデル名を一緒に残します。指定しなければ鍵なし。
- **埋め込み：** `--embedder`のsentence-transformersのモデル。指定しなければ、文字の重なりと日付だけで思い出します。
- **重要度：** 場所は4、ほかは3（会話サーバーと同じ）。

## 指標

| 指標 | 単位と値 | 良い方向 | 欠測・限界 |
|---|---|---|---|
| `recall_auto` | 課題ごとに、届くべき記憶のうち会話モデルの前に置かれた割合 | 高い | 届くべき記憶がない課題はnull。0や1にしない |
| `recall_reach` | 道具を呼べば届く分も含めた割合 | 高い | 道具を呼ぶかはモデル次第で、届いたとはいえない |
| `ranks` | 届くべき記憶が何番目に置かれたか | 小さい | 今の方式は時刻順で、関連の順位ではない |
| `forbidden_auto` | 届いてはいけない記憶が置かれた数 | 0 | 公開範囲・別の人・別のワールド |
| `stale_as_current` | 無効になった記憶が、過去の印なしで置かれた数 | 0 | 候補は記憶ごとに過去の印を返す |
| `recalled_extra` | 関連性で選ばれたのに、届くべき記憶でも過去の印の付いた記憶でもない数 | 少ない | 話の種になりうる近い出来事も数える。0を目標にせず、しきい値を比べるときの雑音の目安 |
| `auto_count`・`auto_chars` | 置かれた記憶の件数と文字数 | 品質を保って少ない | 入力の費用の目安。トークン数ではない |

- **集計：** 全体、段階別、能力別に、`recall_auto`の平均、全部届いた課題の数、`forbidden_auto`・`stale_as_current`・`recalled_extra`の合計、費用の平均を出します。重み付きの総合点は作りません。
- **感度の確認：** テスト（`server/benchmark/tests/test_memory_recall.py`）で、正解だけを返すと満点、全部を返すと想起は上がっても公開範囲・別のワールド・壊れた拠点の誤りが数えられ、1件だけ返すと0.5になることを確かめています。

## 実行と比較

リポジトリのルートで実行します。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 server/benchmark/memory_recall.py score --retriever current --out .local/memory-recall/current-baseline.json
.\.venv\Scripts\python.exe -B -X utf8 server/benchmark/memory_recall.py write-keys --llm-url http://127.0.0.1:18094/v1 --out .local/memory-recall/keys.json
.\.venv\Scripts\python.exe -B -X utf8 server/benchmark/memory_recall.py score --retriever recall --keys .local/memory-recall/keys.json --embedder cl-nagoya/ruri-v3-30m --out .local/memory-recall/recall.json
.\.venv\Scripts\python.exe -B -X utf8 server/benchmark/memory_recall.py compare <基準.json> <候補.json>
.\.venv\Scripts\python.exe -B -X utf8 -m unittest server/benchmark/tests/test_memory_recall.py
```

- **報告：** 課題集のハッシュ、検索方式の名前と設定、Gitのコミット、課題ごとの値を残します。
- **比較：** 課題集のハッシュが同じときだけ比べ、課題ごとの差、想起が上がった・下がった数、新しく増えた漏れ・古い事実の数を出します。
- **心が選ぶ方式（`--retriever mind`）：** 同じ検索で広めの候補（上位8件・関連度0.2以上）を作り、`--llm-url`のLLMに会話サーバーと同じ`server/agent/config/prompts/recall_mind.md`の指示で選ばせます（候補の数も`recall.MindRecall`と同じ）。選んだものだけを添えます。報告の`llm_calls`に、1回ごとの時間・入力と出力のトークン数・心が書いた「思ったこと」が残ります。LLMを使うので、同じ条件でも結果が揺れることがあります。
- **候補の足し方：** ほかの検索方式は、`retrieve(memories, context)`で`Item(id, channel, past, recalled)`の並びを返す（`recalled`は話題に合わせて選んだ印）部品として`RETRIEVERS`に足します。報告の`retriever_config`に、埋め込みモデル・鍵の数・上位件数・しきい値が残ります。

## 決まっていないこと

- 課題は16件で、各能力の課題は1〜6件です。段階1で候補を選ぶ前に、使わずに取っておく課題（holdout）を足します。
- 返答の層（思い出したことを話すか・自然さ・作り話をしないか）の採点方法。
