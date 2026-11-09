# 会話サーバーを扱うエージェントへ

設計・実装の変更前に[現在の設計方針（正本）](../../docs/project/design-policy-ja.md)を参照する。方針を変えたら、正本と対応する契約・実装状況を同じ変更で更新する。

Minecraft のローカル LLM 試験・課題追加・性能比較は、[ベンチマークスキル](../../.agents/skills/ciel-minecraft-benchmark/SKILL.md)と [評価仕様](../../docs/games/minecraft/minecraft-benchmark-ja.md)を読む。実機は自宅サーバーの専用環境を使う。ローカルへの切替設定は [ローカル LLM](../../docs/operations/local-runtime-ja.md)。

会話の組み立て（pipeline：小脳と心・聞く係・付箋・口）を直す前に、[会話の組み立て（pipeline）の仕組み](../../docs/conversation/conversation-pipeline-ja.md) を読んでください。

プロンプトを編集・追加する前に、[プロンプト管理方針](../../docs/conversation/prompt-management-ja.md) と [編集手順](README.md) を読んでください。

- モデルに渡す本文は `config/prompts/*.md`、参照先は `config/persona.toml` で管理する。本文を Python や TOML へ埋め戻さない。
- 編集者向けのメモ・出典・変更理由はドキュメントに置く。Markdown の内容はそのままモデルへ渡る。
- 人物像、初回あいさつ、Irodori の感情タグの指示を分ける。感情タグ名を変える場合は `emotion.py` と読み上げ側の対応も確認する。
- 設定は会話開始時に読み込み、その会話内では固定する。プロンプト本文やユーザーの会話をログに出さない。
- 読み込み・パス解決・エラー処理を変更したらローカルで検証する。本文を変更したら代表的な会話で変更前後を比較し、未実施の確認は明記する。
- 本番への反映は確認済みの Git コミット単位で行う。編集・設定ファイルの変更だけで本番へ配布したことにはしない。

能力カタログ・道具の公開・MCPアダプターを変えたら、unit suiteに加えて `scripts/server/check-capability-runtime.py` で会話入口からの結合を確認する。実行方法は[回帰テスト](../../docs/testing/regression-tests-ja.md)。

モデルの道具・自発的処理・記憶保守を追加／変更するときは[サービス境界](../../docs/conversation/service-boundaries-ja.md)を読む。処理本体は共通MCP入口を使い、基盤専用操作をLLMのカタログへ自動公開しない。

サービス通知・接触・被ダメージ・コメント・歌への反応を変更する前に[サービス入力とリアクション](../../docs/conversation/service-events-and-reactions-ja.md)を読む。初版の実装と未検証範囲を確認する。入力調停を変えたらunit suiteと `scripts/server/check-reaction-runtime.py` を実行する。実機の反応速度は別に検証する。
