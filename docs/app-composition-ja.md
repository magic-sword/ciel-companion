# アプリ構成と配信出力

> 責務：Companion/Broadcastの共通Prefab・シーンと操作/配信出力の構成。

この資料はCompanion/Broadcastの製品構成、シーン・共通Prefab、出力先の違いを説明する。作業状態の意味・操作は[表示契約](work-display-contract-ja.md)、ビルド手順は[ビルド](build-ja.md)が正本。

## 製品と共通実装

日常版とWindows配信版は一つのUnityプロジェクトと`CielRuntime.prefab`を共用する。`Conversation.unity`と`Broadcast.unity`、アプリプロファイル、ビルドの入口を分離し、Runtimeへ接続・音声・モデルの処理を重複配置しない。接続先、音声機器、会話モード等は端末のPlayerPrefsで管理し、製品間の保存先を区別する。

## 操作画面と出力

操作画面は接続、会話、話者、歌、調査、作業の状態を表示する。設定・停止・再試行は対象の現在状態と権限を確認する。未確認を接続済み・停止済みへ読み替えない。

配信用のモデル映像、重畳表示、独立した状態カードを別の出力として扱う。独立カードは表示だけの出力で、会話接続・音声・モデルをもう一つ起動しない。専用カメラとレイヤーでメイン映像から分離し、音声リスナーを追加しない。

作業と会話・リアクションを並行して示す。旧段一覧から0/0を作らず、確認済み状態と残り実行予算を共通の`CielWorkPresentation`から描画する。配信出力へ依頼者の個人名・記憶・内部ログを載せない。機能の詳細は[表示契約](work-display-contract-ja.md)へ集約する。

## 検証

`CielAppCompositionCheck`でシーンと共通構成、`CielStreamStatusCheck`で状態通知と重畳表示、`CielAudienceCardCheck`で独立カードを確認する。Unityのライセンス・起動権限の切り分けとC#検証器は[回帰テスト](regression-tests-ja.md)。Editor描画とWindows/Android実機・配布済みアプリの確認は分け、[確認状況](verification-status-ja.md)を更新する。
