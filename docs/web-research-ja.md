# Web調査

> 責務：Web調査の依頼、引用確認、結果保持、画面と発話への対応。

この資料はWeb調査の依頼・結果・保持・画面への通知を説明する。サービス境界は[サービス境界](service-boundaries-ja.md)、権限と段階的公開は[能力カタログ](capability-runtime-ja.md)を参照する。

`ResearchService`と`WebResearcher`を、利用者の依頼と自発的調査の両方から共通MCP入口で利用する。質問・必要な日時を送り、会話全文・人物メモ・資格情報をLLMの任意引数へ出さない。モデルと接続先の設定は`models.py`と`web_research.py`を正本とする。

同じ会話の同時検索数、処理期限、本文・出典の保持量を制限する。結果の本文と有効な引用、検索処理の完了を確認してから調査済みと扱う。失敗・取消・期限切れを架空の回答で補わない。localモードの公開Web調査は現在利用不可で、OpenAIへ自動で戻らない。

調査の受付、実行中の表示、共通履歴への記録、結果の発話はホストが担当する。完了通知は[サービス入力](service-events-and-reactions-ja.md)からMouthへ渡し、発話済みと生成完了を混同しない。モデル・検索・引用の費用と、ローカルの実行試験は[有料試験](paid-checks-ja.md)で区別する。

テストは`server/agent/tests/test_research.py`、サービス境界とpipelineの結合は[回帰テスト](regression-tests-ja.md)を参照する。
