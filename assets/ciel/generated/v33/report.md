# にこにこ：下まぶたの境界修正

新規生成は行わず、v32の輪郭付き一体画像から左右の下まぶた線を色・領域マスクで分離した。原画の色と透明度を保持し、v32と共通の配置変換を使用する。

にこにこ中だけ既存の下まぶた肌と下まつ毛を隠し、追加線を描画された白目の下端に合わせた。瞳・白目の形や位置は変更していない。半閉眼にもキーを設け、完全閉眼・笑い目では追加線を消す。通常と嬉しいは以前のメッシュ位置・不透明度と一致する。

半閉眼・開眼の左右で、線と白目下端の距離の95百分位は1.32px未満（2172×2896キャンバス）。目線・角度・開口・表情ブレンドの81組み合わせを検証済み。

再現用：`prepare-relaxed-lid-lines.py`で分離、PSDを新規メッシュとして取り込み、`integrate-relaxed-lid-boundary.py`で設定。Cubismでアトラス配置・保存・書き出し後、`check-relaxed-lid-boundary.py`と`check-relaxed.py`で検証し、`promote-relaxed-lid-boundary.py`で採用する。

[変更前後](../../rig/proofs/relaxed-boundary-v33/boundary-comparison.png)・[承認見本との比較](../../rig/proofs/relaxed-boundary-v33/reference-comparison.png)。Unityは未更新。
