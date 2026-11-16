# Web調査

> 責務：Web調査の依頼、引用確認、結果保持、画面と発話への対応。

この資料はWeb調査の依頼・結果・保持・画面への通知を説明する。サービス境界は[サービス境界](../conversation/service-boundaries-ja.md)、権限と段階的公開は[能力カタログ](../conversation/capability-runtime-ja.md)を参照する。

`ResearchService`と`WebResearcher`を、利用者の依頼と自発的調査の両方から共通MCP入口で利用する。質問・必要な日時を送り、会話全文・人物メモ・資格情報をLLMの任意引数へ出さない。モデルと接続先の設定は`models.py`と`web_research.py`を正本とする。

同じ会話の同時検索数、処理期限、本文・出典の保持量を制限する。結果の本文と有効な引用、検索処理の完了を確認してから調査済みと扱う。失敗・取消・期限切れを架空の回答で補わない。localモードの公開Web調査は現在利用不可で、OpenAIへ自動で戻らない。

調査の受付、実行中の表示、共通履歴への記録、結果の発話はホストが担当する。完了通知は[サービス入力](../conversation/service-events-and-reactions-ja.md)からMouthへ渡し、発話済みと生成完了を混同しない。モデル・検索・引用の費用と、ローカルの実行試験は[有料試験](../testing/paid-checks-ja.md)で区別する。

テストは`server/agent/tests/test_research.py`、サービス境界とpipelineの結合は[回帰テスト](../testing/regression-tests-ja.md)を参照する。

## GeminiのGoogle検索連携の接続試験

利用者の指定で`gemini-2.5-flash-lite`を試す。`scripts/server/probe-gemini-search.py`は本番を変更しない単発試験で、既存の`research.md`を使い、GoogleのgenerateContent APIへ`google_search`を指定する。モデル・接続先は固定し、既定1要求・最大3要求、出力1,600トークン、要求timeout45秒。エラー・上限・検索の根拠不足で停止し、再試行や別モデルへの切替は行わない。

APIキーは環境変数`GEMINI_API_KEY`またはGit対象外の`scripts/server/.env.local`に設定する。キーから課金プランは判別できないため、AI Studioで対象プロジェクトの無料プランと利用可能枠を確認してから`--free-tier-confirmed`を指定する。この引数は確認の記録であり、Google側の請求を強制的に止める機能ではない。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/probe-gemini-search.py --check-config
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/probe-gemini-search.py --run --free-tier-confirmed --limit 1 --output .local/gemini-search/first.json
```

指定モデルの応答・正常終了・検索語・出典URL・本文と出典の対応がそろうかを検査する。検索実施の証拠であり、回答の事実の正しさの採点ではない。生の応答、使用量、所要時間、指示とスクリプトのSHA-256を保存し、キーは保存・表示しない。Search Suggestionsも捨てずに保存する。製品への接続時はその表示と引用の要件を別途満たす必要がある。[Google検索連携の仕様](https://ai.google.dev/gemini-api/docs/generate-content/google-search)と[モデルの提供状況](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite)を参照する。実施状況は[確認状況](../testing/verification-status-ja.md)に記録する。
