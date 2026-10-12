# v16 首輪・上着の一体絵

首輪は1回生成の第1案、上着は4回生成の第3案を採用。体は指定のv15生成原画を使用し、再生成していません。
前のv16作業で作成済みだった首輪1案・上着3案を引き継ぎ、今回追加した生成は上着の第4案1回です。準備だけで実行されていなかった旧第4案の指示文は回数に含めていません。

## 納品

- 原画: `../../generated/v16/choker.png`、`../../generated/v16/jacket.png`。採用候補からバイト単位で同一のコピーです。
- 配置済み: `garments/Body.png`、`garments/Choker.png`、`garments/Jacket.png`。すべて2172×2896、RGBA、透明背景。
- 配置設定: `placement.json`。元から存在した設定をそのまま使用。
- 全体比較: `../../generated/v16/proofs/comparison-full.png`
- 首〜肩比較: `../../generated/v16/proofs/comparison-neck-shoulders.png`
- 透明合成: `../../generated/v16/proofs/v16-composite.png`
- 配置パーツ一覧: `../../generated/v16/proofs/placed-garments.png`
- 上着候補一覧: `../../generated/v16/proofs/jacket-candidates.png`
- 指示文・参照・ハッシュ: `../../generated/v16/generation-log.json`

## 採用理由

首輪第1案は、前帯から左右の内壁、奥側の帯まで一つの楕円の輪として連続しています。中央の金具、二つのシアンの発光点、下がる丸い飾り、黒い当て布が一枚に描かれ、参照のデザインを保っています。

上着第1案は連続した襟と裏地を満たしますが、中央に白いベストのような見返しと腰の黒い帯が加わっています。第2案はそれが減った一方で、後ろ襟が高く、肩から外した着方より通常の着方に近く見えます。第3案は中央で低く下がる後ろ襟が左右のファーへつながり、袖も比較的下向きで、4案の中では元絵の着方に最も近いため採用しました。第4案は襟がつながっていますが、上腕外側の髪状の長い房と周囲の点が増えたため不採用です。

## 配置

座標はキャンバス左上が原点。各原画全体の左上を、同じ倍率で拡大縮小した後に指定位置へ移動しています。回転は0度、切り抜き・前後分割はありません。

| パーツ | 原画 | 縦横共通倍率 | 左上座標 |
|---|---|---:|---|
| Body | v15/parts/body-01.png | 1.10 | (553, 1286) |
| Choker | v16/choker.png | 0.33 | (875, 1327) |
| Jacket | v16/jacket.png | 1.61 | (-35, 1280) |

配置は元絵の首輪・肩・袖のおおよその位置に合わせています。生成形状と元絵の差を局所変形で合わせる処理はしていません。上着の袖先・外縁と体の下端にはキャンバス外に出る部分があります。完全な上着は原画PNGに残っています。

## 確認と残る問題

- 重ね順はv15b後ろ髪 → Body → v14cの表示中の顔・頭・首レイヤー → Jacket → Choker。v14cの旧Body・旧上着・旧首輪は除外しています。
- 前後未分割のため、上着の背中側のシアン裏地が胸の白い服・宝石を隠し、後ろ襟が首元と前髪の一部に重なります。首輪の奥側も首より手前に表示されています。この確認図は完成時の前後関係を表しません。Claude Codeで前後を分けて重ね順を設定する必要があります。
- 採用した上着第3案にも、両上腕外側に髪のように見える細長い白い房が残っています。袖口の内側も濃い空洞の影が弱く、シアンの面として見えます。
- ファーの量感・前端・袖の装飾位置は元絵と完全一致していません。首輪も元絵に比べ帯と飾りの比率に小さな差があります。均等拡大縮小・移動での配置のため、その差を残しています。
- 生成原画には輪郭周囲の微小な孤立点や半透明の縁が残っています。消去・マスク・色調整・描き足しは行っていません。
- 体はv15の生成原画そのものです。脇の追加やお腹の形状変更を含むv15/v15bの加工済みBodyは使っていません。
- ハッシュと画素比較により、採用原画のコピー一致、体の元画像一致、3配置レイヤーが均等拡大縮小と移動のみの結果に一致することを確認しました。開始時に存在したv16ファイルのハッシュも全件一致しています。詳細は`validation.json`と`handoff-validation.json`。
- 作業成果は指定の3つのv16ディレクトリ内に保存しています。画像生成ツールは指定保存先に対応せず、ツール管理の`C:/Users/prog/.codex/generated_images/`にも原画を自動保存しました。その原画をv16へコピーしています。既存ファイルは変更していません。

## 実行した画像生成の指示文（全文）

全呼び出しで`transparent_background=true`。第1〜3案の実行指示文は前のv16セッションの記録から回収しました。

### choker-01（採用）

参照: `assets/ciel/generated/v16/inputs/choker-reference.png`

```text
Create ONE complete isolated choker accessory as a single naturally painted coherent object, based closely on the attached approved anime character collar reference. True transparent background. Front view, worn shape around an invisible upright neck: a shallow oval closed ring, NOT a flat strip and not separate front/back pieces. Render the entire continuous rear arc and the dark navy inner wall visible inside the left and right ends of the ring, smoothly joining the front band with consistent thickness and perspective. The empty neck opening is transparent. Preserve the reference design: broad luminous cyan panels, charcoal black upper and lower edging and vertical panel separators, central upright rounded rectangular dark clasp with a silver frame and two small cyan lights vertically stacked, a short cyan/silver connector hanging in front, one round cyan luminous pendant with silver dark edging. Include the small black triangular fabric backing below the collar and behind the pendant. The backing belongs only below the band, not inside the neck hole. Refined clean 2D anime linework, soft cool lilac shadows, subtle cel shading, front view same as reference. No neck, skin, body, hair, clothes, mannequin, text, labels, cast shadow, extra accessories or detached fragments. Complete silhouette with transparent margin all around. Keep the collar band and pendant proportions exactly like the reference; do not exaggerate the depth of the oval. Save the generated original PNG to D:/CIEL/apps/ciel-companion/assets/ciel/generated/v16/parts/choker-01.png. Do not write anywhere else.
```

### jacket-01（不採用）

参照: `assets/ciel/generated/v16/inputs/jacket-reference.png`、`assets/ciel/master/ciel-upper-body-2x.png`

```text
Paint ONE complete isolated white puffer jacket from the attached approved anime character reference as a coherent finished garment on a truly transparent background. Front view in the SAME worn off-shoulder silhouette as the reference, with the wearer invisible. This is a single jacket, not two separate sleeves: the two large fluffy white shoulder collars must connect naturally through ONE continuous rear fur collar across the back of the neck. Paint that previously occluded back arc and the continuous cyan inner back lining as physical parts of this jacket. The back fur arc is fairly low, just behind the base of the neck; it smoothly rolls forward and down to the two broad fluffy shoulder lapels with no pasted seams. Preserve the generous shoulder fur shapes tapering down towards the chest, white puffy sleeves hanging down and slightly outward in the reference pose, cyan interior lining visible inside the open front edges, charcoal reinforcement panels and straps, round cyan glowing ornaments near each upper sleeve, elongated charcoal panels with round cyan glowing discs lower on both sleeves, fine lilac seam linework and cool lavender cel shadows. Match the original broad jacket silhouette and sleeve angles precisely, shoulders slipped down and a wide open front. Draw the inward-facing back lining behind the invisible torso naturally, with fabric depth and folds, as part of the same garment. No body, skin, neck, face, hair, ears, hands, mannequin, white central shirt, diamond chest gem, choker, pendant, belt or skirt. Do not mistake the long white hair for fur or jacket: no long hair tendrils. Only one jacket. Preserve the reference's clean polished 2D anime illustration style, soft cool shading, white fabric and bright cyan accents, near bilateral symmetry. Full jacket object with transparent margin; no captions, no ground shadow, no extra objects, no split panels. Save original PNG to D:/CIEL/apps/ciel-companion/assets/ciel/generated/v16/parts/jacket-01.png if output path is configurable.
```

### jacket-02（不採用）

参照: `assets/ciel/generated/v16/inputs/jacket-reference.png`、`assets/ciel/generated/v16/parts/jacket-01.png`

```text
Create a refined new version of the SINGLE complete isolated white off-shoulder puffer jacket. Reference 1 is the approved original character: match its garment design and WIDE OPEN FRONT silhouette. Reference 2 is the first standalone jacket draft: preserve its one-piece rear collar and natural continuous cyan back lining, but correct its overly narrow front opening and excessive inward white lapels. Both sleeves are worn slipped down off the shoulders, with arms down, not stretched sideways. Make the two big white fluffy front fur lapels fall along the OUTSIDE of the invisible shoulders/chest as in reference 1; keep a broader gap between the inward edges, with the cyan back lining visible through that broad open gap. The two front fur masses join smoothly through ONE lower rear fur collar extending across the shoulder blades behind the base of the invisible neck. This is a coherent volumetric jacket, no detached parts. Only cyan lining inside: eliminate the extra white front vertical facings with black waist straps seen in draft 2; those resemble the central shirt from the character and do not belong to this jacket. Keep the white puffy sleeves, cyan inner side lining, black reinforcement armbands with round cyan lights and elongated dark lower sleeve patches with round lights. Fine cool lavender anime linework, luminous white cloth, fur with natural tufts and soft lilac shadows, polished clean cel shading matching reference 1. The front fur lapels should be long and full like reference 1, tapering to the upper-arm round ornaments. No actual body, skin, neck, head, hands, mannequin, hair, shirt, chest diamond, waist belt, choker or pendant. Front view, symmetrical, complete garment including both empty cuff openings. True transparent background, no text, no backdrop, no ground shadows, no extra objects, generous clear margin. Draw the inner rear lining continuously as a physical jacket back, not a transparent hole. Output as one finished garment painting.
```

### jacket-03（採用）

参照: `assets/ciel/generated/v16/inputs/jacket-reference.png`、`assets/ciel/master/ciel-upper-body-2x.png`

```text
Using the attached original anime character image as the design reference, paint ONLY her white puffer jacket as ONE complete coherent garment, including the previously hidden back. Transparent background. Think of the wearer becoming invisible while the jacket retains its exact worn position and silhouette. The jacket is worn OFF BOTH SHOULDERS, the collar slipped outward around the upper arms. It is NOT a zipped coat or a coat worn normally up at the neck. Keep the front opening VERY WIDE as in the original: the inward edge of left front fur is about 36 percent across the overall garment width, and right front fur at about 64 percent, so the center third remains broadly open. Large white fluffy fur lapels sit on the outer shoulders and descend toward the upper-arm cyan lights. The highest tufts are around the outer shoulders. Both side fur lapels connect naturally through one LOWER narrow soft rear collar around the back/base of the neck, continuously painted with matching thickness and flowing tufts. The rear collar should sag gently in the center behind the invisible nape, not rise into a high stand collar. Draw the continuous cyan back lining naturally between the two sides, behind the invisible chest: broad back fabric with gentle folds. Its upper edge follows the lower back collar. The back lining is part of the jacket and is opaque cyan fabric, not a hole. Keep both puffy white sleeves falling almost vertically down beside the body with only a modest outward angle like the original, longer and with roomy cuffs. Preserve original black upper arm reinforcements, round cyan glowing ornaments near the upper arms, elongated black plaques with larger round cyan lights below, cyan side lining, white seams with pale cool lavender shadows. No extra white central vest panels or long front white shirt strips. No skin, body, neck, hands, head, hair, mannequin, choker, shirt, chest diamond, skirt or waist belt. One naturally drawn connected jacket only, no separate panels or duplicate parts. Refined 2D anime artwork with crisp delicate lavender outlines and soft cel shading, coherent material and lighting. Centered front view, complete silhouette and transparent margin on all sides, no text or ground shadow.
```

### jacket-04（不採用）

参照: `assets/ciel/generated/v16/inputs/jacket-reference.png`、`assets/ciel/generated/v16/parts/jacket-03.png`

```text
Create one complete isolated white puffer jacket as a transparent PNG asset. Use the first reference as the authoritative anime artwork and clothing design. The second reference is the current complete jacket candidate: improve its silhouette to match the original relaxed off-shoulder worn pose, with the two shoulders dropped outward. Draw the jacket ONLY, no person, skin, neck, head, hair, chest garment, choker, jewelry, mannequin, hanger or background. Front view at the original viewing angle, as worn by an invisible person. The left and right fluffy white fur lapels MUST flow smoothly into ONE continuous fur collar passing behind the neck/back, a shallow curved U-shaped back neckline lower in the center, not a high upright wall and not two detached pieces. Preserve full continuous cyan back lining with plausible cloth folds and seams behind the invisible torso, naturally connected to the cyan side lining. Preserve the original white puff sleeves, black reinforcement bands, round glowing cyan upper-arm decorations, dark oval forearm hardware, thin lavender anime linework, cool white and pale lilac cel shading. All garment parts are one coherent connected object painted together, with soft naturally joined collar transitions. No long hair-like wisps trailing behind the collar. Both sleeves hang downward slightly outward, with original large puffy proportions and a wide open front. Include complete sleeve cuffs and all edges with transparent margin. Use a landscape canvas like the second reference and similar object framing. Real alpha transparency, no background color, no checkerboard, no floating debris. This is candidate jacket-04, the fourth and final jacket generation for v16. Save the resulting image to D:/CIEL/apps/ciel-companion/assets/ciel/generated/v16/parts/jacket-04.png if local output paths are supported.
```
