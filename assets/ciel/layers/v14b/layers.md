# v14b レイヤー一覧

2172×2896 RGBA、54層、下から上。Mouth_Largeだけを更新し、残る53層はv14とSHA256一致。

- 閉口：Mouth_SmallとMouth_Largeを両方OFF。
- 小口：Mouth_SmallのみON。
- 大口：Mouth_LargeのみON。
- v14と同じくMouth_Skin_Upper/LowerとMouth_Line_Upper/Lowerは常時ON。新素材が閉口線を完全に覆う。
- 開口素材は不透明度100%で排他表示。歯・舌・輪郭は一体。
- 閉眼：Eye_L_Closed・Eye_R_ClosedをON、他のEye層をOFF。
- layer-state.jsonのmouth_switchとpresetsに切り替えを記載。

PSD出力先はassets/ciel/psd/ciel-v14b。[作成ラッパー](../../../../scripts/live2d/v14b/build_psd_with_state.py)を同梱。今回PSD自体は未作成。

|順|レイヤー|通常|内容|クリップ|
|---:|---|---|---|---|
|1|Hair_Back|ON|v14そのまま|なし|
|2|Body|ON|v14そのまま|なし|
|3|Choker_Back|ON|v14そのまま|なし|
|4|Choker_Inside|ON|v14そのまま|なし|
|5|Neck|ON|v14そのまま|なし|
|6|Neck_Shadow_Chin|ON|v14そのまま|Neck|
|7|Outer_R|ON|v14そのまま|なし|
|8|Outer_L|ON|v14そのまま|なし|
|9|Choker_Pendant|ON|v14そのまま|なし|
|10|Choker_Front|ON|v14そのまま|なし|
|11|Choker_Buckle|ON|v14そのまま|なし|
|12|Ear_R_Outer|ON|v14そのまま|なし|
|13|Ear_R_Inner|ON|v14そのまま|なし|
|14|Ear_L_Outer|ON|v14そのまま|なし|
|15|Ear_L_Inner|ON|v14そのまま|なし|
|16|Face_Skin|ON|v14そのまま|なし|
|17|Face_Shadow_Hair|ON|v14そのまま|Face_Skin|
|18|Nose|ON|v14そのまま|なし|
|19|Mouth_Skin_Upper|ON|v14そのまま|なし|
|20|Mouth_Skin_Lower|ON|v14そのまま|なし|
|21|Mouth_Line_Upper|ON|v14そのまま|なし|
|22|Mouth_Line_Lower|ON|v14そのまま|なし|
|23|Mouth_Small|OFF|v14そのまま|なし|
|24|Mouth_Large|OFF|大口を再生成|なし|
|25|Eye_R_Sclera|ON|v14そのまま|なし|
|26|Eye_R_Iris|ON|v14そのまま|Eye_R_Sclera|
|27|Eye_R_Highlight|ON|v14そのまま|Eye_R_Sclera|
|28|Eye_R_LidSkin_Upper|ON|v14そのまま|なし|
|29|Eye_R_LidSkin_Lower|ON|v14そのまま|なし|
|30|Eye_R_LashUpper|ON|v14そのまま|なし|
|31|Eye_R_LashLower|ON|v14そのまま|なし|
|32|Eye_R_Crease|ON|v14そのまま|なし|
|33|Eye_R_Closed|OFF|v14そのまま|なし|
|34|Eye_L_Sclera|ON|v14そのまま|なし|
|35|Eye_L_Iris|ON|v14そのまま|Eye_L_Sclera|
|36|Eye_L_Highlight|ON|v14そのまま|Eye_L_Sclera|
|37|Eye_L_LidSkin_Upper|ON|v14そのまま|なし|
|38|Eye_L_LidSkin_Lower|ON|v14そのまま|なし|
|39|Eye_L_LashUpper|ON|v14そのまま|なし|
|40|Eye_L_LashLower|ON|v14そのまま|なし|
|41|Eye_L_Crease|ON|v14そのまま|なし|
|42|Eye_L_Closed|OFF|v14そのまま|なし|
|43|Hair_Ahoge|ON|v14そのまま|なし|
|44|Ear_R_Base|ON|v14そのまま|なし|
|45|Ear_L_Base|ON|v14そのまま|なし|
|46|Hair_Side_R_LongFront|ON|v14そのまま|なし|
|47|Hair_Side_L_LongFront|ON|v14そのまま|なし|
|48|Hair_Side_R_Inner|ON|v14そのまま|なし|
|49|Hair_Side_L_Inner|ON|v14そのまま|なし|
|50|Hair_Front_1|ON|v14そのまま|なし|
|51|Hair_Front_3|ON|v14そのまま|なし|
|52|Hair_Front_2|ON|v14そのまま|なし|
|53|Brow_R|ON|v14そのまま|なし|
|54|Brow_L|ON|v14そのまま|なし|
