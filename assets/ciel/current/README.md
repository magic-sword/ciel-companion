# シエルの現行素材

採用中の素材115層（頭部・表情89、身体と上着22、尻尾2、ほっぺのくぼみの影2）。2026-10-17 時点。

| 用途 | 採用中の参照先 |
| --- | --- |
| 素材の一覧と配置 | [layers.json](layers.json) と `layers/*.png` |
| 採用状態・正式モデルのハッシュ | [approved.json](approved.json) |
| 編集用モデル | [../rig/ciel.cmo3](../rig/ciel.cmo3)（[説明](../rig/README.md)） |
| 確認図・検証結果 | [../rig/proofs/current/](../rig/proofs/current/) |
| 配布用SDK | [../runtime/](../runtime/README.md)（`manifest.json` で照合） |
| Unityで使用するモデル | `unity/Assets/Characters/Ciel/`（リポジトリのルートから） |

## 配置

素材キャンバスは3000×3800、モデル原点は(414,0)、モデルキャンバスは2172×2896。頭部・表情・ほっぺの素材はモデルキャンバスの大きさのPNGを、一覧の `canvas` / `offset` で配置する。腕や手をモデルキャンバス内へ縮小しない。CMOのUVと原寸PNGのワールド座標の差に注意し、身体や関節の倍率・移動を二重適用しない。
尻尾2層は1254×1254の素材座標のPNGで、配置・拡大・左向きへの反転はCMO内で行う（`placement: native-rig`）。PSDの初期表示では非表示にする。

全素材のPSD/XCFは `CIEL_PSD_MANIFEST=assets/ciel/current/layers.json` として `scripts/live2d/gimp/build_layers_psd.py` で再作成できる（出力はGit対象外）。

## 動きの部品

- 尻尾：パラメーターはすべて範囲−1〜1、初期値0。`ParamCielTailWag` は画面左=−1・非表示=0・画面右=1。`ParamCielTailFollow` と `ParamCielTailTip` は物理演算の出力先。Unityでは `CielTail` が「嬉しい」「わくわく」に合わせて振る（`Wag(strength, seconds, cyclesPerSecond)`）。画角は顔中心のまま（orthographic size=0.7003115）で、尻尾のために変えない。
- ほっぺ（L＝モデルの左＝画面の右）：`ParamCielCheekPoke{L,R}` 押す0〜1（くぼみの影の不透明度は0→0.3）、`ParamCielCheekPullX{L,R}` 外向き＋・`PullY{L,R}` 下向き＋で−1〜1、`ParamCielCheekJiggle{L,R}` は物理演算の出力（押す量を入力にした短い振り子）。顔の回転の下に `Cheek_Squish_L/R` のワープを挟み、顔・口・鼻の曲面をその子にした。Unityでは `CielTouch` がつつき・引っ張りを扱い、内側へは変形させず、上へはわずかにだけ引く。引っ張りの強さで困り顔／半泣きにし、会話サーバーへ `cheek`・`pull` を知らせる。
- 頬の赤みは、表情用も含めて目の下の部品より上に描く。

再検証: `python -B scripts/live2d/v64/adopt-cheek.py`。過去の版は Git の履歴（タグ `archive/pre-history-cleanup` 以前）とローカルの `.local/history/` にある。
