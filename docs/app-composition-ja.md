# 日常版と配信用Windows版の構成

2026-11-08。Unityプロジェクトを共有し、起動シーンと配信向けの画面を分ける。

| 製品 | 起動シーン | 設定アセット | Windows出力 |
|---|---|---|---|
| CIEL Companion | `Assets/Scenes/Conversation.unity` | `CompanionApp.asset` | `Builds/Windows/CIEL Companion.exe` |
| CIEL Broadcast | `Assets/Scenes/Broadcast.unity` | `BroadcastApp.asset` | `Builds/Broadcast/CIEL Broadcast.exe` |

Androidは日常版のシーンを使う。共通のシエル、カメラ、会話接続、表情、音声、タッチの参照は `Assets/Prefabs/CielRuntime.prefab` に置く。両方のシーンは同じPrefabを参照し、モデルや通信コードをコピーしない。各シーンの `CielAppComposition` が、`CielAppProfile` を見て操作画面と必要な配信出力を組み立てる。日常版でもWindows版を作れる。

画面の部品・状態の解釈・アプリの道具も共有する。日常版はモデルに触れて会話する画面。配信版は不透明な操作画面に目的・現在の処理を並べ、同じプロセスの別ウィンドウ「CIEL Broadcast 映像」にシエルを出す。会話接続、マイク、音声受信、モデルはそれぞれ1つ。配信映像へ目的・処理の札を重ねる機能は配信設定から任意に有効にする（初期値はオフ）。詳細な処理状態は操作画面に常時表示する。

配信専用の操作画面は `CielConversationUI.Broadcast.cs`、映像に重ねる札は `CielConversationUI.BroadcastOutput.cs`。日常版の目的パネルは `CielConversationUI.Goal.cs`。Windows固有の映像ウィンドウは `CielStreamWindow.cs` が担当し、日常版のUIからは生成しない。

日常版には配信設定ページを作らず、以前保存したYouTubeのオン状態も読み込まない。配信版の製品名は `CIEL Broadcast` とし、UnityのPlayerPrefs保存先を日常版から分ける。既存の日常版の設定は残る。配信版の初回は、マイク・音量・会話モード・配信URLなどを設定する。旧アプリの設定を一括コピーする移行は行わない。

## 編集とビルド

共通のモデル・カメラ・会話部品は `CielRuntime.prefab` を編集する。片方のシーンでPrefabの上書きを足すと共有から外れるので、製品差は起動設定アセットまたは画面構築コードへ置く。起動設定ではWindowsの初期サイズ、映像ウィンドウの初回自動表示、映像への状態表示の初期値を変えられる。

`CIEL/Apps/Create Shared Runtime and App Scenes` は既存の会話シーンから共通Prefabを一度だけ作り、2つの起動シーンを再生成する。既存のPrefabと設定アセットは再生成で上書きしない。`CielConversationSetup.Run` でモデルから会話シーンを新規作成した場合は、そのシーンを共通Prefabへ取り込み直す。通常のモデル更新では、モデルのPrefabと共通Runtimeの参照を更新する。

`CIEL/Build/Windows`、`CIEL/Build/Windows Broadcast`、`CIEL/Build/Android` を使う。コマンド用の `CielBuild.WindowsAll` は日常版・配信版のWindowsビルドを順に作る。ビルド後はプロジェクトの製品名を元に戻す。

## 確認

`Ciel.EditorTools.CielAppCompositionCheck.Run` は接続せずに、両方のシーンが同じRuntimeを持つこと、モデル・会話接続が1つであること、口・表情の参照、配信設定と出力の所属、画面構築を確認する。グラフィックスを有効にしたUnityでは `.local/app-refactor/` に画面画像も出す。前回の配信札の回帰確認 `CielStreamStatusCheck.Run` も実行する。

配信用の映像ウィンドウは既存のWindowsネイティブ出力を使う。OBSではウィンドウキャプチャを選ぶ。別のGPU共有方式や透過出力への変更は今回の分離に含めない。

スマホと配信版を同時起動しても、現在はそれぞれ別の会話になる。同じ会話をスマホから操作する機能は追加していない。
