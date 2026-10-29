# CIEL Companion

Live2Dキャラクターと日本語で音声会話するスマートフォンアプリ。要件は [仕様書](docs/specification-ja.md)、原画・パーツ・モデル制作は [Live2Dモデル制作仕様書](docs/ciel-live2d-production-spec-ja.md) を参照してください。

**新しく参加する人へ：[1枚で見るシステム構成と開発環境](docs/system-overview-ja.svg)** → [構成・API・設定の詳細](docs/architecture-ja.md)。SVGはブラウザーで開いて拡大できます。

**クローンしたら：[開発環境構築の図](docs/development-setup-ja.svg)** → [コマンドつきのセットアップ手順](docs/development-setup-ja.md)。Windows / VS Code、Codex・Claude Code の拡張、Live2D 復元、Unity の表示確認、音声接続、Python のテストを順に案内します。

**よく使うコマンド：[ビルド・サーバーデプロイのコマンド集](docs/build-ja.md)**（Git Bash 用。Windows / Android のビルド、APK のインストール、サーバーへの反映、状態・ログの確認）。

## キャラクター（シエル）のLive2D制作

制作の仕様は [Live2Dモデル制作仕様書](docs/ciel-live2d-production-spec-ja.md)、**現在の方針・手順・進み具合は [作り直しの計画](docs/ciel-live2d-rebuild-analysis-plan-ja.md) の 6〜8 章**にまとめています。新しく参加する人・新しいセッションは、まずこの 6〜8 章から読んでください。

- 外観の参考：[シエル外観参考](assets/ciel/reference/ciel-approved-appearance-v1.png)。控えめな鼻と、滑らかな白磁の肌を維持します。見た目の基準は承認済みの基準画像 `assets/ciel/master/ciel-upper-body-2x.png`（2172×2896px）です。
- 現在：素材とリグを作り直しています（2026-10-11〜）。素材は Codex が生成から組み立て・調整まで担当し、最新の素材は `assets/ciel/current/` にまとめています（作業モデルは `assets/ciel/rig/ciel.cmo3`）。Codex への素材の頼み方は `docs/ciel-codex-request-guide-ja.md`。
- 再生成できない素材（生成画像の原本、基準画像、採用した層と配置の記録）は Git で管理します。作業モデル（`.cmo3`）は Git LFS です。
- 作り直す前の方式（素材 v2〜v5、外部の 3D 計算による頭の向き）は削除しました。Git のタグ `archive/pre-v9-cleanup` で参照できます。さらに古い方式（280×195px 素材など）は `archive/pre-v2-cleanup` です。

## Unity開発環境

2026-10-05に公式CLIのリリース一覧で確認した最新正式版を使用しています。

| 項目 | バージョン・設定 |
|---|---|
| Unity Editor | 6000.6.4f1（Unity 6.6 Supported release） |
| テンプレート | Universal 2D 7.0.0 |
| Universal Render Pipeline | 17.6.0 |
| Unity Pipeline | 0.8.0-exp.1（CLIによるEditor操作用の実験版） |
| Live2D Cubism | 5 SDK R5（URP版、Unity 6.6互換修正あり） |
| LiveKit Unity SDK | 2.1.0（Gitタグとlockファイルで固定） |
| プロジェクト | `unity/` |
| アプリ表示名 | CIEL Companion |
| 画面 | 縦画面 |
| Android | IL2CPP / ARM64、Target APIはインストール済みの最高版を自動選択 |
| アプリID | `com.ciel.companion`（開発用。公開前に確定） |

Editorのバージョンは `ProjectSettings/ProjectVersion.txt`、パッケージの解決結果は
`Packages/packages-lock.json` で固定します。最新版への更新は互換性確認とセットで行います。
Androidの最低対応OSはテンプレートの既定値（API 26）を維持しており、検証端末決定後に確定します。

## 開く・操作する

新しくcloneした場合は、先に次節のLive2D復元を実行してください。SDKはGitに含めません。

Unity HubのProjectsからこのリポジトリの `unity` を開いてください。
一覧に出ない場合は **Add → Add project from disk** で `unity` を選択します。
会話アプリのシーンは `Assets/Scenes/Conversation.unity` です。SDK だけを確認する場合は、復元後に生成する `Assets/Scenes/SdkCheck.unity` を使います。初回は [セットアップ手順](docs/development-setup-ja.md) に沿って進めてください。

PowerShellではリポジトリのルートから次のコマンドを使用できます。
ラッパーはUnity CLIがPATHにない場合も、標準のUnity Hub同梱CLIを探します。

```powershell
.\scripts\unity.ps1 open .
.\scripts\unity.ps1 status
.\scripts\unity.ps1 recompile
```

設定を再適用する場合はEditorの **CIEL → Apply Project Defaults** を選択するか、
Editorを閉じて以下を実行してください。アプリ名、画面方向、ビルドシーン等を初期値へ戻します。

```powershell
.\scripts\unity.ps1 run . --timeout 600 --log-file ./Logs/setup.log -- -executeMethod Ciel.Companion.Editor.CompanionProjectSetup.Apply
```

## 実装状況

会話サーバーのプロンプト本文は Markdown、参照先は TOML で管理します。編集方法は [会話サーバーの README](server/agent/README.md)、他のセッション・AI エージェントへの引き継ぎは [プロンプト管理方針](docs/decisions/prompt-management-ja.md) を参照してください。

Windows・Android のビルドと起動・端末への入れ方、サーバーへのデプロイは [ビルド・サーバーデプロイのコマンド集](docs/build-ja.md) にまとめています。

全体の構成（アプリ・LiveKit・会話サーバー・読み上げ・OpenAI のつながり、データのメッセージ、動かす場所）は [システムの構成](docs/architecture-ja.md) にまとめています。

シエルを Zoom・Google Meet の会議に参加させて多人数で話す方法（仮想オーディオ・OBS の配線、Windows 用のビルド、会話のモード）は [会議への参加](docs/meeting-bridge-ja.md) を参照してください。

現在は、シエル（Live2D）の表示・タッチ・表情、OpenAI Realtime API と Irodori-TTS による音声会話、会議への参加、会話のしかた（おしゃべり度・その場にいる人）、声による話者の識別と、本人が同意した人の名前・メモの記憶まで動いています（Windows と Android で確認）。
シエルが人を覚えるしくみ（名前の覚え方、呼び名・人違いの直し方、メモの確認と削除、保存するもの）は [人を覚える機能の使い方](docs/people-memory-ja.md) にまとめています。
会議の議事録（とり方と Discord への下書きの送り方）は [議事録の決定記録](docs/decisions/meeting-minutes-ja.md) を参照してください。
シエルに歌を聴いてもらう機能（ときめき度・感想の決まり方、図つき）は [シエルが歌を聴く仕組み](docs/singing-scoring-ja.md)、決めたことは [歌を聴く決定記録](docs/decisions/singing-ja.md) にまとめています。
シエルが自分から話しかけるしくみ（内なる考え）の発想の原点と参考にした研究は [内なる考えの参考文献と設計の原点](docs/inner-thoughts-research-ja.md)、決めたことと試した結果は [決定記録](docs/decisions/inner-thoughts-ja.md) にまとめています。
APIキーはUnityへ入れずサーバー側で管理します。

## Live2D・LiveKit

### clone後のLive2D復元

1. [Live2D公式サイト](https://www.live2d.com/en/sdk/download/unity/)で利用条件を確認し、
   **Cubism SDK for Unity R5（URP）** をダウンロードします。
2. Unityを閉じた状態で、リポジトリのルートから実行します。

```powershell
.\scripts\restore-cubism.ps1 -PackagePath 'C:\path\to\CubismSdkForUnity-5-r.5.unitypackage'
```

スクリプトは配布物のSHA-256を確認し、SDKと元の.metaを復元してUnity 6.6互換修正を適用します。
SDKのライセンス・通知はローカルに保持します。別バージョンは誤って適用しないよう拒否します。
Windows付属のtarを使用します。LiveKitの復元にはGit LFSもインストールしてください。

3. Unityを開き、パッケージ読み込み後に **CIEL → SDK → Configure and Validate** を実行します。
   以下の確認シーンと接続設定がローカルに生成されます。

Live2Dの確認用シーンは `Assets/Scenes/SdkCheck.unity` です。
公式サンプルKoharuを配置しています。シエルのモデルではなくSDK確認用で、アプリの
ビルドシーンには追加していません。Editorでこのシーンを開いてPlayで確認できます。
プロジェクトのURPではCubismURPRendererを既定にし、公式手順に合わせてHDRを無効、
Color SpaceをGammaに設定しています。従来の2D Rendererはリストに残しています。

LiveKitの接続設定は `Assets/Settings/LiveKitTokenSource.asset` です。初回生成時は Endpoint が選択され、接続先は空欄です。
既存の開発環境を使う場合は、Inspector の **Token Source Type** を **Development Token Server** にし、管理者から共有された **Token Server Id** を設定します。独自の取得先を使う場合は **Endpoint** と **Endpoint URL** を設定します。
`Conversation.unity` は再生時に接続を試みます。接続設定の参照とマイクの確認は [音声会話の初期設定](docs/development-setup-ja.md#7-音声会話を試す場合) を参照してください。API secretや長期トークンをこのアセットへ保存しないでください。

再設定・導入検証は **CIEL → SDK → Configure and Validate** から行えます。
Editorを閉じている場合は次のコマンドでも実行できます。

```powershell
.\scripts\unity.ps1 run . --timeout 900 --log-file ./Logs/sdk-setup.log -- -executeMethod Ciel.Companion.Editor.CompanionSdkSetup.Configure
```

Live2DはGit除外の `Assets/Live2D` に公式SDKを展開し、同梱ライセンス・通知を保持しています。
入手元は [公式ダウンロード](https://www.live2d.com/en/sdk/download/unity/) のURP R5です。
SDK更新で上書きする前に、[互換修正記録](docs/decisions/sdk-setup.md)を確認してください。

## ソース公開とライセンス

自作コードをOSSとして公開する予定ですが、現時点ではプロジェクト自身のLICENSEは未選定です。
ライセンスを決定・追加するまでは、公開しただけで第三者へOSSとしての利用許諾を与えたことにはなりません。
Live2Dは独自ライセンスの外部依存であり、本プロジェクトのライセンスの適用対象に含めません。
SDK一式・サンプル・確認シーン・接続設定はGit除外し、復元スクリプトと自作の互換処理を管理します。
LiveKitはmanifest/lockから取得します。[第三者依存関係](docs/third-party-dependencies.md)も参照してください。

Android Build Support、SDK、NDK、OpenJDKはEditorとともにインストールしています。
Android の実機ビルドと音声会話は確認済み（2026-10-16、[アプリのビルド](docs/build-ja.md)）。iOS ビルドは未検証です。

確認済み: CLIでのプロジェクト作成、Pipelineを含むスクリプトコンパイル、設定スクリプトの
バッチ実行（終了コード0）、URP設定、Mainシーン登録、Android Build Supportの認識。
検証ログはGit除外の `unity/Logs/setup.log` に出力します。

## 公式資料

サーバーの改修時は[回帰テスト](docs/regression-tests-ja.md)を実行してください。通常テストと使い捨てDBの結合テストを、Git管理のスクリプトから実行できます。

- [Unity CLI](https://docs.unity.com/en-us/unity-cli/unity-cli-reference)
- [Unityリリースとサポート](https://unity.com/releases/unity-6/support)
- [Live2DのURP導入手順](https://docs.live2d.com/en/cubism-sdk-tutorials/urp-import/)
- [LiveKit Unity SDK](https://github.com/livekit/client-sdk-unity)
