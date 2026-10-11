# v14 レイヤー一覧

2172×2896 RGBA、54層。下から上の順。v11の開口10層を一体素材2層に置換。残る52層はバイト単位で同じ。

## 口の切り替え

- 閉口：`Mouth_Small`・`Mouth_Large` ともOFF。
- 小口：`Mouth_Small` のみON。
- 大口：`Mouth_Large` のみON。
- `Mouth_Skin_Upper/Lower`・`Mouth_Line_Upper/Lower` は常時ON。開口素材が閉口線を完全に覆う。
- Small/Largeは同時表示しない。肌を含むため、それぞれ不透明度100%で使用。
- 閉眼：左右の `Eye_*_Closed` をON、他のEye層をOFF。口状態は独立。

口の中・歯・舌・輪郭は生成画素を一体で保存。分割なし。新しい口素材のクリップ先はなし。
表情プリセットと表示リストは `layer-state.json` に記載。従来のmouth_closedグループのみをOFFにする汎用処理ではなく、v14のmouth_switchを使う。

## PSD

`psd-manifest.json` の out は `assets/ciel/psd/ciel-v14`。
[GIMP 3作成ラッパー](../../../../scripts/live2d/v14/build_psd_with_state.py)を同梱。PSD出力先は今回の書き込み許可範囲外のため未実行。

|順|名前|通常表示|出典・担当|クリップ|
|---:|---|---|---|---|
|1|Hair_Back|ON|v11そのまま|なし|
|2|Body|ON|v11そのまま|なし|
|3|Choker_Back|ON|v11そのまま|なし|
|4|Choker_Inside|ON|v11そのまま|なし|
|5|Neck|ON|v11そのまま|なし|
|6|Neck_Shadow_Chin|ON|v11そのまま|Neck|
|7|Outer_R|ON|v11そのまま|なし|
|8|Outer_L|ON|v11そのまま|なし|
|9|Choker_Pendant|ON|v11そのまま|なし|
|10|Choker_Front|ON|v11そのまま|なし|
|11|Choker_Buckle|ON|v11そのまま|なし|
|12|Ear_R_Outer|ON|v11そのまま|なし|
|13|Ear_R_Inner|ON|v11そのまま|なし|
|14|Ear_L_Outer|ON|v11そのまま|なし|
|15|Ear_L_Inner|ON|v11そのまま|なし|
|16|Face_Skin|ON|v11そのまま|なし|
|17|Face_Shadow_Hair|ON|v11そのまま|Face_Skin|
|18|Nose|ON|v11そのまま|なし|
|19|Mouth_Skin_Upper|ON|v11そのまま|なし|
|20|Mouth_Skin_Lower|ON|v11そのまま|なし|
|21|Mouth_Line_Upper|ON|v11そのまま|なし|
|22|Mouth_Line_Lower|ON|v11そのまま|なし|
|23|Mouth_Small|OFF|生成された口内・歯・舌・輪郭と周囲の肌を一体で抽出。縁だけ透明化。|なし|
|24|Mouth_Large|OFF|生成された口内・歯・舌・輪郭と周囲の肌を一体で抽出。縁だけ透明化。|なし|
|25|Eye_R_Sclera|ON|v11そのまま|なし|
|26|Eye_R_Iris|ON|v11そのまま|Eye_R_Sclera|
|27|Eye_R_Highlight|ON|v11そのまま|Eye_R_Sclera|
|28|Eye_R_LidSkin_Upper|ON|v11そのまま|なし|
|29|Eye_R_LidSkin_Lower|ON|v11そのまま|なし|
|30|Eye_R_LashUpper|ON|v11そのまま|なし|
|31|Eye_R_LashLower|ON|v11そのまま|なし|
|32|Eye_R_Crease|ON|v11そのまま|なし|
|33|Eye_R_Closed|OFF|v11そのまま|なし|
|34|Eye_L_Sclera|ON|v11そのまま|なし|
|35|Eye_L_Iris|ON|v11そのまま|Eye_L_Sclera|
|36|Eye_L_Highlight|ON|v11そのまま|Eye_L_Sclera|
|37|Eye_L_LidSkin_Upper|ON|v11そのまま|なし|
|38|Eye_L_LidSkin_Lower|ON|v11そのまま|なし|
|39|Eye_L_LashUpper|ON|v11そのまま|なし|
|40|Eye_L_LashLower|ON|v11そのまま|なし|
|41|Eye_L_Crease|ON|v11そのまま|なし|
|42|Eye_L_Closed|OFF|v11そのまま|なし|
|43|Hair_Ahoge|ON|v11そのまま|なし|
|44|Ear_R_Base|ON|v11そのまま|なし|
|45|Ear_L_Base|ON|v11そのまま|なし|
|46|Hair_Side_R_LongFront|ON|v11そのまま|なし|
|47|Hair_Side_L_LongFront|ON|v11そのまま|なし|
|48|Hair_Side_R_Inner|ON|v11そのまま|なし|
|49|Hair_Side_L_Inner|ON|v11そのまま|なし|
|50|Hair_Front_1|ON|v11そのまま|なし|
|51|Hair_Front_3|ON|v11そのまま|なし|
|52|Hair_Front_2|ON|v11そのまま|なし|
|53|Brow_R|ON|v11そのまま|なし|
|54|Brow_L|ON|v11そのまま|なし|
