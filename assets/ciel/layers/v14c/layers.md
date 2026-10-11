# v14c レイヤー一覧

2172×2896 RGBA、54層、下から上。Mouth_Largeの八重歯だけ変更。残る53層はv14bとSHA256一致。

- 閉口：Mouth_Small・Mouth_LargeともOFF。
- 小口：Mouth_SmallのみON。
- 大口：Mouth_LargeのみON。
- Mouth_Skin_Upper/Lower・Mouth_Line_Upper/Lowerは常時ON。開口素材で閉口線を覆う。
- Small/Largeは不透明度100%で排他表示。歯もMouth_Large内に統合。
- 閉眼：Eye_L_Closed・Eye_R_ClosedをON、その他のEye層をOFF。
- mouth_switchとpresetsはv14bを継承。

manifestのoutはassets/ciel/psd/ciel-v14c。[PSD作成ラッパー](../../../../scripts/live2d/v14c/build_psd_with_state.py)を同梱。PSD実体は未作成。

|順|名前|通常|内容|クリップ|
|---:|---|---|---|---|
|1|Hair_Back|ON|v14bそのまま|なし|
|2|Body|ON|v14bそのまま|なし|
|3|Choker_Back|ON|v14bそのまま|なし|
|4|Choker_Inside|ON|v14bそのまま|なし|
|5|Neck|ON|v14bそのまま|なし|
|6|Neck_Shadow_Chin|ON|v14bそのまま|Neck|
|7|Outer_R|ON|v14bそのまま|なし|
|8|Outer_L|ON|v14bそのまま|なし|
|9|Choker_Pendant|ON|v14bそのまま|なし|
|10|Choker_Front|ON|v14bそのまま|なし|
|11|Choker_Buckle|ON|v14bそのまま|なし|
|12|Ear_R_Outer|ON|v14bそのまま|なし|
|13|Ear_R_Inner|ON|v14bそのまま|なし|
|14|Ear_L_Outer|ON|v14bそのまま|なし|
|15|Ear_L_Inner|ON|v14bそのまま|なし|
|16|Face_Skin|ON|v14bそのまま|なし|
|17|Face_Shadow_Hair|ON|v14bそのまま|Face_Skin|
|18|Nose|ON|v14bそのまま|なし|
|19|Mouth_Skin_Upper|ON|v14bそのまま|なし|
|20|Mouth_Skin_Lower|ON|v14bそのまま|なし|
|21|Mouth_Line_Upper|ON|v14bそのまま|なし|
|22|Mouth_Line_Lower|ON|v14bそのまま|なし|
|23|Mouth_Small|OFF|v14bそのまま|なし|
|24|Mouth_Large|OFF|小さな八重歯2本を追加|なし|
|25|Eye_R_Sclera|ON|v14bそのまま|なし|
|26|Eye_R_Iris|ON|v14bそのまま|Eye_R_Sclera|
|27|Eye_R_Highlight|ON|v14bそのまま|Eye_R_Sclera|
|28|Eye_R_LidSkin_Upper|ON|v14bそのまま|なし|
|29|Eye_R_LidSkin_Lower|ON|v14bそのまま|なし|
|30|Eye_R_LashUpper|ON|v14bそのまま|なし|
|31|Eye_R_LashLower|ON|v14bそのまま|なし|
|32|Eye_R_Crease|ON|v14bそのまま|なし|
|33|Eye_R_Closed|OFF|v14bそのまま|なし|
|34|Eye_L_Sclera|ON|v14bそのまま|なし|
|35|Eye_L_Iris|ON|v14bそのまま|Eye_L_Sclera|
|36|Eye_L_Highlight|ON|v14bそのまま|Eye_L_Sclera|
|37|Eye_L_LidSkin_Upper|ON|v14bそのまま|なし|
|38|Eye_L_LidSkin_Lower|ON|v14bそのまま|なし|
|39|Eye_L_LashUpper|ON|v14bそのまま|なし|
|40|Eye_L_LashLower|ON|v14bそのまま|なし|
|41|Eye_L_Crease|ON|v14bそのまま|なし|
|42|Eye_L_Closed|OFF|v14bそのまま|なし|
|43|Hair_Ahoge|ON|v14bそのまま|なし|
|44|Ear_R_Base|ON|v14bそのまま|なし|
|45|Ear_L_Base|ON|v14bそのまま|なし|
|46|Hair_Side_R_LongFront|ON|v14bそのまま|なし|
|47|Hair_Side_L_LongFront|ON|v14bそのまま|なし|
|48|Hair_Side_R_Inner|ON|v14bそのまま|なし|
|49|Hair_Side_L_Inner|ON|v14bそのまま|なし|
|50|Hair_Front_1|ON|v14bそのまま|なし|
|51|Hair_Front_3|ON|v14bそのまま|なし|
|52|Hair_Front_2|ON|v14bそのまま|なし|
|53|Brow_R|ON|v14bそのまま|なし|
|54|Brow_L|ON|v14bそのまま|なし|
