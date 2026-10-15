# シエルを Zoom・Google Meet の会議に参加させる（多人数の会話）

全体の構成は [システムの構成](architecture-ja.md) を参照。

更新：2026-10-15（日本時間）。試作の段階。会議にはシエルが「別の参加者」として入り、何人かの人と同時に話す。

## しくみ

LiveKit の部屋に入るのは、今までどおり Unity のアプリ（CIEL Companion）と会話サーバー（server/agent）だけ。会議の人たちは LiveKit の部屋には入らない。
シエル用の会議のクライアント（ブラウザ）のマイク・スピーカー・カメラを、仮想オーディオケーブルと OBS の仮想カメラでアプリにつなぐ。

```
会議（Zoom / Meet）
 ├─ 利用者 … 普段のアプリかブラウザ（実際のマイク・ヘッドホン）
 ├─ ほかの参加者
 └─ シエル … 別のブラウザ（例：Edge）で「シエル」として参加
       スピーカー：Hi-Fi Cable Input ─→ Hi-Fi Cable Output ─→ アプリの「マイク」 ─→ 会話サーバー（シエルが聞く）
       マイク    ：CABLE Output     ←─ CABLE Input       ←─ アプリの「声の出力」 ←─ 会話サーバー（シエルの声）
       カメラ    ：OBS Virtual Camera ←─ OBS のウィンドウキャプチャ ←─ アプリの画面
```

向きの違う 2 本の音の線が要るので、仮想ケーブルを 2 本使う。会議システムは自分の声を自分に返さないので、シエルの声が入力へ戻ってくることはない。

## 用意するもの（初回だけ）

| もの | 入手先 | 用途 |
|---|---|---|
| VB-Audio Virtual Cable（無料） | https://vb-audio.com/Cable/ | シエルの声 → 会議（「CABLE Input／CABLE Output」） |
| VB-Audio Hi-Fi Cable（寄付制・無料で使える） | 同じページ | 会議の音 → シエル（「Hi-Fi Cable Input／Output」） |
| OBS Studio（映像も流すとき） | https://obsproject.com/ja | アプリの画面を仮想カメラにする |
| シエル用の会議の参加口 | — | Zoom はブラウザからゲスト名で入れる（主催者の設定による）。Meet はゲスト参加を主催者が承認する。安定させるならシエル専用のアカウントを作る |

仮想ケーブルを入れたら PC を再起動する。

## アプリのビルド（Windows）

会議で使うときは、Unity のエディタではなくビルドしたアプリを使う。

- Unity のメニュー **CIEL ＞ Build ＞ Windows**、または Unity を閉じて、リポジトリの `unity` で次を実行（Git Bash。PowerShell では `--` が渡らない）：
  ```sh
  "/c/Program Files/Unity Hub/resources/unity.exe" --no-banner run . --timeout 1800 --log-file ./Logs/build-windows.log -- -executeMethod Ciel.Companion.Editor.CielBuild.Windows
  ```
- 出力：`unity/Builds/Windows/CIEL Companion.exe`（Git 管理外）。処理は `Assets/Editor/CielBuild.cs`。
- ビルドの設定：前面でなくても動き続ける（Run In Background）、ウィンドウで開く、大きさを変えられる。会議中に OBS やブラウザを操作しても会話が止まらないようにするため。
- ビルドには LiveKit の接続の設定（`Assets/Settings/LiveKitTokenSource.asset`）が入る。**ほかの人に配らない。** `..._BackUpThisFolder_ButDontShipItWithYourGame` も配らない。
- アプリのログ：`%USERPROFILE%\AppData\LocalLow\CIEL\CIEL Companion\Player.log`

## 会議のたびの手順

### 1. アプリ（CIEL Companion）

1. `CIEL Companion.exe` を起動する。
2. 画面の上の欄を選ぶ（選んだものは次回も使われる）：
   - 「マイク：」→ **Hi-Fi Cable Output**
   - 「声の出力：」→ **CABLE Input**
3. 「会話：」ボタンが「自動 ― いまは 多人数」になっていることを確かめる。
4. **マイクボタンを押して「録音中」にし、会議のあいだ入れたままにする。** 切るとシエルには何も聞こえない。

### 2. OBS（映像も流すとき）

1. ソースの「＋」→「ウィンドウキャプチャ」→ `[CIEL Companion.exe]: CIEL Companion`。キャプチャ方式は「Windows 10 (1903 以降)」。
2. 今はマイクボタンや選択欄も映るので、必要ならフィルタの「クロップ」で切り抜く。アプリの画面は縦長（540×960）なので、横長のキャンバス（1280×720 など）の中央に置く。
3. 「仮想カメラ開始」を押す。

### 3. シエル用の会議のクライアント

利用者とは別のブラウザ（例：利用者が Chrome なら Edge）か別のプロファイルで、名前を「シエル」にして入る。

**Zoom（ブラウザ版）**
1. 招待リンクを開き、「ブラウザから参加」を選ぶ。
2. 「コンピューターオーディオで参加」を押す。
3. 画面下のマイクのボタンの横の「^」で選ぶ：
   - マイク：**CABLE Output**
   - スピーカー：**Hi-Fi Cable Input**
4. 映像を流すなら、カメラの「^」で **OBS Virtual Camera**。
5. 音声の設定で「背景雑音を抑制」を「低」にするか、「オリジナルサウンド」をオンにする（合成の声が雑音として削られないように）。

**Google Meet**
1. 会議のリンクを開き、参加する前の画面か、参加後の「︙」→「設定」→「音声」で選ぶ：
   - マイク：**CABLE Output**
   - スピーカー：**Hi-Fi Cable Input**
2. 「動画」でカメラを **OBS Virtual Camera**。

### 4. 利用者

いつものアプリかブラウザで、実際のマイクと**ヘッドホン**で同じ会議に入る（スピーカーだと、会議の音を実際のマイクが拾い直す）。

### 5. 参加者への説明

会議に AI（シエル）が参加し、会議の声を会話サーバー（OpenAI の Realtime API）で処理することを、参加者に先に伝えて了承を得る。

## 会話のモード（2 人・多人数）

アプリの「会話：」ボタンで、自動 → 2 人 → 多人数 → 自動 と切り替える（選んだものは次回も使われる）。

| モード | 答え方 |
|---|---|
| 2 人 | 今までどおり、話しかけられるたびに答える |
| 多人数 | 次のときだけ答える：「シエル」と呼ばれた／シエルへの質問やお願い／シエルの直前の発言への返し／その場の全員への質問。答えるときは 1〜2 文 |
| 自動 | 「声の出力」の名前に CABLE・VB-Audio・Voicemeeter を含めば多人数、それ以外は 2 人。文字は `CielConversation` の Meeting Output Keywords で変えられる |

しくみ：

- Unity は `ciel.mode` のデータのメッセージ（`{"v":1,"type":"conversation.mode","mode":"group"}`）を、つないだとき・会話サーバーが部屋に入ったとき・モードが変わったときに送る。
- 会話サーバー（`server/agent/mode.py`）は、多人数のとき `config/prompts/group.md` の決まりを指示の最後に足す（`update_instructions`。会話の途中で切り替わる）。
- 答えないとき、会話モデルは `[silent]` とだけ出す。`mode.drop_silent` が読み上げ・文字起こしから捨てる。会話の履歴には残るので、黙っていたあいだの流れもシエルは覚えている。
- 多人数は `CIEL_VOICE=irodori`（文字から声を作る方式）のときだけ使える。ほかの方式では会話サーバーが受け付けず、2 人のまま続ける。

## 困ったとき

| 症状 | 確かめること |
|---|---|
| シエルが何も反応しない | アプリのマイクが「録音中」か。「マイク：」が Hi-Fi Cable Output か。Windows の「設定 → システム → サウンド → 入力」で Hi-Fi Cable Output を選び、会議で誰かが話したときに音量のメーターが動くか（動かなければ、シエル用の会議のスピーカーが Hi-Fi Cable Input になっていない） |
| 会議にシエルの声が聞こえない | 「声の出力：」が CABLE Input か。シエル用の会議のマイクが CABLE Output か。会議の側でミュートになっていないか |
| シエルの声が途切れる・小さい | シエル用の Zoom の雑音の抑制を「低」にするか、オリジナルサウンドをオンにする |
| 呼んでも答えない・呼んでいないのに答える | 会話サーバーのログで「多人数の会話：シエルは黙った」「会話のモード：group」が出ているか。判断の決まりは `config/prompts/group.md` |
| アプリを前面から外すと止まる | 古いビルドを使っていないか（Run In Background はビルドの設定で入れてある） |

会話サーバーのログは、自宅サーバーの `~/work/ciel-companion/server/agent` で `docker compose logs --tail 50` で見る。

## 今の制限（試作）

- 話者を区別しない。会議の全員の声が 1 本に混ざって届く。誰の発言かは、名乗った名前や話の流れから推し量るだけ。
- 多人数でも、誰かが話し終わるたびに会話モデルは動く（黙るかどうかを決めるため）。出力は `[silent]` だけなので料金は小さい。
- シエルが話している途中で誰かが話し始めると、シエルの話は止まる（2 人のときと同じ割り込み）。
- 映像には操作の部品（ボタン・選択欄）も映る。会議用に隠す表示は未実装。
- 確かめていないこと：実際の会議での聞き取り・判断の精度、Zoom・Meet の雑音の抑制との相性、OBS での取り込み。

## 今後の候補

- 会議用の表示（操作の部品を隠す、横長の画面、単色の背景）。
- 話者の区別：OpenAI の `gpt-4o-transcribe-diarize`（Realtime で使えるかはアカウント次第）か、自宅 GPU の pyannote など。
- 迷う発言だけ、別の小さなモデルで「答えるべきか」を判断する。
