# マイクラのスキン（シエル・博士）

今使っているスキンだけを置く（2026-11-06 にユーザーが採用）。作った経緯は [マインクラフトで遊ぶ設計](../../../docs/games/minecraft/minecraft-design-ja.md) の 16 章。

| ファイル | だれ | 型 | 中身 |
|---|---|---|---|
| `Ciel.png` | シエル（ボットのプレイヤー名 `Ciel`） | スリム（腕 3 px） | 顔は候補 D。Ears の設定（左下 x 0〜3・y 32〜35）と、立体の耳（x 24〜39・y 0〜7、裏 x 56〜63・y 28〜43）・尻尾（x 56〜63・y 16〜27）の絵入り |
| `Hakase4364.png` | 博士（持ち主のプレイヤー名） | ふつう（腕 4 px） | 黒髪・琥珀色の目・灰色のコート |
| `Ciel_Debug.png` | 試験用の`Ciel_Debug`、開発アプリ用の`Ciel_Dev` | スリム（腕 3 px） | シエルの 2P カラー。形・Ears の設定は `Ciel.png` と同じで、色だけ黒い服と緑のターミナル色の光（2026-11-07）。開発用には同じ画像を`Ciel_Dev.png`という名前で配置する |

LocalSkin内のファイル名はプレイヤー名と一致させる。2Pカラーの画像の正本は`Ciel_Debug.png`で、`Ciel_Dev.png`は配置時に同じ内容をコピーする。

## 見えるようにする（持ち主の PC だけ）

サーバーはアカウントの確認なし（`online-mode=false`）なので、公式のスキンはだれにも届かない。持ち主のマイクラ（Fabric 1.21.11）に Mod を入れて、自分の画面でだけ表示する。

1. ランチャーの起動構成（今は「CIEL」、ゲームディレクトリ `D:\CIEL\apps\minecraft\data1`）のバージョンを `fabric-loader-0.20.1-1.21.11` にする。
2. ゲームディレクトリの `mods\` に、CustomSkinLoader（`CustomSkinLoader_Universal-15.1.jar`）と Ears（`ears-fabric-1.21.11-2.2.1-c.jar`）を置く（どちらも Modrinth）。
3. `CustomSkinLoader\LocalSkin\skins\` に、このフォルダの 3 枚を置く。
   開発用の身体`Ciel_Dev`にも2Pカラーを表示するため、`Ciel_Debug.png`を同じ配置先へ`Ciel_Dev.png`の名前でもコピーする。画像を更新したときは両方を更新する。
4. 一度起動すると `CustomSkinLoader\CustomSkinLoader.json` ができる。`loadlist` を `LocalSkin` だけにする（既定では Mojang や外部のスキンサービスを先に探し、別人の「ciel」のスキンが出た。外部への問い合わせも止まる）。

既存の `.minecraft` の `mods\` には Forge 1.20.1 の Mod があるので、同じフォルダに入れない。ランチャーを開いたまま `launcher_profiles.json` を書き換えると、ランチャーに上書きされる（2026-11-06、足した起動構成が消えた）。

2026-11-11、`Ciel_Dev`の画像未配置をCustomSkinLoaderのログで確認し、上記ゲームディレクトリへ2Pカラーを配置した。正本とのSHA-256一致を確認済み。ゲーム内の表示が変わらなければ、Minecraftのサーバーから一度退出して入り直す。画像の再読込と見た目はゲーム内で確認する。

## 直すとき

見た目の直しは Codex に頼む（依頼文の例は `.local/codex/req-53`〜`59`）。Ears の耳・尻尾の場所と向きは、上の表のとおり（耳の裏は、後ろから見た 16×8 の絵 B(u, v) を (x = 63 − v, y = 43 − u) に置く）。Ears の設定を変えるときは、設定ツール [skin.daisy.cat](https://skin.daisy.cat)（ブラウザの中だけで動く）か、`.local/minecraft-skins/ears/ears-regions.html` で読み書きできる。
