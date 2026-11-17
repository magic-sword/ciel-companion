# Web調査

> 責務：Web調査の依頼、引用確認、結果保持、画面と発話への対応。

この資料はWeb調査の依頼・結果・保持・画面への通知を説明する。サービス境界は[サービス境界](../conversation/service-boundaries-ja.md)、権限と段階的公開は[能力カタログ](../conversation/capability-runtime-ja.md)を参照する。

`ResearchService`と`WebResearcher`を、利用者の依頼と自発的調査の両方から共通MCP入口で利用する。質問・必要な日時を送り、会話全文・人物メモ・資格情報をLLMの任意引数へ出さない。検索処理は`approved_search.py`、許可台帳は`config/search-sources.json`を正本とする。検索にOpenAI・Geminiは使用せず、検索結果は会話モデルへ返す。

同じ会話の同時検索数、処理期限、本文・出典の保持量を制限する。結果の本文と有効な引用、検索処理の完了を確認してから調査済みと扱う。失敗・取消・期限切れを架空の回答で補わない。local・openaiのどちらの会話backendでも同じ許可済みAPIを使い、別プロバイダーへのフォールバックはない。

調査の受付、実行中の表示、共通履歴への記録、結果の発話はホストが担当する。完了通知は[サービス入力](../conversation/service-events-and-reactions-ja.md)からMouthへ渡し、発話済みと生成完了を混同しない。モデル・検索・引用の費用と、ローカルの実行試験は[有料試験](../testing/paid-checks-ja.md)で区別する。

テストは`server/agent/tests/test_research.py`、サービス境界とpipelineの結合は[回帰テスト](../testing/regression-tests-ja.md)を参照する。

## 許可を確認した検索APIの収集スクリプト

`scripts/server/search-approved.py`は、運営者が公開したAPIの利用条件を確認して登録した接続先だけを検索し、タイトル・URL・検索概要をJSONへ保存する。初期対象は日本語・英語WikipediaのAction APIであり、Web全体の検索ではない。Google検索ページの直接取得は行わない。APIキーや外部LLMは不要。会話の`research_web`も同じ収集処理を使い、日本語Wikipediaに固定して最大3件を検索する。短い検索語を渡し、検索概要・出典・CC BY-SA 4.0の参照を既存の調査記録・画面通知へ載せる。空結果は検索済みで該当なし、API失敗はfailedとして区別する。配布状況は確認状況を参照。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/search-approved.py --list-sources
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/search-approved.py "Python" --source wikipedia-ja --limit 5 --contact "<公開してよい実際の連絡先URLまたはメール>" --output .local/approved-search/result.json
```

公開連絡先は`server/.env`の`CIEL_SEARCH_CONTACT`にも設定できる。優先順位と開発用ファイルは[実行設定](../operations/local-runtime-ja.md#本番開発で共通の変数名)を参照。`--contact`は運営者へのUser-Agentに送る公開連絡先。APIキーや秘密情報を指定しない。Wikimediaの[利用案内](https://www.mediawiki.org/wiki/API:Etiquette)と[API利用方針](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_API_Usage_Guidelines)に従い、専用の識別名、単発のGET、`maxlag=5`を使う。1実行1要求・最大10結果・応答上限1MB・HTTP待ち時間20秒で、再試行やページ送りはしない。複数プロセスの一括実行や定期巡回は対象外。429やAPI負荷エラーでは停止し、`Retry-After`を結果に残す。再実行は待機指示に従う。

許可台帳は`server/agent/config/search-sources.json`。対象API、取得範囲、許可の根拠URL、確認日と再確認期限、利用規約・ライセンスの参照先を保存する。2027-02-15はこの実装の自主的な再確認期限で、運営者が保証する許諾期限ではない。条件の変更を検知した場合は期限前でも見直す。台帳を追加するだけでは接続できず、コード側の接続先一覧とAPIアダプターもレビューして更新する。LLMに接続先の追加・許可判定を任せない。`robots.txt`だけを許可根拠にしない。

未登録・期限切れ・範囲違いは通信前に拒否し、HTTPリダイレクトも追わない。検索結果のリンクや、利用条件の参照URLをスクリプトが取得することはない。`content_kind=search_snippets`、`pages_fetched=false`、`untrusted_content=true`をJSONへ付ける。取得した文章は外部資料であり、実行指示として扱わない。概要はHTMLを除去して最大1,200文字に整形し、記事・履歴URL、Wikipedia contributorsの帰属、ライセンス参照を残す。公開・加工時には対象コンテンツの利用条件に従う。会話モデルはこの概要を受け取って返答する。記事本文やWeb全体を確認したとは扱わない。会話側のHTTPは非同期で、取消時は接続を閉じる。同一プロセスの検索を直列化し、429・負荷エラーではRetry-After（指定なしは60秒）まで追加要求を抑止する。

オフライン試験は`server/benchmark/tests/test_approved_search.py`。実APIでの確認範囲は[確認状況](../testing/verification-status-ja.md)を参照する。

## GeminiのGoogle検索連携の接続試験

利用者の指定で`gemini-3.5-flash-lite`を試す。`scripts/server/probe-gemini-search.py`は本番を変更しない単発試験で、既存の`research.md`を使い、GoogleのgenerateContent APIへ`google_search`を指定する。モデル・接続先は固定し、既定1要求・最大3要求、出力1,600トークン、要求timeout45秒。エラー・上限・検索の根拠不足で停止し、再試行や別モデルへの切替は行わない。

APIキーは環境変数`GEMINI_API_KEY`またはGit対象外の`server/.env.shared`に設定する。Google検索連携は有料プランが必要。AI Studioで対象プロジェクトの課金設定と利用可能枠を確認し、有料API利用を了承したときに`--paid-usage-confirmed`を指定する。この引数は了承の記録であり、課金状態の検証やGoogle側の請求上限を設定する機能ではない。429だけでは課金設定の不備と利用枠の消費を区別できない。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/probe-gemini-search.py --check-config
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/probe-gemini-search.py --run --paid-usage-confirmed --limit 1 --output .local/gemini-search/next.json
```

指定モデルの応答・正常終了・検索語・出典URL・本文と出典の対応がそろうかを検査する。検索実施の証拠であり、回答の事実の正しさの採点ではない。生の応答、使用量、所要時間、指示とスクリプトのSHA-256を保存し、キーは保存・表示しない。Search Suggestionsも捨てずに保存する。製品への接続時はその表示と引用の要件を別途満たす必要がある。[Google検索連携の仕様](https://ai.google.dev/gemini-api/docs/generate-content/google-search)と[モデルの提供状況](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite)を参照する。実施状況は[確認状況](../testing/verification-status-ja.md)に記録する。
