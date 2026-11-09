# 資料一覧

更新：2026-11-08。[アプリの紹介へ戻る](../README.md)

現在の実装を知るには、まず構成・セットアップ・各機能の最新の検証記録を読む。設計書には提案や未実装の項目も含まれるため、冒頭の状態と検証章を確認する。「試験に通った」と「実機で動作確認した」は区別する。

## まず読む資料

| 目的 | 入口 |
|---|---|
| 何のアプリか知りたい | [トップREADME](../README.md) |
| 紹介動画を撮りたい | [撮影台本・OBSの収録手順](demo-recording-ja.md) |
| 自分の環境で始めたい | [開発環境構築](development-setup-ja.md) |
| 全体のつながりを知りたい | [システム構成](architecture-ja.md) |
| ビルド・サーバー反映をしたい | [コマンド集](build-ja.md) |
| 日常版と配信版の違いを知りたい | [アプリ構成・配信ウィンドウ](app-composition-ja.md) |
| 変更を検証したい | [回帰テスト](regression-tests-ja.md)、[料金のかかる試験](paid-checks-ja.md) |
| Minecraft をローカルモデルで試験・比較したい | [ローカル LLM](local-llm-ja.md)、[ベンチマーク・課題拡張・性能評価](minecraft-benchmark-ja.md)、[評価スキル](../.agents/skills/ciel-minecraft-benchmark/SKILL.md) |
| 利用条件・外部依存を確認したい | [第三者依存関係](third-party-dependencies.md)、[READMEのライセンス説明](../README.md#公開とライセンス) |

## 会話と記憶

| 資料 | 内容 |
|---|---|
| [pipelineの仕組み](conversation-pipeline-ja.md) | 現在の会話の流れと、変更時に守る境界 |
| [会話の改善と確認記録](conversation-improvements-2026-10-ja.md) | pipelineを採用した理由・測定結果 |
| [プロンプト編集](../server/agent/README.md) | キャラクター設定とMarkdownの編集・反映 |
| [人を覚える機能](people-memory-ja.md) | 同意、名前・呼び名・メモ、確認・削除 |
| [共有記憶](shared-memory-ja.md) | 接続をまたいだ記憶と同期 |
| [タッチ](ciel-touch-interaction-ja.md) | 頬などの操作と反応 |
| [会議への参加](meeting-bridge-ja.md) | 仮想オーディオ、OBS、複数人との会話 |
| [歌を聴く仕組み](singing-scoring-ja.md)、[使用モデル](singing-models-ja.md) | 分析・感想・採点の扱い |
| [YouTubeコメント](youtube-comments-design-ja.md) | 配信コメントの選別・返答・道具の制限 |
| [エラーの扱い](errors-design-ja.md) | 接続や処理の失敗の通知 |
| [ローカルLLM](local-llm-ja.md) | ローカル推論を使う構成 |

## ゲーム・視覚・目的

| 資料 | 内容 |
|---|---|
| [Minecraftの設計](minecraft-design-ja.md) | Java版の体、行動、接続、検証記録 |
| [環境のMCP設計](game-environment-mcp-design-ja.md) | ゲーム・アプリとの共通の接続。実装済み範囲と実ゲームでの未確認項目 |
| [目的の管理](goal-runner-design-ja.md) | 計画、実行、確認、修正、相談 |
| [体の作業の状態](body-command-lifecycle-ja.md) | 開始から完了・停止までの状態通知 |
| [ゲームの知識](game-knowledge-design-ja.md) | 物・制作方法・攻略知識の取得 |
| [視覚の設計](vision-design-ja.md)、[Minecraftの視覚](minecraft-vision-design-ja.md) | 景色の取得と理解 |

## キャラクター・Live2D制作

現在の制作方針は[作り直しの計画](ciel-live2d-rebuild-analysis-plan-ja.md)の6〜8章から読む。素材とモデルの入口は[assets/ciel](../assets/ciel/README.md)。

- [制作仕様](ciel-live2d-production-spec-ja.md)、[リグ設計](ciel-live2d-rig-design-ja.md)、[体・衣装](ciel-live2d-body-outfit-design-ja.md)
- [素材を依頼する手順](ciel-codex-request-guide-ja.md)、[パーツの相談資料](ciel-codex-consult-parts-ja.md)、[パーツの制約](ciel-design-constraints-for-parts-ja.md)
- [現行素材](../assets/ciel/current/README.md)、[作業リグ](../assets/ciel/rig/README.md)、[アプリ向けモデル](../assets/ciel/runtime/README.md)、[Minecraftスキン](../assets/minecraft/skins/README.md)
- [参考リグの分析](ciel-live2d-reference-rig-analysis-ja.md)、[素材制作の調査](ciel-live2d-material-guidelines-research-ja.md)、[リギングの調査](live2d-rigging-best-practices-ja.md)

## 研究・設計の背景

実装済み機能の一覧ではなく、比較・検討・採用理由を読むための資料。

- [聞く・考える・話す設計](attention-and-thinking-design-ja.md)、[自発的な発話の参考研究](inner-thoughts-research-ja.md)
- [長い目的の計画](long-horizon-planning-research-ja.md)、[シエルの成長](ciel-growth-research-ja.md)
- [話者識別](speaker-recognition-research-ja.md)、[歌の評価](singing-evaluation-research-ja.md)
- [決定記録の一覧](decisions/README.md)

## 初期仕様と過去の図

[初期仕様書](specification-ja.md)は2026-10-05時点の提案。Seed-VCを中心とした初期方針やiOSを含む目標が残っており、現在の実装状況には使わない。[旧システム構成図](system-overview-ja.svg)もRealtime経路を描いたもの。現在は[システム構成](architecture-ja.md)と[pipelineの仕組み](conversation-pipeline-ja.md)を参照する。

[開発環境構築図](development-setup-ja.svg)は導入順の補助資料。起動シーンや製品の違い、手順の更新は[文章のセットアップ手順](development-setup-ja.md)を優先する。
