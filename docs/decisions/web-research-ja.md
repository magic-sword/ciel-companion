# シエルのWeb検索と調査記録

2026-10-18。Realtimeから関数ツール `research_web(question)` を呼び、サーバー側のResponses APIでWeb検索する。会話モデルと声の方式は変更しない。

## 検索

- `web_research.py` の `WebResearcher`。既定モデルは `gpt-5.4-mini`、変更は `CIEL_RESEARCH_MODEL`。既存の `OPENAI_API_KEY` を使用する。検索と文字モデルの追加料金が発生する。
- Responsesへ `tools=[{"type":"web_search","external_web_access":true}]`、`tool_choice="required"`、`store=False`、推論量low、最大出力2200トークンで問い合わせる。会話全文や人物メモを送らず、ツールの質問（600字以内）と依頼日時だけを送る。相対日付の解釈に日本時間の日時を渡す。
- 最初は明示的な「検索して・調べて・ネットで確認して」に対応する。対象・地域・日付などが不足していればシエルが確認する。変化する情報の再確認も検索する。
- 同じ接続の同時検索は1件。検索は最大45秒、SDKの自動再試行なし。検索済みと扱うのはResponsesとweb_search_callがcompletedで、本文と有効な引用URLがある場合だけ。失敗・打ち切り・出典なしを、モデル知識による回答で埋めない。
- 正常なHTTP(S)の引用URLだけを採用する。本文中のURLを正規表現で拾って出典にすることはせず、APIの `url_citation` を使う。引用箇所を `[1]` などの番号に置き換える。要点・条件・資料の日付・未確認事項は調査本文に含める。
- 指示は `config/prompts/research.md`、シエル向けの道具の使い方は `research_voice.md`。会話開始時に読み、Personaのハッシュへ含める。

## 会話との対応

- `research.py` の `ResearchBook` は接続ごとに独立し、`Conversation.research` が持つ。質問、依頼日時、取得日時、状態、本文、引用出典、依頼元の発言ID、ツール呼び出しID、返答の発言IDを保持する。
- 調査本文を会話の発言として追加しない。シエルが実際に話した分だけは、従来どおり会話履歴へ入る。人物メモ・議事録・関係の更新は実際の会話を読み、調査本文を本人の発言や好みとして取り込まない。
- 依頼元はツール実行時点の直近ユーザー発言。書き起こし待ちでも、予約済みの発言IDを参照する。割り込み等で直近発言が変わる場合があるため、因果関係の完全な保証ではない。
- 返答との対応はLiveKitの公開API `RunContext.speech_handle`、`SpeechHandle.chat_items` と `add_done_callback` を使用する。ツール結果が利用可能になった後、同じ返答ハンドル内に追加されたassistant項目のIDを共通履歴と照合する。別の返答を「次の発言だから」という理由で結び付けない。対応は「この調査結果を参照できた返答」であり、全出典を実際に口頭で引用したという意味ではない。返答が無いときは返答IDを空にする。
- 会話検索の結果に、質問や返答IDから関連する調査記録を最大3件、合計7000字以内で返す。本文は各900字、出典は最大3件へ縮め、省略を明記する。詳細は `read_research(research_id)`。再参照は追加のWeb検索をしない。
- checked_atは取得日時であり、公開日や出来事の日時ではない。営業時間・価格・予定などを最新情報として答える必要がある場合は再検索する。

## 保持とアプリ

- 調査記録は接続中だけのメモリー。DB・ファイルへの保存や、本文のログ出力は追加しない。最大50件・本文と質問と出典の合計20万字。本文は1件5000字、引用出典は8件、返答との対応は20件まで。保持上限で捨てたIDと省略の有無を返す。
- `ciel.research` のreliableデータパケットで、ヘッダー `research.result`、最大1500文字ずつの `research.text`、1出典ずつの `research.source`、完了通知 `research.complete` を送る。日本語・絵文字でも各パケットを小さく保つ。画面への通知は最大3秒で打ち切り、通知の失敗で検索結果を失敗にはしない。
- Unityの `CielConversation` は最大20件を受け取り、切断時に消す。`CielConversationUI` に「調査・出典」のボタンを追加し、質問・取得日時・本文・番号付きの出典リンクを表示する。リンクはHTTP(S)のみ、タップ時に外部ブラウザーで開く。外部テキストのリッチテキスト解釈は無効。過去の記録を `read_research` で読むと画面にも再送する。
- アプリ側も更新が必要。古いアプリは新しいデータパケットを表示しない。

## 検証と反映

- サーバーの自動テストは `server/agent` で `python -m unittest discover -s tests -q`。外部API・DB・Discordはモック化し、41件が成功した。検索必須・送信範囲・引用検証・保持上限・発言との対応・再参照・同時実行・失敗・待機上限・キャンセル・UI送信失敗を確認する。
- 実接続テスト：本番コンテナの別プロセスへメモリー内だけで今回のコードを読み込ませ、国立国会図書館の公式URLを確認する公開情報の検索を1件実行した。`completed`、引用出典2件を確認。サービス・ファイル・会話は変更していない。
- `dotnet build unity/Assembly-CSharp.csproj --no-restore` はエラーなし。UnityのJSON・画面統合確認用に `Ciel.EditorTools.CielResearchCheck.Run` を追加した（入力は `.local/research-check/packets.jsonl`、出力は同ディレクトリ）。エディターはライセンスのentitlement不足・初期化待ちで起動できず、この統合テストは未実施。実音声でのツール選択・待ち時間・割り込み・出典表示の実機確認も未実施。
- 本番サービスへの反映とアプリの配布は未実施。

## 「検索できない」と返す報告の調査（2026-10-18）

利用者がサーバーを配布したあと、シエルが「リサーチ」を頼まれてもできないと返すという報告があった。本番コンテナには `research_web`・`read_research` と検索の指示があり、ローカルとコードのハッシュが一致していた。本番と同じ指示・全15ツール・モデルで独立したRealtime接続を作り、「ウェブ検索はできる？」「ネットでリサーチはできる？」には可能と答え、「国立国会図書館の公式サイトをネットで検索して」「最近のAIニュースをリサーチして」では `research_web` を選ぶことを確認した。実際の会話での拒否は再現できておらず、これだけで原因が解消したとは判断しない。

検索できる能力を検索用プロンプトへ明記し、「リサーチして」を明示的な検索依頼へ追加した。検索ツールが呼ばれたかを会話本文なしで追えるよう、調査ID・開始/終了・成否・出典件数だけをINFOログへ追加した。また、運用ログに見つかった会話開始時の `AgentHandoff.role` のAttributeErrorを修正し、発言以外の通知を履歴収集から除外する回帰テストを追加した。この例外と検索拒否の因果関係は確認できていない。自動テスト42件成功。会話全文を新たに保存する機能は追加していない。

Unity統合テストを再実行するときは、リポジトリのルートで `python scripts/server/make-research-check-fixture.py` を実行して合成パケットを生成し、Unity 6000.6.4f1で `-projectPath unity -batchmode -nographics -executeMethod Ciel.EditorTools.CielResearchCheck.Run` を指定する。外部通信や実際のWebサイトを開く操作は行わない。

## 公式仕様

- [Realtimeのツール](https://developers.openai.com/api/docs/guides/realtime-mcp)
- [ResponsesのWeb検索・引用](https://developers.openai.com/api/docs/guides/tools-web-search)
- [GPT-5.4 miniの対応ツール](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
