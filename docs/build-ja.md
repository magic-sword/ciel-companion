# ビルド・サーバーデプロイのコマンド集

更新：2026-10-18（日本時間）。コマンドは **Git Bash** 用。

## まずここから

ターミナルでリポジトリのルート（`ciel-companion/`）を開く。ビルドだけは、そこから `cd unity` で移動して実行する。

| やりたいこと | 実行する場所 | 手順 |
|---|---|---|
| Windows / Android をビルドする | 手元の `unity/` | [ビルドのコマンド](#コマンドからエディタを閉じて) |
| Unity を開いたままビルドする | 手元の `unity/` | [メニューをコマンドで実行](#コマンドからエディタを開いたまま) |
| Windows アプリを起動する | 手元のリポジトリルート | `"./unity/Builds/Windows/CIEL Companion.exe"` |
| Android 端末に APK を入れる | 手元の `unity/` | [Android](#android) |
| サーバーへデプロイする | 手元のリポジトリルート | `bash scripts/server/deploy-server.sh`（[前提と確認方法](#サーバーへのデプロイ)） |
| サーバーの状態・ログを見る | SSH 接続先の `~/work/ciel-companion/server` | [デプロイ後の確認・再起動](#デプロイ後の確認再起動) |

Unity 側の変更はアプリをビルドし直し、`server/` 側の変更はサーバーへデプロイする。両方を変更したときは両方を行う。

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

VS Code の統合ターミナルで Git Bash を開き、まずリポジトリ直下から `cd unity` で Unity プロジェクトへ移動する（すでに `unity` フォルダにいる場合は移動不要）。Unity Editor と、起動中の Windows アプリは閉じておく。

`run .` の `.` は現在のフォルダを指す。リポジトリ直下の `ciel-companion` で実行すると「Unity プロジェクトではありません」というエラーになる。Unity プロジェクトは `unity/` にあり、その中の `ProjectSettings/ProjectVersion.txt` が目印。

```sh
# リポジトリ直下から Unity プロジェクトへ移動（最初に一度だけ）
cd unity

# Windows
"/c/Program Files/Unity Hub/resources/unity.exe" --no-banner run . --timeout 1800 --log-file ./Logs/build-windows.log -- -executeMethod Ciel.Companion.Editor.CielBuild.Windows
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

- 通常起動するもの：会話サーバー（`agent`）、読み上げ（`tts`）、DB（`db`）。声質変換（`vc`）は任意。
- `.env` と `data/` は送信・上書きしない。DB のデータは Docker ボリュームに保持する。サーバーの `server/.env` が無い場合は DB のパスワードを自動生成する。
- 転送は既存ファイルへの上書きで、手元で削除したファイルをサーバーから消す処理はない。
- 最後に `DEPLOY_SERVER_DONE` が出たら、続けて下の手順で起動状態を確認する。

処理の本体：[転送スクリプト](../scripts/server/deploy-server.sh) / [サーバー側の起動スクリプト](../server/deploy-remote.sh)。全体の構成は [システムの構成](architecture-ja.md) を参照。

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

プロンプト本文・TOML は、**サーバー上の** `agent/config/` を編集した場合、次に開始する会話から反映される（再起動・再ビルド不要）。手元のファイルを編集した場合は、上のデプロイでサーバーへ送る。編集対象は [会話サーバーの README](../server/agent/README.md) を参照。

## アプリで確かめたこと・まだのこと

2026-10-19追加：議事録を記録中、アプリを前面に表示している間は自動消灯を防ぎ、終了・切断時に元の設定へ戻す処理を追加。声から開始した場合もサーバーの記録状態に連動する。Androidビルド成功（`CIEL_BUILD_OK`）。手動ロック・別アプリへの切り替え中の録音継続は対象外。[仕様と実機確認の手順](decisions/meeting-minutes-ja.md#議事録中の自動スリープ防止2026-10-19)を参照。実機での消灯・録音継続の確認は未実施。

2026-10-18追加：[複数端末の独立した会話](decisions/independent-conversations-ja.md)に合わせ、接続ごとに別の部屋を要求するWindowsビルドに成功。固定トークン（Literal）は使用せず、DevelopmentTokenServerまたは `room_name` に対応したEndpointを設定する。サーバーの共有記憶・音声合成の改善は本番未反映。実端末2台の同時会話とAndroid再ビルドは未確認。

- Windows：ビルド・起動・会話・仮想ケーブルへの出力を確認済み（2026-10-15）。
- Android：ビルドは確認済み（2026-10-15、APK 約 58 MB、arm64-v8a、API 26 以上、権限の宣言も確認）。**実機での起動・マイクの許可・会話は未確認。**
