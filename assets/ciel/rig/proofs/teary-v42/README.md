# 採用済み：半泣きとサモエド折れ耳

2026-10-14、半泣きv40の顔とv42の大きめの折れ耳を正式モデルへ採用。

- [見本・旧表情・採用モデル](reference-comparison.png)
- [モデルの描画](teary.png)
- [左右のまばたき・発話](blink-and-mouth.png)
- [顔の向き](head-angles.png)
- [通常と共用する5表情の実モデル描画](shared-expressions.png)
- [検証記録](verification.json)と[採用記録](adoption.json)

Cubismで読み込み、アトラスを再生成して保存・SDK書き出しした実モデルの描画。以前の9ポーズの耳以外の形と表示、涙と目線の独立、左右別のまばたき、発話の口、81通りの組み合わせを確認。

耳はぷんすか・しょんぼり・困り・照れ・半泣きで共用。通常時の立ち耳は変更しない。正式モデルは `../../ciel.cmo3`、素材は `../../../current/`、Unity更新パッケージは `../../../runtime/`。Unityへは未適用。
