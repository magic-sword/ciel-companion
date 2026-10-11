"""Validate delivered v14b and generate its standalone documentation."""
import ast
import hashlib
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from common import ROOT,GEN,LAY,PROOF,SIZE,read,write

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    hashes=read(GEN/'inputs/source-hashes.json')
    assert all(sha(ROOT/p)==h for p,h in hashes.items()),'Existing source changed'
    state=read(LAY/'layer-state.json');old=read(ROOT/'assets/ciel/layers/v14/layer-state.json')
    manifest=read(LAY/'psd-manifest.json')
    assert len(state['layers'])==54
    assert manifest['out']=='assets/ciel/psd/ciel-v14b'
    assert manifest['layers']==[{k:r[k] for k in ('name','path')} for r in state['layers']]
    assert state['presets']==old['presets'] and state['mouth_switch']==old['mouth_switch']
    assert [r['name'] for r in state['layers']]==[r['name'] for r in old['layers']]
    preserved=[]
    for r in state['layers']:
        p=ROOT/r['path']
        with Image.open(p) as im:
            assert im.mode=='RGBA' and im.size==SIZE and im.getextrema()[3][0]==0
        if r['name']!='Mouth_Large':
            assert sha(p)==sha(ROOT/'assets/ciel/layers/v14'/p.name)
            preserved.append(r['name'])
    assert len(preserved)==53
    for m in ('closed','small'):
        assert np.array_equal(np.asarray(Image.open(PROOF/f'{m}-composite.png')),
                              np.asarray(Image.open(ROOT/f'assets/ciel/generated/v14/proofs/{m}-composite.png')))
    base=np.asarray(Image.open(GEN/'inputs/v11-neutral.png'))
    actual=np.asarray(Image.open(PROOF/'large-composite.png'))
    alpha=np.asarray(Image.open(LAY/'Mouth_Large.png'))[:,:,3]
    assert np.array_equal(base[alpha==0],actual[alpha==0])
    for n in ('Mouth_Line_Upper','Mouth_Line_Lower'):
        ink=np.asarray(Image.open(LAY/(n+'.png')))[:,:,3]>0
        assert np.all(alpha[ink]==255)
    metrics=read(GEN/'extraction/metrics.json')
    assert metrics['inverse_space_opaque_core_max']<=1
    assert metrics['input_space_opaque_core_mae']<1
    measurements=read(GEN/'extraction/corner-measurements.json')
    selected=measurements['large-01']
    assert selected['height_difference_input_px']==0
    assert all(v==0 for v in selected['threshold_sensitivity'].values())
    assert abs(measurements['centering']['horizontal_offset_from_axis_canvas_px'])<1
    for filename in ('mouth-switch.gif','mouth-switch.png'):
        with Image.open(PROOF/filename) as im:assert im.n_frames==4
    private=list((GEN/'private').glob('*.png'))
    assert private and all('PRIVATE' in p.name for p in private)
    cp=subprocess.run(['git','check-ignore','--',*[p.relative_to(ROOT).as_posix() for p in private]],
                      cwd=ROOT,capture_output=True,text=True,check=True)
    assert len(cp.stdout.strip().splitlines())==len(private)
    for p in Path(__file__).parent.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
    count=read(GEN/'generation-log.json')['count'];assert count==3
    result={'passed':True,'generation_count':count,'generation_limit':6,'layer_count':54,
        'unchanged_v14_layers':len(preserved),'unchanged_source_files':len(hashes),
        'small_and_closed_composites_equal_v14':True,'outside_large_patch_equal_v11':True,
        'closed_line_fully_covered':True,'private_gitignored':True,
        'corner_height_difference_input_px':selected['height_difference_input_px'],
        'corner_height_difference_canvas_px':selected['height_difference_canvas_px'],
        'psd_export_run':False,'symmetry_note':'Corner contour estimate, not a claim of bitwise mirror symmetry.'}
    write(LAY/'validation.json',result)
    rows=['# v14b レイヤー一覧','',
          '2172×2896 RGBA、54層、下から上。Mouth_Largeだけを更新し、残る53層はv14とSHA256一致。','',
          '- 閉口：Mouth_SmallとMouth_Largeを両方OFF。',
          '- 小口：Mouth_SmallのみON。',
          '- 大口：Mouth_LargeのみON。',
          '- v14と同じくMouth_Skin_Upper/LowerとMouth_Line_Upper/Lowerは常時ON。新素材が閉口線を完全に覆う。',
          '- 開口素材は不透明度100%で排他表示。歯・舌・輪郭は一体。',
          '- 閉眼：Eye_L_Closed・Eye_R_ClosedをON、他のEye層をOFF。',
          '- layer-state.jsonのmouth_switchとpresetsに切り替えを記載。','',
          'PSD出力先はassets/ciel/psd/ciel-v14b。[作成ラッパー](../../../../scripts/live2d/v14b/build_psd_with_state.py)を同梱。今回PSD自体は未作成。','',
          '|順|レイヤー|通常|内容|クリップ|','|---:|---|---|---|---|']
    for i,r in enumerate(state['layers'],1):
        rows.append(f"|{i}|{r['name']}|{'ON' if r['visible'] else 'OFF'}|{'大口を再生成' if r['name']=='Mouth_Large' else 'v14そのまま'}|{r.get('clip') or 'なし'}|")
    (LAY/'layers.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    report=f'''# v14b：大口だけを左右対称に再生成

**large-01を採用。生成は3回／上限6回。左右の口角の高さの差は0px（1254×1254生成画像上の輪郭測定）。** 2172×2896キャンバスへ戻した換算でも0px。v14の小口と閉口をそのまま保持し、大口以外の53層はv14とSHA256一致。

## 確認図

- [閉口／小口／大口](../../generated/v14b/proofs/three-states.png)
- [v14とv14b](../../generated/v14b/proofs/v14-v14b.png)
- [v12・v13・v14・v14b](../../generated/v14b/proofs/v12-v13-v14-v14b.png)
- [生成された顔と素材合成の比較](../../generated/v14b/proofs/generated-vs-composite.png)
- [口拡大での一致確認](../../generated/v14b/proofs/generated-vs-composite-mouth.png)
- [素材単体：明暗の背景](../../generated/v14b/proofs/parts-light-dark.png)
- [切替GIF](../../generated/v14b/proofs/mouth-switch.gif)／[APNG](../../generated/v14b/proofs/mouth-switch.png)
- [全候補の顔と旧v14](../../generated/v14b/proofs/candidates.png)／[口拡大](../../generated/v14b/proofs/candidate-mouths.png)
- [左右口角の測定位置](../../generated/v14b/proofs/corner-measurements.png)
- [鼻・顎の中心線と口の中心](../../generated/v14b/proofs/center-alignment.png)
- [参照入りの比較・PRIVATE](../../generated/v14b/private/reference-mouths-PRIVATE.png)：Git管理外。

v12〜v14の比較は既存v14の確認図をそのまま使用し、同じ切り抜き範囲・倍率のv14bを追加した。v14/v14b単独比較とv14bの各状態は今回の層一式から合成した。

## 入力と生成指示

v14で使ったv11通常表示の閉口顔をバイト単位で複製して使用。頭部 `(318,236)–(1854,1772)` を1254×1254にした入力で、開いたv14の口は生成入力にしていない。別添えの非公開 `.local/reference/anime-mouth-zoom.png` は口内色と線の参考のみ。

全3回で「正面の左右対称の口」「左右の口角を同じ高さ」「口の中心を鼻・顎の中心の真下へ」「参照の斜め向きや傾斜した形は再現しない」「口以外を維持」と明示。形・大きさの数値指定はせず、自然でかわいい大きく開いた口を求めた。実際の全プロンプトと生成IDは [generation-log.json](../../generated/v14b/generation-log.json) に保存。

|候補|口角高低差・入力px|選定理由|
|---|---:|---|
|旧v14|7|左口角が上。色判定によって7〜8px。|
|large-01・採用|0|全判定条件で0px。新候補で横幅が最も控えめ、柔らかい丸みと淡いピンクが顔になじむ。|
|large-02|0|外形はほぼ対称だが横幅が広い。色判定により0〜2px程度の差。|
|large-03|0|口角はそろうが横幅が最も広い。片側の小さな歯と口内の色分けにも左右差がある。|

採用原画は [large-01.png](../../generated/v14b/selected/large-01.png)。歯は新しい生成絵には描かれていない。追加や補描はしていない。小口の原画はv14から記録用に複製しただけで、再生成も素材の再抽出もしていない。

## 口角の測定

左右は画面上の左右。口の近傍のみで `R−G>12` かつ `G<224` の最大連結領域を取り、左右端それぞれ3列における輪郭上端yの中央値を口角の高さとした。口の側壁全体の重心ではなく、上下の唇が接する上端を測る。[測定スクリプト](../../../../scripts/live2d/v14b/measure.py)／[測定データ](../../generated/v14b/extraction/corner-measurements.json)。

採用絵の口角は左 `(597,805)`、右 `(689,805)`。高さの差 **0px**。逆変換後は左 `(1049.25,1222.03)`、右 `(1161.94,1222.03)`、差 **0px**。色差閾値を8・12・16・20へ変えても差は0pxで、輪郭の見た目とも一致した。ぼかしやアンチエイリアスがあるため、測定精度はおよそ入力1px単位であり、全画素が鏡写しという意味ではない。

旧v14の同じ測定では左 `(600,805)`、右 `(684,812)`、差7入力px＝約8.57キャンバスpx。前回報告の「約11px」は閉口からの口角中心の上下移動であり、今回の左右差とは別の値。

鼻と顎は元の絵でも厳密な同一x座標ではないため、未変更のNose層とFace_Skinの顎下端から両者を結ぶ中心線を求めた。新しい口の外接枠中心 `(643,832)` と、その高さでの鼻・顎中心線とのずれは約 **{measurements['centering']['horizontal_offset_from_axis_input_px']:.2f}入力px／{measurements['centering']['horizontal_offset_from_axis_canvas_px']:.2f}キャンバスpx**。位置を修正する処理はしていない。

## 透明素材化と層

抽出方法はv14と同じ。入力と生成画像の差分を口の領域だけに限定し、閉口線を覆う部分も含める。穴埋めで口内・輪郭・肌を一体化し、不透明余白6入力pxと外側9入力pxのなだらかなalphaを作る。RGBは生成原画のまま。1254→1536の入力切り抜きの逆変換を行い、2172×2896キャンバスの `(318,236)` に戻す。

左右反転、片側の複製、変形、回転、口だけの拡縮・移動による対称化は一切していない。歯や舌は分割せず、`Mouth_Large.png` 一枚にした。小口は `Mouth_Small.png` をv14からそのまま複製。透明素材は周囲の肌を含むので、暗い背景では白い肌の縁が見える。v11/v14の肌に重ねるための素材。

54層一式、[manifest](psd-manifest.json)、[表示状態](layer-state.json)、[layers.md](layers.md)、[PSD作成ラッパー](../../../../scripts/live2d/v14b/build_psd_with_state.py)を用意。outは `assets/ciel/psd/ciel-v14b`。閉口線と口まわりの肌を下に残し、開口素材で覆うv14の表示契約を維持。Small/Largeは同時表示しない。

## 検証と残る点

- 既存{len(hashes)}ファイルのハッシュ不変を確認。小口・閉口の合成はv14と全画素一致。
- 大口素材の外側はv11と全画素一致。閉口線は全画素がalpha=255で覆われる。
- 同じ逆変換をした生成原画と、不透明な口内部の差は最大{metrics['inverse_space_opaque_core_max']}階調。入力サイズへの往復縮小後の平均差も約{metrics['input_space_opaque_core_mae']:.2f}階調（0〜255）。
- 生成時に口以外へ生じた微細な変化は使っていない。口の見た目は原画を再現し、それ以外は元の層を保持する。
- [validation.json](validation.json)に寸法・層の同一性・口外不変・口角差・非公開図のGit除外・アニメーション4フレームの検査結果。

左右の口角の持ち上がり差は解消したが、生成絵の柔らかい輪郭や微細な色むらはそのまま残した。閉口から大口へは上唇も上がる表情変化があり、絶対的な口角位置まで固定したリグではない。Cubism上の中間開度やリップシンク動作は未検証。PSD/XCF本体も今回の書き込み範囲外なので未作成。

再実行は `prepare.py`（入力複製・元ファイル記録）、`measure.py`（候補測定）、`build.py`（素材・層・確認図）、`validate.py`（検査と報告）の順。共通の差分抽出処理はv14から複製した `common.py`。全スクリプトは `scripts/live2d/v14b/` 内に保存。

書き込みは指定のv14b三ディレクトリのみ。画像生成ツール自身の既定キャッシュは `C:/Users/prog/.codex/generated_images/` で、出力をv14bへ複製した。非公開図は `generated/v14b/private/` に置き、PRIVATEを付け、v14b内の.gitignoreで除外した。
'''
    (LAY/'report.md').write_text(report,encoding='utf-8')
    print(result)

if __name__=='__main__':main()
