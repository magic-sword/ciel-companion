# CIEL Companion

Live2Dキャラクターと日本語で音声会話するスマートフォンアプリ。要件は [仕様書](docs/specification-ja.md)、原画・パーツ・モデル制作は [Live2Dモデル制作仕様書](docs/ciel-live2d-production-spec-ja.md) を参照してください。

制作基準は [シエル外観参考](docs/assets/ciel/ciel-approved-appearance-v1.png) と [承認済みの閉眼デザイン](docs/assets/ciel/production/ciel-eye-appearance-study-v1.png) です。控えめな鼻と、滑らかな白磁の肌を維持します。画像編集はGIMP 3.2.6を使用します。

動作確認の入口は [表情プレビュー](docs/assets/ciel/production/ciel-gaze-preview.html) に統一しています。視線17段階・瞬き33段階・口の開閉33段階を組み合わせられます。[瞬きの比較](docs/assets/ciel/production/ciel-approved-eye-motion-v1-comparison.png)、[視線・瞬き・開口の比較](docs/assets/ciel/production/ciel-approved-eye-motion-v1-combined-comparison.png) も参照できます。現在は280×195pxの素材とソフトウェア描画の試作です。高解像度原画、現行素材のCubismリグ、Unityでの表示検証は未完了です。

現在は [目のない顔下地＋独立した目パーツ](docs/ciel-live2d-production-spec-ja.md#16-目のない顔の下地と独立した目パーツ最新方針再開位置) へ移行中です。下地を仕上げた後、片目のパーツをCubismで変形して検証します。新構成の編集原稿は作成済みですが、外観・リグは未完成で、プレビューへの反映前です。2026-10-08に高解像度の基準画像（素材v2）へ切り替えました。新しいセッションは制作仕様書の[第17節](docs/ciel-live2d-production-spec-ja.md#17-高解像度の基準画像と生成パーツ素材v22026-10-08)から再開してください。

素材とプレビュー画像は次のコマンドで再生成できます。

```powershell
.\scripts\build-ciel-approved-eyes.ps1 -Publish
```

`-Publish` は生成・検証した画像と記録を、このリポジトリの資料フォルダへコピーします。省略時はGit除外の `assets/private/ciel/live2d/gimp/` 内だけを更新します。インターネットへの公開は行いません。入力・出力と検証手順は [制作仕様書の現行工程](docs/ciel-live2d-production-spec-ja.md#12-現行の制作工程2026-10-06)、素材分離と品質判断の根拠は [Live2D公式資料調査](docs/live2d-rigging-best-practices-ja.md) にまとめています。

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

現在はUnity開発基盤とLive2D・LiveKit SDKの導入までです。Mainは空のシーンです。
会話UI、サーバー、Seed-VC、シエルのモデルはまだ組み込んでいません。
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

LiveKitの接続設定は `Assets/Settings/LiveKitTokenSource.asset` です。
Inspectorの **Endpoint URL** に、短期トークンを返すサーバーのURLを指定します。
現在は空欄で、自動接続・録音する処理はありません。トークン取得やRoom接続を呼び出す
会話処理は次の実装段階です。API secretや長期トークンをこのアセットへ保存しないでください。

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
Android実機ビルド・iOSビルド・音声会話は未検証です。

確認済み: CLIでのプロジェクト作成、Pipelineを含むスクリプトコンパイル、設定スクリプトの
バッチ実行（終了コード0）、URP設定、Mainシーン登録、Android Build Supportの認識。
検証ログはGit除外の `unity/Logs/setup.log` に出力します。

## 公式資料

- [Unity CLI](https://docs.unity.com/en-us/unity-cli/unity-cli-reference)
- [Unityリリースとサポート](https://unity.com/releases/unity-6/support)
- [Live2DのURP導入手順](https://docs.live2d.com/en/cubism-sdk-tutorials/urp-import/)
- [LiveKit Unity SDK](https://github.com/livekit/client-sdk-unity)
