# Web調査

> 責務：Web調査の依頼、引用確認、結果保持、画面と発話への対応。

検索は`server/search`の独立した認証付きMCPサービスが担当する。CIELの`ResearchService`は接続・結果検証・会話用の整形だけを行い、`WebResearcher`が受付・取消・記録・画面通知を管理する。利用者の依頼と自発的調査は同じ入口を使う。[サービス境界](../conversation/service-boundaries-ja.md)と[能力カタログ](../conversation/capability-runtime-ja.md)を参照。

LLMが呼ぶ`research_web`と段階的ロードは維持する。サービスへ渡すのは短い検索語と件数だけで、会話全文・人物メモ・外部APIキーは渡さない。検索サービスの交換でLLMの道具定義を変更しない。現在の実装はWikipedia APIだけで、OpenAI・Geminiのアダプターや記事本文の巡回は未実装。別プロバイダーへの自動フォールバックはない。

## 独立MCPの契約

Streamable HTTPの`/mcp`にBearer認証し、`search(query, limit=3)`を呼ぶ。queryは1～600文字、limitは1～5。応答は`version=1`、`status`、`coverage`（検索範囲）、`content_kind`、`retrieved_at`、`results`、任意の`summary`・`reason`・`retry_after_seconds`からなる。各結果はtitle・url・snippet・attributionと任意のlicense_url・history_urlを持つ。

`status`はok / no_results / unavailable / rate_limited / failed。成功は出典必須、結果なしと障害を区別する。`content_kind=search_snippets`は取得した検索概要、`grounded_summary`は出典番号`[n]`付き生成要約。後者は将来のアダプター用の契約であり、現プロバイダーは生成しない。検索範囲と証拠の種類を会話へ返し、概要を記事本文やWeb全体の確認と扱わない。検索結果は外部資料として扱う。

契約の正本は`server/search/contract.py`。その`SearchReply.model_json_schema()`をJSON化したものが`server/agent/config/search-api.schema.json`で、実HTTPテストが両者の一致を検査する。破損応答・未知の版・出典不足をクライアントで拒否し、内部例外や資格情報を結果へ含めない。会話の結果形式・画面通知は既存のまま。

検索サービス内で要求を直列化し、429・負荷エラーの待機を全接続で共有する。Retry-Afterまたは最低60秒の待機中は追加要求を送らず、自動再試行しない。サービス30秒・会話45秒で打ち切り、取消はMCPセッション終了から検索HTTPへ伝播する。セッションは最大64・無操作90秒、要求bodyは16KiBまで。

## 設定と起動

資格情報は本番`server/.env.shared`の`CIEL_SEARCH_TOKEN`（ランダムASCII32文字以上）。各環境の`server/search/.env`は`SEARCH_CONTACT`（公開連絡先）、`SEARCH_SOURCE=wikipedia-ja`、`SEARCH_PORT`（本番8780・開発8781）。検索コンテナへ渡す資格情報はこのトークンだけで、共有ファイル全体を注入しない。CIEL側は`.env` / `.env.dev`の`CIEL_SEARCH_URL`と共有トークンだけを使う。[環境設定](../operations/local-runtime-ja.md)を参照。

Linuxホストの`server/search`で起動する。

```sh
# 本番
 docker compose --env-file ../.env.shared --env-file .env up -d --build
# 開発（共有資格情報は本番に一つ）
 docker compose -p ciel-search-dev --env-file ../../../ciel-companion/server/.env.shared --env-file .env up -d --build
```

127.0.0.1だけで待ち受ける。`GET /health`は資格情報なしで稼働・API版を返すが、外部検索の可用性までは保証しない。`/mcp`は認証必須。これは同一ホストの信頼されたクライアント向け共有トークン方式で、公開インターネット向けOAuthサービスではない。別ホストへ公開する場合はTLS・到達制限・認証方式を別途設計する。CIELと独立にビルド・再起動できる。

## 許可を確認した検索APIの収集スクリプト

`scripts/server/search-approved.py`も同じMCP APIを呼び、共通形式の結果を保存する。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/search-approved.py "Python" --limit 3 --output .local/approved-search/result.json
```

既定の接続先は`server/.env`、資格情報は`server/.env.shared`。開発は`--env-file server/.env.dev`、資格情報の別配置は`--credentials-file`で指定する。プロセス環境変数を優先する。対象や連絡先をCLI・LLMから切り替えない。

収集本体は`server/search/approved_search.py`、許可台帳は`server/search/config/search-sources.json`。日本語・英語WikipediaのAction APIを登録し、稼働対象はサービス側で選ぶ。運営者が公開したAPIの条件を確認し、検索結果・概要だけを取得する。Google検索ページの直接取得はしない。APIキー・外部LLMは不要。

Wikimediaの[利用案内](https://www.mediawiki.org/wiki/API:Etiquette)と[API利用方針](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_API_Usage_Guidelines)を根拠に、識別名・公開連絡先入りUser-Agent、単発GET、maxlag=5、応答上限1MB、HTTP待機20秒を使う。記事本文・検索結果リンク・規約URLは自動取得せず、概要のHTMLを除去して最大1,200文字へ整形する。出典・Wikipedia contributorsの帰属・履歴URL・ライセンス参照を保持する。会話の記録と通知にも出典・帰属・ライセンス参照を渡す。

台帳には対象API・取得範囲・許可根拠URL・確認日・再確認期限を保存する。2027-02-15は自主的な再確認期限であり、運営者の許諾期限ではない。未登録・期限切れ・範囲違いは通信前に拒否し、リダイレクトも追わない。対象追加には台帳だけでなく接続先一覧とアダプターのレビューが必要。LLMに接続先追加や許可判定を任せず、robots.txtだけを許可根拠にしない。

独立APIの実HTTP試験は`server/search/tests/test_service.py`、収集のオフライン試験は`server/benchmark/tests/test_approved_search.py`、会話統合は`server/agent/tests/test_research.py`。[回帰テスト](../testing/regression-tests-ja.md)と[配布・確認状況](../testing/verification-status-ja.md)を参照。実マイク・TTS・端末画面の確認はAPI試験と分ける。

## GeminiのGoogle検索連携の接続試験

利用者の指定で`gemini-3.5-flash-lite`を試す。`scripts/server/probe-gemini-search.py`は本番を変更しない単発試験で、既存の`research.md`を使い、GoogleのgenerateContent APIへ`google_search`を指定する。モデル・接続先は固定し、既定1要求・最大3要求、出力1,600トークン、要求timeout45秒。エラー・上限・検索の根拠不足で停止し、再試行や別モデルへの切替は行わない。

APIキーは環境変数`GEMINI_API_KEY`またはGit対象外の`server/.env.shared`に設定する。Google検索連携は有料プランが必要。AI Studioで対象プロジェクトの課金設定と利用可能枠を確認し、有料API利用を了承したときに`--paid-usage-confirmed`を指定する。この引数は了承の記録であり、課金状態の検証やGoogle側の請求上限を設定する機能ではない。429だけでは課金設定の不備と利用枠の消費を区別できない。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/probe-gemini-search.py --check-config
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/probe-gemini-search.py --run --paid-usage-confirmed --limit 1 --output .local/gemini-search/next.json
```

指定モデルの応答・正常終了・検索語・出典URL・本文と出典の対応がそろうかを検査する。検索実施の証拠であり、回答の事実の正しさの採点ではない。生の応答、使用量、所要時間、指示とスクリプトのSHA-256を保存し、キーは保存・表示しない。Search Suggestionsも捨てずに保存する。製品への接続時はその表示と引用の要件を別途満たす必要がある。[Google検索連携の仕様](https://ai.google.dev/gemini-api/docs/generate-content/google-search)と[モデルの提供状況](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite)を参照する。実施状況は[確認状況](../testing/verification-status-ja.md)に記録する。
