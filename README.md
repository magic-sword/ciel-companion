# CIEL Companion

Live2Dキャラクターと日本語で音声会話するスマートフォンアプリ。
要件は [仕様書](docs/specification-ja.md) を参照してください。

## Unity開発環境

2026-10-05に公式CLIのリリース一覧で確認した最新正式版を使用しています。

| 項目 | バージョン・設定 |
|---|---|
| Unity Editor | 6000.6.4f1（Unity 6.6 Supported release） |
| テンプレート | Universal 2D 7.0.0 |
| Universal Render Pipeline | 17.6.0 |
| Unity Pipeline | 0.8.0-exp.1（CLIによるEditor操作用の実験版） |
| プロジェクト | `unity/` |
| アプリ表示名 | CIEL Companion |
| 画面 | 縦画面 |
| Android | IL2CPP / ARM64、Target APIはインストール済みの最高版を自動選択 |
| アプリID | `com.ciel.companion`（開発用。公開前に確定） |

Editorのバージョンは `ProjectSettings/ProjectVersion.txt`、パッケージの解決結果は
`Packages/packages-lock.json` で固定します。最新版への更新は互換性確認とセットで行います。
Androidの最低対応OSはテンプレートの既定値（API 26）を維持しており、検証端末決定後に確定します。

## 開く・操作する

Unity HubのProjectsからこのリポジトリの `unity` を開いてください。
一覧に出ない場合は **Add → Add project from disk** で `unity` を選択します。
メインシーンは `Assets/Scenes/Main.unity` です。

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

現在はUnity開発基盤です。Mainはテンプレート由来の空のシーンです。
Live2D Cubism SDK、LiveKit SDK、会話UI、サーバー、Seed-VCはまだ組み込んでいません。
Unity 6.6とそれらのSDKの組み合わせは今後の導入時に実機を含めて検証します。
Live2DのURP対応SDKとリギング済みモデルを導入し、表示・口パクから開発を進めます。
APIキーはUnityへ入れずサーバー側で管理します。

Android Build Support、SDK、NDK、OpenJDKはEditorとともにインストールしています。
Android実機ビルド・iOSビルド・音声会話は未検証です。

確認済み: CLIでのプロジェクト作成、Pipelineを含むスクリプトコンパイル、設定スクリプトの
バッチ実行（終了コード0）、URP設定、Mainシーン登録、Android Build Supportの認識。
検証ログはGit除外の `unity/Logs/setup.log` に出力します。

## 公式資料

- [Unity CLI](https://docs.unity.com/en-us/unity-cli/unity-cli-reference)
- [Unityリリースとサポート](https://unity.com/releases/unity-6/support)
- [Live2DのURP導入手順](https://docs.live2d.com/en/cubism-sdk-tutorials/urp-import/)
- [LiveKit Unity SDK](https://github.com/livekit/client-sdk-unity)
