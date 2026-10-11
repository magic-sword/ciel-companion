# v11 層の担当と受け渡し

2172×2896、RGBA、62層。全層キャンバス原点 (0,0)。下→上順、名前、通常表示50層／差分非表示12層はv10と同一。L/Rはキャラクター視点（R＝画面左）。

## PSD を作る前に

`psd-manifest.json` の out は `assets/ciel/psd/ciel-v11`。PSD/XCF自体は今回の書き込み範囲外なので作成していない。

既存の `scripts/live2d/gimp/build_layers_psd.py` は表示状態を読まない。全層表示すると閉じ目や口差分が重なるため、[表示状態対応ラッパー](../../../../scripts/live2d/v11/build_psd_with_state.py)を同じGIMP 3バッチ環境で使用する。`CIEL_PROJECT_ROOT` をプロジェクトルート、`CIEL_PSD_MANIFEST` を `assets/ciel/layers/v11/psd-manifest.json` に設定する。ラッパーは既存ビルダーをメモリ上で読み、挿入時と保存後の再読込で表示状態を照合する。今回GIMP実行・PSD保存・Cubism取り込みは未確認。

## 表示とクリッピング

- 通常：ONの50層。開眼＋閉口。
- 閉眼：左右の `Eye_*_Closed` のみON、他の全 `Eye_*` はOFF。
- 小口：`Mouth_Line_Upper/Lower` と `Mouth_Large_*` はOFF、5枚の `Mouth_Small_*` はON。大口はSmallとLargeを入れ替える。
- `Mouth_Skin_Upper/Lower` は全口状態でON。顔を変えたため、まぶた肌と口周囲肌も新しい顔色で更新済み。
- 虹彩・点光は同側の白目へ、歯・舌は同サイズの口腔へ、髪影はFace_Skinへ、顎影はNeckへクリップ。PNG確認図は静止画合成。Cubismのクリッピング設定は別途必要。
- 閉眼／開口差分は終端形。まばたき・口パクの連続変形や中間形はこの納品で確認していない。
- 髪7層の32px下塗り、耳・首輪の分割契約はv10を継承。髪の根元を固定し毛先へ変形量を増やす。
- 顔輪郭と頬の陰はFace_Skin内で一緒に補正。髪影は髪の位置から再計算。首の横移動は首輪に向かって0pxへ戻す。

## 全層

|下→上|名前|通常|内容|下に隠れる相手|動き／クリップ|
|---:|---|---|---|---|---|
|1|`Hair_Back`|ON|既存後ろ髪を保持し、y365の切れ目の下に丸い頭部を補完。頭頂の外形は前髪担当。|耳、顔、前髪、体|頭XY・後ろ髪の揺れ|
|2|`Body`|ON|胴・服・菱形をv9のまま保持|上位の部位|体・呼吸|
|3|`Choker_Back`|ON|首輪の後帯|上位の部位|首|
|4|`Choker_Inside`|ON|首輪内側の暗部|上位の部位|首|
|5|`Neck`|ON|上端を右8px、首輪接続で0pxへ減衰。|上位の部位|首|
|6|`Neck_Shadow_Chin`|ON|補正首へ追従した顎影。|上位の部位|首＋頭XY／クリップ：Neck|
|7|`Outer_R`|ON|上着とファーをv9のまま保持|上位の部位|肩・体|
|8|`Outer_L`|ON|上着とファーをv9のまま保持|上位の部位|肩・体|
|9|`Choker_Pendant`|ON|接続タブと丸飾り|上位の部位|首輪＋飾り揺れ|
|10|`Choker_Front`|ON|前帯。金具の下まで帯を補完。|Choker_Buckle|首輪の曲げ|
|11|`Choker_Buckle`|ON|矩形金具とシアンの留め具。帯から分離。|なし|首輪追従、金具の剛性維持|
|12|`Ear_R_Outer`|ON|耳の外形と内毛の下の連続面。人間耳なし。|内毛・付け根毛・前髪|耳の傾き|
|13|`Ear_R_Inner`|ON|内側の白い毛。下地と線を二重に持たせない。|付け根毛・前髪|耳親＋内毛の小変形|
|14|`Ear_L_Outer`|ON|耳の外形と内毛の下の連続面。人間耳なし。|内毛・付け根毛・前髪|耳の傾き|
|15|`Ear_L_Inner`|ON|内側の白い毛。下地と線を二重に持たせない。|付け根毛・前髪|耳親＋内毛の小変形|
|16|`Face_Skin`|ON|お手本の頬・顎に合わせた顔土台。目鼻口の座標は保持。|上位の部位|頭XY|
|17|`Face_Shadow_Hair`|ON|固定髪の影を補正顔へ再クリップ。|上位の部位|顔＋髪の変位／クリップ：Face_Skin|
|18|`Nose`|ON|v9の小さな鼻|上位の部位|顔|
|19|`Mouth_Skin_Upper`|ON|既存の位置・肌マスクを保ち、補正後のFace_Skinから色を再採取。|口線・口内|口周りの変形|
|20|`Mouth_Skin_Lower`|ON|既存の位置・肌マスクを保ち、補正後のFace_Skinから色を再採取。|口線・口内|口周りの変形|
|21|`Mouth_Small_Inside`|**OFF**|小口123×36px配置。歯・舌・輪郭を焼き込まない連続したローズモーブの口腔。|舌・歯・口線|口の開閉|
|22|`Mouth_Large_Inside`|**OFF**|大口185×133px配置。歯・舌・輪郭を焼き込まない連続したローズモーブの口腔。|舌・歯・口線|口の開閉|
|23|`Mouth_Small_Tongue`|**OFF**|小口123×36px配置。生成した淡いピンクの舌。|口の開口縁|口の開閉／クリップ：Mouth_Small_Inside|
|24|`Mouth_Large_Tongue`|**OFF**|大口185×133px配置。生成した淡いピンクの舌。|口の開口縁|口の開閉／クリップ：Mouth_Large_Inside|
|25|`Mouth_Small_Teeth`|**OFF**|小口123×36px配置。左右の小さな八重歯。|口の開口縁|口の開閉／クリップ：Mouth_Small_Inside|
|26|`Mouth_Large_Teeth`|**OFF**|大口185×133px配置。左右の小さな八重歯。|口の開口縁|口の開閉／クリップ：Mouth_Large_Inside|
|27|`Mouth_Line_Upper`|ON|承認済み微笑みの上半分。|なし|閉じた微笑み|
|28|`Mouth_Small_Line_Upper`|**OFF**|小口123×36px配置。生成口の連続した上縁と口角。|口の開口縁|口の開閉|
|29|`Mouth_Large_Line_Upper`|**OFF**|大口185×133px配置。生成口の連続した上縁と口角。|口の開口縁|口の開閉|
|30|`Mouth_Line_Lower`|ON|承認済み微笑みの下半分。上線と合成して元の一本の線。|なし|閉じた微笑み|
|31|`Mouth_Small_Line_Lower`|**OFF**|小口123×36px配置。生成口の連続した側縁下部と下縁。|口の開口縁|口の開閉|
|32|`Mouth_Large_Line_Lower`|**OFF**|大口185×133px配置。生成口の連続した側縁下部と下縁。|口の開口縁|口の開閉|
|33|`Eye_R_Sclera`|ON|白目。虹彩の下も白で連続させた開口。|虹彩・まぶた・まつげ|まばたき開口／虹彩クリップ元|
|34|`Eye_R_Iris`|ON|瞳孔込みの丸い虹彩。見える部分はv9、隠れる上端のみ生成素材。白い点光は分離。|まぶた肌・まつげ|視線、白目へのクリッピング／クリップ：Eye_R_Sclera|
|35|`Eye_R_Highlight`|ON|v9の白い点光。青い面反射は虹彩の彩色として保持。|まぶた|虹彩と一緒に移動／クリップ：Eye_R_Sclera|
|36|`Eye_R_LidSkin_Upper`|ON|既存の位置・肌マスクを保ち、補正後のFace_Skinから色を再採取。|上まつげ・二重|まばたき上まぶた|
|37|`Eye_R_LidSkin_Lower`|ON|既存の位置・肌マスクを保ち、補正後のFace_Skinから色を再採取。|下まつげ|まばたき下まぶた|
|38|`Eye_R_LashUpper`|ON|上まつげと目尻をv9から分離。|髪|まばたき／表情|
|39|`Eye_R_LashLower`|ON|下まつげ・下縁の線をv9から分離。|髪|まばたき／表情|
|40|`Eye_R_Crease`|ON|二重線をv9から分離。|髪|まばたき／表情|
|41|`Eye_R_Closed`|**OFF**|開眼と同幅の新規閉じ目。開眼層と排他。|髪|閉眼の終端形|
|42|`Eye_L_Sclera`|ON|白目。虹彩の下も白で連続させた開口。|虹彩・まぶた・まつげ|まばたき開口／虹彩クリップ元|
|43|`Eye_L_Iris`|ON|瞳孔込みの丸い虹彩。見える部分はv9、隠れる上端のみ生成素材。白い点光は分離。|まぶた肌・まつげ|視線、白目へのクリッピング／クリップ：Eye_L_Sclera|
|44|`Eye_L_Highlight`|ON|v9の白い点光。青い面反射は虹彩の彩色として保持。|まぶた|虹彩と一緒に移動／クリップ：Eye_L_Sclera|
|45|`Eye_L_LidSkin_Upper`|ON|既存の位置・肌マスクを保ち、補正後のFace_Skinから色を再採取。|上まつげ・二重|まばたき上まぶた|
|46|`Eye_L_LidSkin_Lower`|ON|既存の位置・肌マスクを保ち、補正後のFace_Skinから色を再採取。|下まつげ|まばたき下まぶた|
|47|`Eye_L_LashUpper`|ON|上まつげと目尻をv9から分離。|髪|まばたき／表情|
|48|`Eye_L_LashLower`|ON|下まつげ・下縁の線をv9から分離。|髪|まばたき／表情|
|49|`Eye_L_Crease`|ON|二重線をv9から分離。|髪|まばたき／表情|
|50|`Eye_L_Closed`|**OFF**|開眼と同幅の新規閉じ目。開眼層と排他。|髪|閉眼の終端形|
|51|`Hair_Ahoge`|ON|v9アホ毛。根元は冠の後ろ。|上位の部位|アホ毛揺れ|
|52|`Ear_R_Base`|ON|既存耳下部の接合毛。耳親を基礎に頭側へ根元固定。|頭頂・前髪|耳と頭の接合|
|53|`Ear_L_Base`|ON|既存耳下部の接合毛。耳親を基礎に頭側へ根元固定。|頭頂・前髪|耳と頭の接合|
|54|`Hair_Side_R_LongFront`|ON|画面左・胸へ下る長い手前髪。根元を頬髪の下へ32px補完。|Hair_Side_L_LongFront, Hair_Side_R_Inner, Hair_Side_L_Inner, Hair_Front_1, Hair_Front_3, Hair_Front_2|頭→各束。根元固定、毛先を個別に揺らす|
|55|`Hair_Side_L_LongFront`|ON|画面右・胸へ下る長い手前髪。根元を頬髪の下へ32px補完。|Hair_Side_R_Inner, Hair_Side_L_Inner, Hair_Front_1, Hair_Front_3, Hair_Front_2|頭→各束。根元固定、毛先を個別に揺らす|
|56|`Hair_Side_R_Inner`|ON|画面左・頬を包む内側の横髪。前髪の下へ32px補完。|Hair_Side_L_Inner, Hair_Front_1, Hair_Front_3, Hair_Front_2|頭→各束。根元固定、毛先を個別に揺らす|
|57|`Hair_Side_L_Inner`|ON|画面右・頬を包む内側の横髪。前髪の下へ32px補完。|Hair_Front_1, Hair_Front_3, Hair_Front_2|頭→各束。根元固定、毛先を個別に揺らす|
|58|`Hair_Front_1`|ON|画面左の前髪束。中央束の下へ32px補完。頭頂の丸みも分担。|Hair_Front_3, Hair_Front_2|頭→各束。根元固定、毛先を個別に揺らす|
|59|`Hair_Front_3`|ON|画面右の前髪束。中央束の下へ32px補完。頭頂の丸みも分担。|Hair_Front_2|頭→各束。根元固定、毛先を個別に揺らす|
|60|`Hair_Front_2`|ON|目の間へ下る中央束。承認済みの毛先を保持。頭頂を水平に切らず、分け目で左右束と接続。|根元以外は露出|頭→各束。根元固定、毛先を個別に揺らす|
|61|`Brow_R`|ON|v9眉。前髪より上。|上位の部位|眉表情|
|62|`Brow_L`|ON|v9眉。前髪より上。|上位の部位|眉表情|
