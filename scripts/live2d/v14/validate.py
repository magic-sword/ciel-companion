"""Validate the delivered PNG set and write the v14 handoff documentation."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from build import ROOT, GEN, LAY, PROOF, SIZE, CLOSED, read, write

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    state=read(LAY/'layer-state.json')
    manifest=read(LAY/'psd-manifest.json')
    metrics=read(GEN/'extraction/metrics.json')
    sources=read(GEN/'inputs/source-hashes.json')
    assert all(sha(ROOT/p)==h for p,h in sources.items()), 'Original input changed'
    assert len(state['layers'])==54
    assert len({r['name'] for r in state['layers']})==54
    assert manifest['out']=='assets/ciel/psd/ciel-v14'
    assert manifest['layers']==[{k:r[k] for k in ('name','path')} for r in state['layers']]
    unchanged=[]
    for row in state['layers']:
        path=ROOT/row['path']
        with Image.open(path) as im:
            assert im.size==SIZE and im.mode=='RGBA',row['name']
            assert im.getextrema()[3][0]==0,row['name']
        if row['name'] not in ('Mouth_Small','Mouth_Large'):
            assert sha(path)==sha(ROOT/'assets/ciel/layers/v11'/path.name)
            unchanged.append(row['name'])
    assert len(unchanged)==52
    assert sum(r['visible'] for r in state['layers'])==50
    assert list(r['z'] for r in state['layers'])==sorted(r['z'] for r in state['layers'])
    for r in state['layers']:
        assert not r.get('clip') or r['clip'] in {q['name'] for q in state['layers']}
    base=np.asarray(Image.open(GEN/'inputs/v11-neutral.png'))
    assert np.array_equal(base,np.asarray(Image.open(PROOF/'closed-composite.png')))
    closed_ink=np.zeros((SIZE[1],SIZE[0]),bool)
    for name in ('Mouth_Line_Upper','Mouth_Line_Lower'):
        closed_ink|=np.asarray(Image.open(LAY/(name+'.png')))[:,:,3]>0
    coverage={}
    for m in ('small','large'):
        rgba=np.asarray(Image.open(LAY/f'Mouth_{m.title()}.png'))
        alpha=rgba[:,:,3]
        actual=np.asarray(Image.open(PROOF/f'{m}-composite.png'))
        assert np.array_equal(actual[alpha==0],base[alpha==0]),m
        assert np.all(alpha[closed_ink]==255),'Closed line not covered'
        assert metrics[m]['inverse_space_opaque_core_max']<=1
        assert metrics[m]['input_space_opaque_core_mae']<1
        coverage[m]={'closed_line_pixels_fully_covered':int(closed_ink.sum()),
                     'alpha_bbox':list(Image.fromarray(alpha).getbbox()),
                     'feather_pixels':int(np.count_nonzero((alpha>0)&(alpha<255)))}
    for filename in ('mouth-switch.gif','mouth-switch.png'):
        with Image.open(PROOF/filename) as im:
            assert im.n_frames==4 and im.info['loop']==0
    assert read(GEN/'generation-log.json')['count']==8
    private=list((GEN/'private').glob('*.png'))
    assert private and all('PRIVATE' in p.name for p in private)
    ignore=subprocess.run(['git','check-ignore','--',*[p.relative_to(ROOT).as_posix() for p in private]],cwd=ROOT,capture_output=True,text=True,check=True)
    assert len(ignore.stdout.strip().splitlines())==len(private)
    for p in Path(__file__).parent.glob('*.py'):
        ast.parse(p.read_text(encoding='utf-8'))
    result={'passed':True,
            'scope':'Asset integrity, compositing, file preservation and privacy checks. Does not certify visual acceptance or zero mouth-corner motion.',
            'zero_corner_motion_achieved':False,
            'layer_count':54,'default_visible':50,'unchanged_v11_layer_count':52,
            'original_input_files_unchanged':len(sources),'closed_equals_v11':True,
            'outside_patch_unchanged':True,'coverage':coverage,'private_gitignored':True,
            'generation_count':8,'generation_limit':12,'psd_export_run':False,
            'position_note':'No post-generation mouth move or deformation. Generated large mouth corners rise approximately 10.7 canvas pixels relative to closed.'}
    write(LAY/'validation.json',result)
    rows=['# v14 レイヤー一覧','',
          '2172×2896 RGBA、54層。下から上の順。v11の開口10層を一体素材2層に置換。残る52層はバイト単位で同じ。','',
          '## 口の切り替え','',
          '- 閉口：`Mouth_Small`・`Mouth_Large` ともOFF。',
          '- 小口：`Mouth_Small` のみON。',
          '- 大口：`Mouth_Large` のみON。',
          '- `Mouth_Skin_Upper/Lower`・`Mouth_Line_Upper/Lower` は常時ON。開口素材が閉口線を完全に覆う。',
          '- Small/Largeは同時表示しない。肌を含むため、それぞれ不透明度100%で使用。',
          '- 閉眼：左右の `Eye_*_Closed` をON、他のEye層をOFF。口状態は独立。','',
          '口の中・歯・舌・輪郭は生成画素を一体で保存。分割なし。新しい口素材のクリップ先はなし。',
          '表情プリセットと表示リストは `layer-state.json` に記載。従来のmouth_closedグループのみをOFFにする汎用処理ではなく、v14のmouth_switchを使う。','',
          '## PSD','',
          '`psd-manifest.json` の out は `assets/ciel/psd/ciel-v14`。',
          '[GIMP 3作成ラッパー](../../../../scripts/live2d/v14/build_psd_with_state.py)を同梱。PSD出力先は今回の書き込み許可範囲外のため未実行。','',
          '|順|名前|通常表示|出典・担当|クリップ|','|---:|---|---|---|---|']
    for i,r in enumerate(state['layers'],1):
        desc='v11そのまま' if r['name'] in unchanged else r['description']
        rows.append(f"|{i}|{r['name']}|{'ON' if r['visible'] else 'OFF'}|{desc}|{r.get('clip') or 'なし'}|")
    (LAY/'layers.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    report='''# v14：顔の中で生成した口を一体素材にする

小口 **small-03**、大口 **large-04** を採用。生成は小口4回・大口4回の **計8回／上限12回**。閉口はv11のまま。生成した口を数式で描き直す、口だけを縮小する、口だけを移動する処理はしていない。

## まず見る図

- [閉口／小口／大口の顔全体](../../generated/v14/proofs/three-states.png)
- [v12・v13・v14の同倍率比較](../../generated/v14/proofs/v12-v13-v14.png)
- [生成された顔／素材を重ねた顔](../../generated/v14/proofs/generated-vs-composite.png)
- [同じ比較の口拡大](../../generated/v14/proofs/generated-vs-composite-mouth.png)
- [素材単体：明背景／暗背景](../../generated/v14/proofs/parts-light-dark.png)
- [閉口→小→大→小 GIF](../../generated/v14/proofs/mouth-switch.gif)／[色量子化のないAPNG](../../generated/v14/proofs/mouth-switch.png)
- [全8候補の顔](../../generated/v14/proofs/candidates.png)
- [参照の口との比較・PRIVATE](../../generated/v14/private/reference-mouths-PRIVATE.png)：Git管理外。

顔の比較は全て同じ頭部範囲を同倍率で表示。v12・v13は各バージョンのlayer-stateから合成し、口まわりの肌を常時表示する元の契約も維持した。

## 入力と生成

v11の通常表示50層を下から重ね、頭部 `(318,236)–(1854,1772)` を切り抜いて1254×1254に縮小。[入力](../../generated/v14/inputs/v11-face-closed.png)は閉口だけ。参照は非公開の `.local/reference/anime-mouth-zoom.png` を別画像として渡した。元の `.local/reference/anime-cleaning.webp` も目視確認。

毎回同じ閉口画像から独立生成し、「口だけを小さく／大きく開く」「その他は維持」「自然でかわいい形は自由」「参照は淡い口内色と繊細な線の参考」と指示。数値で幅・高さ・比率・輪郭を指定していない。最後の大口では口角の高さ維持も言葉で指示したが、完全には従わなかった。

|候補|評価|
|---|---|
|small-01|輪郭は明瞭だが小口としては開きが深い。|
|small-02|横幅は控えめだが、小口としては縦に開きすぎる。|
|small-03・採用|最も浅い開きで閉口からつながる。柔らかいピンクが自然。輪郭の柔らかさは残る。|
|small-04|線は比較的明瞭だがsmall-03より笑顔寄りで開きが深い。|
|large-01|縦の開きは自然だが、他の大口候補より横幅が広い。|
|large-02|控えめな横幅だが縦に深く、輪郭も柔らかい。|
|large-03|整った線と小さな歯。ただし横幅が大きく、今回の不満に対する改善幅が小さい。|
|large-04・採用|大口の中で横幅が最も控えめ。小さな歯と淡い舌が顔に収まり、顎までの余白もある。口角のわずかな上がり・左右差は残る。|

生成記録は [generation-log.json](../../generated/v14/generation-log.json)。採用原画は `generated/v14/selected/` に保存。全候補は `generated/v14/candidates/` に保存（既存のGit除外規則の対象）。アニメの参照画素は素材へ転写していない。

## 透明素材の作り方

[prepare.py](../../../../scripts/live2d/v14/prepare.py) と [build.py](../../../../scripts/live2d/v14/build.py) を保存。Pythonは入力合成、差分検出、切り抜き、透明化、逆変換、確認図作成に使用した。

1. 入力と生成画像のRGB差分を求め、口付近だけに限定する。目・鼻・髪・顎の差分は採用しない。
2. 差分8階調超の連結領域と元の閉口線を合わせ、穴を埋める。これにより歯の白や肌色に近い部分も欠けず、閉口線が完全に覆われる。
3. 口・歯・舌・輪郭と近傍の変わった肌を生成原画のRGBのまま保持。抽出領域の外側に6入力pxの不透明余白を取り、その外側9入力pxでsmoothstepによりalphaを0へ落とす。数値は抽出用で、生成する口の形の指定ではない。
4. 1254×1254を1536×1536へ戻し、2172×2896キャンバスの `(318,236)` へ置く。逆変換は `x=318+u×1536/1254, y=236+v×1536/1254`。口だけの拡大縮小・平行移動・変形はしない。
5. v11閉口線・口まわり肌を下に残し、開口素材で覆う。素材外の肌を変えずに済む。歯や舌は無理に分割しない。

口内だけの切り抜きではなく、ご指定の周囲肌を含む素材。暗い背景で肌の白い縁が見えるのはそのため。v11の肌へ重ねた際に縁がなじむ構成で、任意の肌色へそのまま流用する用途ではない。

## 層と検査

v11の62層から従来の開口10層を除き、`Mouth_Small`・`Mouth_Large` を追加した **54層**。非口48層＋閉口・肌4層の計52層はv11とSHA256一致。通常50層ON、開口2層・閉眼2層OFF。[全層一覧と切替](layers.md)／[manifest](psd-manifest.json)／[表示状態](layer-state.json)。

採用した口の見える色領域は、逆変換後の概算で小口91×33px、大口107×82px。これは生成後の測定値。肌と透明な縁を含む素材の外接枠とは異なる。

閉口合成はv11と全画素一致。開口合成も口素材のalpha=0の場所はv11と全画素一致。閉口線の全画素は素材のalpha=255に覆われる。逆変換後の不透明な口内部は、同じ逆変換をかけた生成原画と最大1階調差。入力サイズへ再縮小した比較でも不透明部平均差は小口約0.36・大口約0.70階調（0〜255）で、拡大図で口の見た目を確認した。

生成原画自体では口以外も微細に変わっている（口外の平均RGB差は約2階調）。その画素は素材へ入れていない。このため生成した顔全体と完全な画素一致を求めるのではなく、口は原画を再現し、他の部位はv11を保持する。詳細は [metrics.json](../../generated/v14/extraction/metrics.json)。

元の221入力ファイルの不変、54枚のRGBA寸法、52枚の同一性、表示順、閉口線被覆、口外不変、アニメ参照入り図のGit除外、4フレームのGIF/APNGを [validate.py](../../../../scripts/live2d/v14/validate.py) で検証。[validation.json](validation.json)。

## 位置の確認と残る問題

素材化に由来する座標ずれはない。閉口／小口／大口の推定口角中心xは約1106.4／1108.6／1104.5pxで、左右方向の違いは閉口から約2px。口の開きに伴う下端の移動と区別するため、色領域の重心ではなく左右端の帯から口角中心を推定した。

ただし大口の推定口角中心yは1235.6px、閉口は1246.3pxで、**大口の口角が約10.7px上がる**。小口は1244.9px。520px幅の確認図では大口の差は約3.6px相当。切替図で確認できるため、「位置が完全に跳ばない」は未達の点として残す。生成の口を忠実に使うため、事後の移動で隠していない。口の位置を厳密固定する場合は、原画の再生成か別途リグでの調整が必要。

小口は生成原画の輪郭が柔らかく、大口には軽い左右差がある。3状態の切替素材であり、中間開度のモーフやCubism上のリップシンク動作は未検証。

PSD作成ラッパーを同梱し、manifestのoutは `assets/ciel/psd/ciel-v14`。今回の書き込み範囲外なのでPSD/XCF実体は未作成。GIMP/Cubismでの読込検証は未実施。

作業用ファイルの書き込みは指定のv14三ディレクトリ内。画像生成ツールには別途、自動保存先 `C:/Users/prog/.codex/generated_images/` があり、ツール出力をv14へコピーした。ツールの既定キャッシュ先は変更できない。既存ファイルは変更していない。非公開図は `generated/v14/.gitignore` の `/private/` で除外し、ファイル名にPRIVATEを付けた。
'''
    (LAY/'report.md').write_text(report,encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
