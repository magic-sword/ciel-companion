"""Verify that v14c changes ONLY two fang patches, then write handoff docs."""
import ast
import hashlib
import numpy as np
from PIL import Image
from common import ROOT,GEN,LAY,PROOF,SIZE,read,write,ndi

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    hashes=read(GEN/'inputs/source-hashes.json')
    assert all(sha(ROOT/p)==h for p,h in hashes.items()),'Prior source changed'
    state=read(LAY/'layer-state.json')
    previous=read(ROOT/'assets/ciel/layers/v14b/layer-state.json')
    manifest=read(LAY/'psd-manifest.json')
    assert manifest['out']=='assets/ciel/psd/ciel-v14c'
    assert len(state['layers'])==54
    assert manifest['layers']==[{k:r[k] for k in ('name','path')} for r in state['layers']]
    assert [r['name'] for r in state['layers']]==[r['name'] for r in previous['layers']]
    assert state['presets']==previous['presets'] and state['mouth_switch']==previous['mouth_switch']
    unchanged=[]
    for row,old in zip(state['layers'],previous['layers']):
        im=Image.open(ROOT/row['path'])
        assert im.mode=='RGBA' and im.size==SIZE and im.getextrema()[3][0]==0
        assert all(row[k]==old[k] for k in ('name','z','visible','clip','group'))
        if row['name']!='Mouth_Large':
            assert sha(ROOT/row['path'])==sha(ROOT/old['path'])
            unchanged.append(row['name'])
    assert len(unchanged)==53
    old=np.asarray(Image.open(ROOT/'assets/ciel/layers/v14b/Mouth_Large.png'))
    new=np.asarray(Image.open(LAY/'Mouth_Large.png'))
    tooth=np.asarray(Image.open(GEN/'extraction/paired-fangs.png'))
    support=tooth[:,:,3]>0
    change=np.any(old!=new,axis=2)
    assert np.array_equal(old[:,:,3],new[:,:,3]),'Mouth alpha changed'
    assert np.array_equal(old[~support],new[~support]),'Change outside teeth'
    assert np.array_equal(support,change)
    assert np.all(old[:,:,3][support]==255)
    # Mouth exterior and its edge are protected even where enamel meets the lip.
    rgb=old[:,:,:3].astype(np.int16)
    mouth=(rgb[:,:,0]-rgb[:,:,1]>12)&(rgb[:,:,1]<224)&(old[:,:,3]>128)
    assert np.all(ndi.binary_erosion(ndi.binary_fill_holes(mouth))[support]),'Fang crossed outline'
    # Exact mirrored enamel geometry/RGB, not a mirrored or changed base mouth.
    tile=tooth[1218:1235,1048:1164]
    assert np.array_equal(tile,tile[:,::-1]),'Fangs not symmetric'
    labels,n=ndi.label(support);assert n==2
    teeth=[]
    for i in range(1,n+1):
        yy,xx=np.where(labels==i)
        teeth.append({'bbox_canvas':[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)],
                      'width':int(xx.max()-xx.min()+1),'height':int(yy.max()-yy.min()+1),'pixels':int(len(xx))})
    actual=np.asarray(Image.open(PROOF/'large-composite.png'))
    target=np.asarray(Image.open(GEN/'selected/edited-full-canvas.png'))
    assert np.array_equal(actual,target),'Layer reconstruction differs from edited face'
    old_face=np.asarray(Image.open(ROOT/'assets/ciel/generated/v14b/proofs/large-composite.png'))
    assert np.array_equal(actual[~support],old_face[~support])
    for m in ('closed','small'):
        assert np.array_equal(np.asarray(Image.open(PROOF/f'{m}-composite.png')),
                              np.asarray(Image.open(ROOT/f'assets/ciel/generated/v14b/proofs/{m}-composite.png')))
    corners=read(GEN/'extraction/corner-measurements.json')
    assert corners['v14b']==corners['v14c']
    assert corners['v14c']['height_difference_input_px']==0
    for name in ('mouth-switch.gif','mouth-switch.png'):
        with Image.open(PROOF/name) as im:assert im.n_frames==4
    assert read(GEN/'generation-log.json')['count']==0
    for p in (__import__('pathlib').Path(__file__).parent).glob('*.py'):
        ast.parse(p.read_text(encoding='utf-8'))
    result={'passed':True,'generation_count':0,'layer_count':54,'unchanged_v14b_layers':53,
      'prior_files_unchanged':len(hashes),'changed_pixels_in_mouth_layer':int(change.sum()),
      'changed_pixels_outside_teeth':0,'mouth_alpha_identical':True,'mouth_outer_edge_unchanged':True,
      'fangs_exactly_mirrored':True,'teeth':teeth,'small_and_closed_equal_v14b':True,
      'edited_face_equals_layer_composite':True,'corner_height_difference_input_px':0,
      'corner_positions_and_mouth_bbox_equal_v14b':True,'psd_export_run':False}
    write(LAY/'validation.json',result)
    rows=['# v14c レイヤー一覧','',
          '2172×2896 RGBA、54層、下から上。Mouth_Largeの八重歯だけ変更。残る53層はv14bとSHA256一致。','',
          '- 閉口：Mouth_Small・Mouth_LargeともOFF。',
          '- 小口：Mouth_SmallのみON。',
          '- 大口：Mouth_LargeのみON。',
          '- Mouth_Skin_Upper/Lower・Mouth_Line_Upper/Lowerは常時ON。開口素材で閉口線を覆う。',
          '- Small/Largeは不透明度100%で排他表示。歯もMouth_Large内に統合。',
          '- 閉眼：Eye_L_Closed・Eye_R_ClosedをON、その他のEye層をOFF。',
          '- mouth_switchとpresetsはv14bを継承。','',
          'manifestのoutはassets/ciel/psd/ciel-v14c。[PSD作成ラッパー](../../../../scripts/live2d/v14c/build_psd_with_state.py)を同梱。PSD実体は未作成。','',
          '|順|名前|通常|内容|クリップ|','|---:|---|---|---|---|']
    for i,r in enumerate(state['layers'],1):
        rows.append(f"|{i}|{r['name']}|{'ON' if r['visible'] else 'OFF'}|{'小さな八重歯2本を追加' if r['name']=='Mouth_Large' else 'v14bそのまま'}|{r.get('clip') or 'なし'}|")
    (LAY/'layers.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    report=f'''# v14c：v14bの大口に小さな八重歯だけ追加

**v14の小さな八重歯をPythonで移植し、上側の口角寄りに左右対称の2本を追加した。画像生成は0回。** v14bから変わったのは歯の合計{int(change.sum())}画素だけ。口の形・大きさ・位置・口角・歯以外の口内色・素材のalphaはそのまま。

## 確認図

- [v14・v14b・v14cの大口：顔全体と口拡大](../../generated/v14c/proofs/v14-v14b-v14c-large-with-zoom.png)
- [大口の顔だけ](../../generated/v14c/proofs/v14-v14b-v14c-large.png)／[口拡大だけ](../../generated/v14c/proofs/v14-v14b-v14c-mouth.png)
- [閉口／小口／大口](../../generated/v14c/proofs/three-states.png)
- [八重歯を足した顔とレイヤー合成](../../generated/v14c/proofs/edited-face-vs-composite.png)／[同じ比較の口拡大](../../generated/v14c/proofs/edited-face-vs-composite-mouth.png)
- [素材単体：明暗背景](../../generated/v14c/proofs/parts-light-dark.png)
- [歯だけの差分](../../generated/v14c/proofs/tooth-only-difference.png)
- [口角の高さの確認](../../generated/v14c/proofs/corner-measurements.png)
- [切替GIF](../../generated/v14c/proofs/mouth-switch.gif)／[APNG](../../generated/v14c/proofs/mouth-switch.png)

比較は各版の同じ頭部範囲・同倍率。v14・v14bは保存済みの各版の合成顔、v14cは今回の54層から合成した顔を使用。

## 方法を選んだ理由

今回の優先事項は、すでに良いと評価されたv14bの口を保ち、小さな歯だけを足すこと。v14に自然な小さな八重歯の画素があるため、再生成よりも形・色・位置を厳密に維持できる移植を選んだ。新たな歯を数式で描かず、v14の歯を実寸で再利用している。

実際の処理は [transplant.py](../../../../scripts/live2d/v14c/transplant.py)。供給元は `assets/ciel/layers/v14/Mouth_Large.png` の `(1131,1231)–(1144,1238)`。肌を含まない歯の近傍13×7pxから、明るく色差の小さい画素を透明度付きで抽出した。alphaは `clip((G−180)/55,0,1)`、`R−G>45` を除外。歯のRGBは供給元の値を保持し、境界の混ざった画素だけ部分透明になる。

その歯を右へ置き、**歯だけ**を水平反転した複製を左へ配置。口の鏡映軸x=1105.5に対して両方の歯の形・RGB・alpha・高さは厳密に鏡写し。歯に拡大縮小・回転は加えていない。口本体を反転・変形・再描画する処理はない。

実際の可視領域は1本 **9×6px、38画素**（2172×2896キャンバス上）。左の外接枠は `(1061,1223)–(1070,1229)`、右は `(1142,1223)–(1151,1229)`。v14の歯と同じ実寸の控えめな2本で、顔全体では小さなアクセントになる。抽出・配置の詳細は [transplant.json](../../generated/v14c/extraction/transplant.json)。

## 口の透明素材と層

v14bの `Mouth_Large.png` を直接基準にして歯だけを合成し、元のalphaをそのまま保持した。したがって、以前の顔切り抜き→2172×2896への座標変換、口の輪郭、周囲肌のなだらかな透明縁は一切再計算していない。歯は既存の不透明な口内に収まり、元の口の外縁には触れていない。

`Mouth_Small`、閉口線、口まわりの肌、そのほかの53層はv14bからバイト単位で複製。54層構成と表示切替を維持し、八重歯は `Mouth_Large` 内へ統合した。作業用の [歯2本だけの透明画像](../../generated/v14c/extraction/paired-fangs.png) も保存しているが、manifestへ追加するレイヤーではない。

[psd-manifest.json](psd-manifest.json)／[layer-state.json](layer-state.json)／[layers.md](layers.md)／[PSD作成ラッパー](../../../../scripts/live2d/v14c/build_psd_with_state.py) を用意。manifestのoutは `assets/ciel/psd/ciel-v14c`。

## 検証

- v14・v14bなど既存{len(hashes)}ファイルのハッシュ不変。v14cの53層がv14bとSHA256一致。
- 大口PNGで変わった画素は76。歯の範囲外はRGBA全画素一致。alphaは歯の中を含め全画素一致。
- 歯の全画素が口の輪郭より内側。左右の歯画像はRGB・alphaを含め厳密な鏡写し。
- 左右口角の座標はv14bと同じ、入力顔上で左 `(597,805)`・右 `(689,805)`。**口角の高さの差は0pxのまま**。口の色領域の外接枠と中心xも同一。[測定データ](../../generated/v14c/extraction/corner-measurements.json)。
- v14bの完成顔へ歯だけを足した画像と、v14cの層を重ねた顔が2172×2896の全画素で一致。
- 小口・閉口の完成顔はv14bと全画素一致。GIF/APNGは4フレーム。

[validation.json](validation.json) に検査結果、[validate.py](../../../../scripts/live2d/v14c/validate.py) に検証手順を保存。

## 残る点・再実行

歯は意図的にごく小さいため、顔を小さく表示すると目立たなくなる。口本体の微細な色むらや閉口から大口への表情変化はv14bを引き継ぐ。Cubism上でのリップシンクや中間開度は未検証。PSD/XCF本体は今回の書き込み範囲外のため未作成で、作成ラッパーまでを用意した。

再実行は `python scripts/live2d/v14c/prepare.py` → `python scripts/live2d/v14c/build.py` → `python scripts/live2d/v14c/validate.py`。buildが歯の移植も実行する。全スクリプトと作業画像は指定のv14c三ディレクトリ内に保存し、既存ファイルは変更していない。今回アニメの非公開参照画像を含む確認図は新規作成していない。
'''
    (LAY/'report.md').write_text(report,encoding='utf-8')
    print(result)

if __name__=='__main__':main()
