# Unityへ更新するための確定版パッケージ

2026-10-13に確定したにこにこ（下まぶた・目尻調整済み）と、採用済みの嬉しいを含む。
Cubismの正式モデルは`../rig/ciel.cmo3`。このフォルダはその検証済み書き出し。
現在Unityに入っているモデルはまだ更新していない。

**Unityのメニュー `CIEL > Model > Apply Current Package` で反映できる。**

実行すると素材・モデル・書き出しのハッシュを確認し、既存Unity素材を`.local/unity-model-update/`へ退避する。
moc3・アトラス・表示情報・モデル設定・表情ファイルをコピーし、再取り込みと待機設定を行う。
既存の`.meta`・うなずき・物理演算・まばたき・口パクの設定は引き継ぐ。シーンは作り直さない。
`CIEL > Model > Validate Current Package`なら検証だけを実行できる。

Unity側の`CielExpression`も準備済み。新モデルではにこにこを`ParamRelaxed`で切り替え、
古い目の細め方や口角の値を重ねない。嬉しいは`ParamHappy`も有効にする。
通常へ戻ると両方を0へ戻し、旧モデルには以前の設定を使用する。

| ファイル | 内容 |
| --- | --- |
| `manifest.json` | 正式モデル・現行素材66層・パッケージ9ファイルのSHA-256 |
| `Ciel.model3.json` / `Ciel.moc3` / `Ciel.cdi3.json` | 検証済みモデルと表示情報 |
| `Ciel.4096/texture_00.png` | 現行66層を配置したアトラス |
| `Ciel.physics3.json` / `Motions/` | 既存の物理演算とうなずき |
| `Expressions/` | 通常・嬉しい・にこにこの切り替えファイル |

再作成は、正式モデルをCubismで保存・書き出して検証した後に行う。

```powershell
python -B scripts/live2d/prepare-current-runtime.py <書き出しフォルダ>
```

`current/approved.json`と正式モデルのハッシュが異なる場合は再作成・適用を止める。
表情を改修したら、採用状態と比較・検証記録も更新する。
最新の見た目は[にこにこの比較](../rig/proofs/relaxed-eye-corners/reference-comparison.png)を参照。
