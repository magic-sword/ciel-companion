# Live2D・LiveKit導入記録

日付: 2026-10-05（日本時間）

## 固定した配布物

- Unity: 6000.6.4f1、URP: 17.6.0
- Live2D: Cubism 5 SDK for Unity R5、URP版（正式版）
- 配布元: https://cubism.live2d.com/sdk-unity/bin/CubismSdkForUnity-5-r.5.unitypackage
- SHA-256: `C9AC920B3A7359DC9EBE4EC0E9AD3C50367D615BDAEBA3FC028141E90D45A0A1`
- LiveKit: `https://github.com/livekit/client-sdk-unity.git#v2.1.0`
- Git revision: `356bf5dfe079fd981cd514271b32d6cfe5d5516f`

LiveKitのネイティブライブラリ取得にはGit LFSが必要。
Unity Package Managerのlockファイルを管理対象とする。
Live2DにはCoreの独自ライセンス、オープンコンポーネントおよびサンプルの条件が付属する。
SDK内のライセンスと通知を保持する。アプリ公開時の条件は公開準備時に確認する。

## Unity 6.6との互換修正

R5の未修正版はUnity 6.6で廃止された `GetInstanceID()` 等によりコンパイルが失敗した。
Unityを下げず、以下のEditor用コードを修正した。

1. `CubismUnityEditorUtility.cs`: AssetDatabase.GetAssetPathへオブジェクトを直接渡す。
2. `CubismPoseMotionImporter.cs` と `CubismFadeMotionImporter.cs`: モーションイベントの
   整数識別子の取得を `CubismMotionEventId.Get` に置換（計5箇所）。
3. `Framework/CubismMotionEventId.cs`: Editor専用の互換処理を追加。

Cubismの `InstanceId` アニメーションイベントと `MotionInstanceIds` は整数の対応表であり、
Unityのネイティブオブジェクトハンドルとして逆引きしていない。
既存イベントの値を維持し、新しいクリップには使用済みの値を避けた整数を割り当てる。
Unityの64ビットEntityIdの切り捨てやハッシュ値による置換は行わない。
SDKの再インポート・更新時はこの修正の必要性を再評価する。

公開リポジトリではLive2D一式を追跡しない。
自作ヘルパーの原本を `scripts/cubism/CubismMotionEventId.cs` に保存し、
`scripts/repair-cubism.ps1` でSDKへコピーして上記6箇所を修正する。
`scripts/restore-cubism.ps1` は利用者が取得した公式配布物をハッシュ検証してローカル復元する。
確認シーンと接続設定も追跡せず、Configureコマンドで再生成する。

## 描画と接続の設定

- CubismURPRendererをプロジェクトのURPの既定Rendererへ追加。
- HDR無効・Gamma色空間。既存Renderer2Dは保持。
- 公式Koharuモデルの `SdkCheck` シーンを別途作成。本番ビルド対象にはしない。
- LiveKitの公式TokenSourceComponentConfigをEndpoint方式で作成。URLと認証情報は空欄。
- サーバーへの接続、マイク取得、トークン発行はこの導入検証では行わない。

## 検証方法

`CompanionSdkSetup.Configure` は設定後に次を確認する。

- Cubism CoreのネイティブDLLへのMOCバージョン問い合わせ。
- サンプルモデルのCubismModelとDrawableのインポート。
- LiveKit SDK自身のFFI初期化状態。未初期化ならSDKの初期化処理を呼ぶ。
- モーションイベントの既存ID保持と新規ID割り当て。

実機通信、Android/iOSビルド、マイクのエコーキャンセル、声の変換、シエルの表示は別途検証する。

2026-10-05実行結果: Unityバッチ終了コード0、`CIEL_SDK_OK` を確認。
Cubism CoreのMOC対応版は6、KoharuのDrawable数は91、LiveKit FFI初期化は成功。
画面の目視確認および実サーバー接続は未実施。
SDKには旧iOSシミュレーター構成などの非推奨API警告が残るが、コンパイルエラーはない。
