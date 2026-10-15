# アプリのビルド（Windows・Android）

更新：2026-10-15（日本時間）。

## Unity の標準との関係

ビルドそのものは Unity の標準の仕組み（`BuildPipeline.BuildPlayer`）で行う。File ＞ Build Profiles から手でビルドしてもよい。
このプロジェクトでは、それを決まった設定で呼ぶエディタ拡張 [`Assets/Editor/CielBuild.cs`](../unity/Assets/Editor/CielBuild.cs) を用意している。理由：

- ビルドに入れるシーン（`Assets/Scenes/Conversation.unity`）、出力先、プレイヤー設定を、誰がいつビルドしても同じにする。
- エディタを開かずに、コマンドからもビルドできるようにする。
- Android の権限（マイクなど）を自動で足す（下の「Android の権限」）。

| メニュー | 出力（Git 管理外） | 用途 |
|---|---|---|
| **CIEL ＞ Build ＞ Windows** | `unity/Builds/Windows/CIEL Companion.exe` | PC で使う。会議に OBS で取り込む（[会議への参加](meeting-bridge-ja.md)） |
| **CIEL ＞ Build ＞ Android** | `unity/Builds/Android/CIEL Companion.apk` | スマホで使う（開発用） |

**ビルドしたものはほかの人に配らない。** LiveKit の接続の設定（`Assets/Settings/LiveKitTokenSource.asset`、開発用トークンサーバーの ID）が入っている。

## 必要なもの

- Unity 6000.6.4f1（`unity/ProjectSettings/ProjectVersion.txt`）。
- Android は、Unity Hub でこの版に **Android Build Support**（OpenJDK・Android SDK & NDK Tools を含む）を入れておく。

## ビルドのしかた

### エディタから

メニューの **CIEL ＞ Build ＞ Windows** か **CIEL ＞ Build ＞ Android** を選ぶ。終わると Console に `CIEL_BUILD_OK: <出力先>` と出る。

- 選んだ側へ、ビルドの対象（Build Profile の有効なもの）が切り替わる。**対象を切り替えた最初のビルドは、素材の読み込み直しで時間がかかる**（数分〜十数分）。Windows と Android を交互にビルドすると毎回切り替わる。
- ビルドの間、エディタは操作できない。

### コマンドから（エディタを閉じて）

Git Bash で、リポジトリの `unity` フォルダから実行する（PowerShell では途中の `--` が正しく渡らない）。

```sh
# Windows
"/c/Program Files/Unity Hub/resources/unity.exe" --no-banner run . --timeout 1800 --log-file ./Logs/build-windows.log -- -executeMethod Ciel.Companion.Editor.CielBuild.Windows
# Android
"/c/Program Files/Unity Hub/resources/unity.exe" --no-banner run . --timeout 3000 --log-file ./Logs/build-android.log -- -executeMethod Ciel.Companion.Editor.CielBuild.Android
```

成功するとログに `CIEL_BUILD_OK`、失敗すると `CIEL_BUILD_FAILED` が出る。

### コマンドから（エディタを開いたまま）

開いているエディタのメニューを、Unity CLI から押せる。

```sh
"/c/Program Files/Unity Hub/resources/unity.exe" --no-banner command menu --path "CIEL/Build/Android" --detach
```

結果は `unity/Logs/Editor.log` の `CIEL_BUILD_OK` で確かめる。

## Windows

- ビルドのときに次のプレイヤー設定にする：前面でなくても動き続ける（Run In Background）、ウィンドウで開く、ウィンドウの大きさを変えられる。会議中に OBS やブラウザを操作しても会話が止まらないようにするため。
- 起動：`unity\Builds\Windows\CIEL Companion.exe` をダブルクリック。`CIEL Companion_Data` などのフォルダは exe と同じ場所に置いたままにする。
- 起動したままだとビルドで上書きできないので、ビルドの前に閉じる。
- アプリのログ：`%USERPROFILE%\AppData\LocalLow\CIEL\CIEL Companion\Player.log`
- `..._BackUpThisFolder_ButDontShipItWithYourGame` は不具合を調べるための情報で、配らない。

## Android

- 開発用の **APK** を作る（ストア用の AAB ではない）。署名は Unity の開発用の鍵。ストアに出すときは、別に署名の鍵を用意する。
- 設定：IL2CPP、ARM64、アプリの ID `com.ciel.companion`、最小 Android 8.0（API 26）、縦向き。
- 端末へ入れる：端末の「開発者向けオプション」で USB デバッグを有効にし、USB でつないで次を実行する（adb は Unity の Android モジュールに入っている）。
  ```sh
  "/c/app/unity/editor/6000.6.4f1/Editor/Data/PlaybackEngines/AndroidPlayer/SDK/platform-tools/adb.exe" install -r "Builds/Android/CIEL Companion.apk"
  ```
  APK を端末へコピーして、ファイルアプリから開いて入れてもよい（「提供元不明のアプリ」の許可が要る）。
- 初めてマイクボタンを押したとき、マイクの許可を求める画面が出る（LiveKit の PlatformAudio が出す）。許可しないと話せない。
- スマホでは、マイク・声の出力の選択欄は出ない（OS が切り替える）。会話のモードは「自動」なら 2 人になる。
- 端末のログ：`adb logcat -s Unity`

### Android の権限

`CielBuild.cs` の `CielAndroidPermissions` が、Unity が作る Android のプロジェクトの `AndroidManifest.xml` に次の権限を足す（ビルドの途中で自動）。

| 権限 | 理由 |
|---|---|
| `INTERNET` | LiveKit Cloud へつなぐ |
| `RECORD_AUDIO` | マイク |
| `MODIFY_AUDIO_SETTINGS` | WebRTC が通話用の音声の設定（エコー除去など）に切り替える |

2026-10-15 のビルドでは、この 3 つは Unity・LiveKit の側でもすでに入っていた（この処理は抜けたときの保険）。ほかに `CAMERA`・`BLUETOOTH` も入る（LiveKit SDK・Unity が足すもの。カメラは使っていないので、ストアに出す前に外すか検討する）。確かめ方：`aapt dump permissions "Builds/Android/CIEL Companion.apk"`（aapt は Android モジュールの `SDK/build-tools/<版>/` にある）。

手書きの `Assets/Plugins/Android/AndroidManifest.xml` は置かない。LiveKit のサンプルの手書きのものは古い起動の仕組み（UnityPlayerActivity）向けで、このプロジェクトが使う Unity 6 の GameActivity と食い違うため。

## 確かめたこと・まだのこと

- Windows：ビルド・起動・会話・仮想ケーブルへの出力を確認済み（2026-10-15）。
- Android：ビルドは確認済み（2026-10-15、APK 約 58 MB、arm64-v8a、API 26 以上、権限の宣言も確認）。**実機での起動・マイクの許可・会話は未確認。**
