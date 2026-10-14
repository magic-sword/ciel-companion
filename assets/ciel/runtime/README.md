# Unityへ更新するための確定版パッケージ

最新は **半泣きv40＋サモエド折れ耳v42の採用版**。83層、通常を含む9表情、SDK15ファイルを保存した。`ParamTeary`で半泣きを切り替え、旧涙・目・耳の変形を重ねない。折れ耳v42はぷんすか・しょんぼり・困り・照れ・半泣きで共用する。新旧モデルの12表情切り替えとパッケージのハッシュ検証を通過済み。Unityのモデル本体への適用はまだ行っていない。

2026-10-14に採用した照れ（v39・目尻と赤みの最終調整済み）、困り（v37・下まぶた調整済み）、しょんぼり（v36）、ぷんすか（v35）、驚き（v34）、にこにこ、嬉しいを含む。
Cubismの正式モデルは`../rig/ciel.cmo3`。このフォルダはその検証済み書き出し。
現在Unityに入っているモデルはまだ更新していない。

**Unityのメニュー `CIEL > Model > Apply Current Package` で反映できる。**

実行すると素材・モデル・書き出しのハッシュを確認し、既存Unity素材を`.local/unity-model-update/`へ退避する。
moc3・アトラス・表示情報・モデル設定・表情ファイルをコピーし、再取り込みと待機設定を行う。
既存の`.meta`・うなずき・物理演算・まばたき・口パクの設定は引き継ぐ。シーンは作り直さない。
`CIEL > Model > Validate Current Package`なら検証だけを実行できる。

Unity側の`CielExpression`も準備済み。新モデルではにこにこを`ParamRelaxed`で切り替え、
古い目の細め方や口角の値を重ねない。嬉しいは`ParamHappy`も有効にする。
驚きは`ParamSurprised`で切り替え、従来の目の開きや口の開き値を重ねない。
ぷんすかはParamAngry、しょんぼりはParamSad、困りはParamTroubled、照れはParamEmbarrassedを使い、ParamEarFoldで折れ耳を表示する。困りでは旧汗、照れでは旧赤み・目線・口・耳の変形値を重ねない。通常や他の表情へ戻ると8つの専用キーを0へ戻し、旧モデルには以前の設定を使用する。

| ファイル | 内容 |
| --- | --- |
| `manifest.json` | 正式モデル・現行素材83層・パッケージ15ファイルのSHA-256 |
| `Ciel.model3.json` / `Ciel.moc3` / `Ciel.cdi3.json` | 検証済みモデルと表示情報 |
| `Ciel.4096/texture_00.png` | 現行83層を配置したアトラス |
| `Ciel.physics3.json` / `Motions/` | 既存の物理演算とうなずき |
| `Expressions/` | 通常・嬉しい・にこにこ・驚き・ぷんすか・しょんぼり・困り・照れ・半泣きの切り替えファイル。model3にも登録済み |

再作成は、正式モデルをCubismで保存・書き出して検証した後に行う。

```powershell
python -B scripts/live2d/prepare-current-runtime.py <書き出しフォルダ>
```

`current/approved.json`と正式モデルのハッシュが異なる場合は再作成・適用を止める。
表情を改修したら、採用状態と比較・検証記録も更新する。
最新の見た目は[にこにこの比較](../rig/proofs/relaxed-eye-corners/reference-comparison.png)を参照。
