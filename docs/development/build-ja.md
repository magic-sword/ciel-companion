# ビルド・サーバーデプロイのコマンド集

> 責務：アプリのビルド、配置、更新、ログ取得の操作。

更新：2026-11-08（日本時間）。コマンドは **Git Bash** 用。

## まずここから

ターミナルでリポジトリのルート（`ciel-companion/`）を開く。ビルドだけは、そこから `cd unity` で移動して実行する。

| やりたいこと | 実行する場所 | 手順 |
|---|---|---|
| Windows / Android をビルドする | 手元の `unity/` | [ビルドのコマンド](#コマンドからエディタを閉じて) |
| Unity を開いたままビルドする | 手元の `unity/` | [メニューをコマンドで実行](#コマンドからエディタを開いたまま) |
| Windows アプリを起動する | 手元のリポジトリルート | `"./unity/Builds/Windows/CIEL Companion.exe"` |
| 配信版を起動する | 手元のリポジトリルート | `"./unity/Builds/Broadcast/CIEL Broadcast.exe"` |
| Android 端末に APK を入れる | 手元の `unity/` | [Android](#android) |
| サーバーへデプロイする | 手元のリポジトリルート | `bash scripts/server/deploy-server.sh`（[前提と確認方法](#サーバーへのデプロイ)） |
| サーバーの状態・ログを見る | SSH 接続先の `~/work/ciel-companion/server` | [デプロイ後の確認・再起動](#デプロイ後の確認再起動) |

Unity 側の変更はアプリをビルドし直し、`server/` 側の変更はサーバーへデプロイする。両方を変更したときは両方を行う。

## Unity の標準との関係

ビルドそのものは Unity の標準の仕組み（`BuildPipeline.BuildPlayer`）で行う。File ＞ Build Profiles から手でビルドしてもよい。
このプロジェクトでは、それを決まった設定で呼ぶエディタ拡張 [`Assets/Editor/CielBuild.cs`](../../unity/Assets/Editor/CielBuild.cs) を用意している。理由：

- ビルドに入れるシーン（日常版は`Conversation.unity`、配信版は`Broadcast.unity`）、出力先、プレイヤー設定を、誰がいつビルドしても同じにする。
- エディタを開かずに、コマンドからもビルドできるようにする。
- Android の権限（マイクなど）を自動で足す（下の「Android の権限」）。

日常版と配信用Windows版は同じUnityプロジェクトから作る。共通のRuntime Prefabと起動シーンの構成は [アプリの構成](../app/app-composition-ja.md) を参照。配信版は `CIEL ＞ Build ＞ Windows Broadcast`（`Ciel.Companion.Editor.CielBuild.WindowsBroadcast`）で `unity/Builds/Broadcast/CIEL Broadcast.exe` に出力する。日常版・配信版をまとめて作る場合は `Ciel.Companion.Editor.CielBuild.WindowsAll`。Androidは日常版を作る。

| メニュー | 出力（Git 管理外） | 用途 |
|---|---|---|
| **CIEL ＞ Build ＞ Windows** | `unity/Builds/Windows/CIEL Companion.exe` | PC で使う。会議に OBS で取り込む（[会議への参加](../services/meeting-bridge-ja.md)） |
| **CIEL ＞ Build ＞ Windows Broadcast** | `unity/Builds/Broadcast/CIEL Broadcast.exe` | 配信用の操作画面、シエル映像・目的カードを使う |
| **CIEL ＞ Build ＞ Android** | `unity/Builds/Android/CIEL Companion.apk` | スマホで使う（開発用） |

**ビルドしたものはほかの人に配らない。** LiveKit の接続の設定（`Assets/Settings/LiveKitTokenSource.asset`、開発用トークンサーバーの ID）が入っている。

## 必要なもの

- Unity 6000.6.4f1（`unity/ProjectSettings/ProjectVersion.txt`）。
- Android は、Unity Hub でこの版に **Android Build Support**（OpenJDK・Android SDK & NDK Tools を含む）を入れておく。

## ビルドのしかた

### エディタから

メニューの **CIEL ＞ Build ＞ Windows**、**Windows Broadcast**、**Android** から選ぶ。終わると Console に `CIEL_BUILD_OK: <出力先>` と出る。

- 選んだ側へ、ビルドの対象（Build Profile の有効なもの）が切り替わる。**対象を切り替えた最初のビルドは、素材の読み込み直しで時間がかかる**（数分〜十数分）。Windows と Android を交互にビルドすると毎回切り替わる。
- ビルドの間、エディタは操作できない。

### コマンドから（エディタを閉じて）

VS Code の統合ターミナルで Git Bash を開き、まずリポジトリ直下から `cd unity` で Unity プロジェクトへ移動する（すでに `unity` フォルダにいる場合は移動不要）。Unity Editor と、起動中の Windows アプリは閉じておく。

`run .` の `.` は現在のフォルダを指す。リポジトリ直下の `ciel-companion` で実行すると「Unity プロジェクトではありません」というエラーになる。Unity プロジェクトは `unity/` にあり、その中の `ProjectSettings/ProjectVersion.txt` が目印。

```sh
# リポジトリ直下から Unity プロジェクトへ移動（最初に一度だけ）
cd unity

# Windows
"/c/Program Files/Unity Hub/resources/unity.exe" --no-banner run . --timeout 1800 --log-file ./Logs/build-windows.log -- -executeMethod Ciel.Companion.Editor.CielBuild.Windows
# Windows配信版
"/c/Program Files/Unity Hub/resources/unity.exe" --no-banner run . --timeout 1800 --log-file ./Logs/build-broadcast.log -- -executeMethod Ciel.Companion.Editor.CielBuild.WindowsBroadcast
# Android
"/c/Program Files/Unity Hub/resources/unity.exe" --no-banner run . --timeout 3000 --log-file ./Logs/build-android.log -- -executeMethod Ciel.Companion.Editor.CielBuild.Android
```

成功するとログに `CIEL_BUILD_OK`、失敗すると `CIEL_BUILD_FAILED` が出る。出力先は Windows が `unity/Builds/Windows/CIEL Companion.exe`、Android が `unity/Builds/Android/CIEL Companion.apk`。

`unity/` からログの末尾を見る：

```sh
tail -n 50 Logs/build-windows.log
tail -n 50 Logs/build-android.log
```

### コマンドから（エディタを開いたまま）

開いているエディタのメニューを、Unity CLI から押せる。

```sh
# Windows
"/c/Program Files/Unity Hub/resources/unity.exe" --no-banner command menu --path "CIEL/Build/Windows" --detach
# Android
"/c/Program Files/Unity Hub/resources/unity.exe" --no-banner command menu --path "CIEL/Build/Android" --detach
```

`--detach` はビルド完了を待たずに戻る。結果は `unity/Logs/Editor.log` の `CIEL_BUILD_OK` で確かめる。

## Windows

- ビルドのときに次のプレイヤー設定にする：前面でなくても動き続ける（Run In Background）、ウィンドウで開く、ウィンドウの大きさを変えられる。会議中に OBS やブラウザを操作しても会話が止まらないようにするため。
- 起動：`unity\Builds\Windows\CIEL Companion.exe` をダブルクリック。`CIEL Companion_Data` などのフォルダは exe と同じ場所に置いたままにする。
- 起動すると、操作用のウィンドウ（`CIEL Companion`）と、シエルと背景だけの配信用のウィンドウ（`CIEL Companion 配信`）が開く。OBS では配信用のほうを取り込む（[会議への参加](../services/meeting-bridge-ja.md) の OBS の節）。開くかどうかは設定 → そのほか → 「配信用のウィンドウを開く」。処理は `Assets/Scripts/Conversation/CielStreamWindow.cs`。
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
- スマホでは、マイク・声の出力の選択欄は出ない（OS が切り替える）。会話のモードは「自動」なら 2 人になる。スマホを囲んで何人かで話すときは「会話：」ボタンで多人数にする。
- 画面の上の「声：」ボタンで、シエルの声を本体のスピーカー（みんなに聞こえる。既定）か受話口（耳に当てて聞く）かを切り替える（`AndroidSpeaker.cs`。Android の AudioManager に頼む）。スピーカーのときは、マイクがシエルの声を拾わないよう、エコー除去（Android 本体のものを優先）が効いている。それでも拾うときの対策は検討中（シエル自身の声を見分ける、話している間はマイクを止める）。
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

## サーバーへのデプロイ

### 前提

- 自宅の GPU サーバーへ、同じネットワークなど SSH で到達できる環境から実行する。
- 接続先を `scripts/server/.env.local` に書いておく（Git に入れない）。見本の `scripts/server/.env.example` を写して、自分の値にする：

  ```sh
  cp scripts/server/.env.example scripts/server/.env.local
  ```

  | 名前 | 中身 |
  |---|---|
  | `CIEL_SERVER_HOST` | SSH の接続先（`<ユーザー>@<サーバーのアドレス>`、または `~/.ssh/config` の Host 名）。必須 |
  | `CIEL_SSH_KEY` | SSH の秘密鍵の場所（例：`~/.ssh/id_ed25519`）。空なら ssh の普段の設定に任せる |

  同じ名前の環境変数があればそちらを、スクリプトの引数で接続先を渡せば引数を使う。どれも無いと、何もせずに止まる。
- 初めてつなぐサーバーの鍵は自動で覚え（`~/.ssh/known_hosts`）、2 回目からは鍵が変わっていたら止まる。サーバーを入れ直したなどで止まった場合は、`ssh-keygen -R <サーバーのアドレス>` で古い鍵を消してから実行し直す。
- サーバーに Docker Compose と NVIDIA GPU の実行環境があり、`~/work/ciel-companion/server/agent/.env` に API キーなどを設定済みであること。必要なモデル・参照音声はサーバーの `data/` に別途用意する。

### 手元から送って起動する

**手元のリポジトリルート**で実行する。ビルド後に `unity/` にいる場合は、先に `cd ..` で戻る。

```sh
bash scripts/server/deploy-server.sh
```

Git Bash で実行する（PowerShell 版は無い）。その回だけ別の接続先にする場合：

```sh
bash scripts/server/deploy-server.sh <ユーザー>@<サーバーのアドレス>
```

このコマンドは手元の `server/` 一式を `~/work/ciel-companion/server` へ送り、サーバーで `docker compose up -d --build` を実行する。コミット前の変更も送られるので、配布したい内容を確認してから実行する。

- 通常起動するもの：会話サーバー（`agent`）、読み上げ（`tts`）、歌を聴く（`singing`）、DB（`db`）。声質変換（`vc`）は任意。
- `.env` と `data/` は送信・上書きしない。DB のデータは Docker ボリュームに保持する。サーバーの `server/.env` が無い場合は DB のパスワードを自動生成する。
- 転送は既存ファイルへの上書きで、手元で削除したファイルをサーバーから消す処理はない。
- 最後に `DEPLOY_SERVER_DONE` が出たら、続けて下の手順で起動状態を確認する。

処理の本体：[転送スクリプト](../../scripts/server/deploy-server.sh) / [サーバー側の起動スクリプト](../../server/deploy-remote.sh)。全体の構成は [システムの構成](../project/architecture-ja.md) を参照。

### デプロイ後の確認・再起動

手元から SSH 接続する（`.env.local` に書いた接続先と鍵を使う。鍵を指定していなければ `-i` は不要）：

```sh
ssh -i <秘密鍵> <ユーザー>@<サーバーのアドレス>
```

**ここからはサーバー上**で実行する：

```sh
cd ~/work/ciel-companion/server

# 起動状態と直近のログ
docker compose ps
docker compose logs --tail 50 agent tts

# 会話サーバーのログを追う（Ctrl+C で表示を終了）
docker compose logs -f agent
```

必要な操作だけを選んで実行する：

```sh
# 会話サーバーを再起動する
docker compose restart agent

# サーバー上の agent/.env を変更したあと、その設定を反映する
docker compose up -d agent

# 声質変換を使うときだけ起動する / 使い終わったら止める
docker compose --profile vc up -d vc
docker compose stop vc

# SSH 接続を終了して手元へ戻る
exit
```

プロンプト本文・TOML は、**サーバー上の** `agent/config/` を編集した場合、次に開始する会話から反映される（再起動・再ビルド不要）。手元のファイルを編集した場合は、上のデプロイでサーバーへ送る。編集対象は [会話サーバーの README](../../server/agent/README.md) を参照。

### 開発用の会話サーバー

分析・デバッグ・試験は、本番とは別の**開発用の会話サーバー**で行う（ほかの人が本番を使っていても影響しない。決めたことは [開発用の会話サーバーの決定記録](build-ja.md)）。開発中のコードを、開発用だけに送る：

```sh
bash scripts/server/deploy-server.sh --dev
```

アプリは、設定 ＞ そのほか ＞ 開発 の「**開発用のサーバーにつなぐ**」を入れると、開発用につなぎ直す（左上に「C I E L ・ 開発用」と出る）。開発用は会話をいつも記録している。持ち帰るとき：

```sh
bash scripts/server/debug-log.sh pull --dev
```

開発用で議事録をとると、下書きは開発用の Discord のチャンネルへ送る。Webhook の URL は、サーバーの `~/work/ciel-companion-dev/server/.env.dev` の `CIEL_DEV_DISCORD_WEBHOOK=` に自分で書き、`deploy-server.sh --dev` で反映する（空のあいだはサーバーに保存するだけ）。

### デバッグ用の会話ログ

ふだんは会話を残さない。調べるときだけ入れる（決めたこと・残す中身は [デバッグ用の会話ログの決定記録](build-ja.md)）。**手元のリポジトリルート**で Git Bash から：

```sh
bash scripts/server/debug-log.sh on
```

入れると、次に始まる会話から残る（再起動は要らない）。調べ終わったら切って、持ち帰る：

```sh
bash scripts/server/debug-log.sh off
```

```sh
bash scripts/server/debug-log.sh pull
```

ログは手元の `.local/debug-logs/`（Git の外）に入る。`status` で入っているかと残っているログ、`clear` でサーバーのログをすぐ消せる。サーバーのログは 7 日で自動で消える。


## 調査用ログと確認の記録

会話ログの既定は非保存。調査時の`CIEL_DEBUG_LOG=1`またはサーバー内のONファイルで有効にし、`scripts/server/debug-log.sh`等の既存手順で取得する。本文・話者・道具結果を含むため、公開資料へ貼らない。通常は7日で古いログを削除する。音声の保存は別の明示的な開発用設定で、通常は行わない。正確な設定・出力は`debug_log.py`を参照する。

ビルド、Editor表示、実機の接続、本番反映の確認は[確認状況](../testing/verification-status-ja.md)へ記録し、このコマンド集へ過去の結果を追記しない。
