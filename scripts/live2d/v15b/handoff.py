"""Provenance, layer-state descriptions and deferred GIMP PSD wrapper for v15b."""
import sys
sys.dont_write_bytecode=True
from build import *

DETAILS={
 'Body':('首から肩へ伸びる黒い紐を除去した新規生成。胴幅を補正し、白いトップス・裾・腹部・腰帯・スカートをつなぐ。上着下の隠れ部分を拡張。','parts/body-02.png','肩・上着・首輪・手前髪','体の呼吸と傾き'),
 'Neck':('v15の首を保持し、顔に隠れる上端に24pxの下地を補完。','v15/Neck.png＋隠れ領域補完','顔・首輪','首・頭との接続'),
 'Outer_R':('画面左。上部のファーを保持し、胴幅に合わせて下側の開きを補正。','v15/Outer_R.png＋配置補正','手前髪','体・肩、Fur_Backと共通の親'),
 'Outer_L':('画面右。上部のファーを保持し、胴幅に合わせて下側の開きを補正。','v15/Outer_L.png＋配置補正','手前髪','体・肩、Fur_Backと共通の親'),
 'Choker_Back':('一体生成した首輪の後帯。内壁と前帯の下の暗い下地も持ち、首の奥を白く抜かない。','parts/choker-01.png','Neck・前帯・顔','首輪の共通親'),
 'Choker_Inside':('首輪下の黒い当て布。広い上端から柔らかく先細りする。丸飾りとは分離。','parts/choker-01.png','前帯・金具・丸飾り','首輪の共通親。飾りの揺れと独立'),
 'Choker_Front':('同じ一体生成の前帯。金具の下に連続した帯を補完。','parts/choker-01.png','金具','首輪の共通親＋帯の曲げ'),
 'Choker_Buckle':('同じ一体生成の銀縁の金具と縦二つのシアン留め具。','parts/choker-01.png','なし','首輪に追従、剛性を保つ'),
 'Choker_Pendant':('同じ一体生成の接続タブと丸飾り。黒い当て布は含めず、前帯の下へ接続タブを延長。','parts/choker-01.png','上端は前帯・金具','首輪追従＋接続根元を固定した揺れ'),
}

def main():
    state=read(LAY/'layer-state.json')
    for r in state['layers']:
        if r['name'] in DETAILS:
            desc,source,hidden,motion=DETAILS[r['name']]
            r.update(description=desc,source=source,hidden_by=hidden,motion=motion)
    write(LAY/'layer-state.json',state)
    sources={p.relative_to(ROOT).as_posix():sha(p) for p in (GEN/'parts').glob('*.png')}
    placement={'canvas':SIZE,'coordinates':'native pixels; L/R are character perspective',
      'sources_sha256':sources,'selected':['parts/body-02.png','parts/choker-01.png','parts/fur-back-01.png'],
      'Body':{'source_center_x':526,'target_center_x':1117,'source_y':[0,425,578,780,1020,1360,1507],'target_y':[1256,1724,1892,2200,2450,2790,2937],
       'base_x_scale':1.10,'scale_at_source_y':[0,400,600,780,960,1020,1150,1300,1507],'additional_x_scale':[1,1,1,1.05,1.26,1.26,1.12,1,1],
       'alpha_cut_above_y':1440,'color':'remove 80% of positive R-B; add 25% of that excess to B to neutralize warm skin tint',
       'hidden_padding':'At y>=2480, use a 1.14x horizontally enlarged paint donor only under Outer alpha>=250; neutral visible pixels remain covered'},
      'Outer_L_R':{'outward_offset_y':[0,1950,2100,2240,2450,2670,2896],'outward_offset_px':[0,0,0,20,85,45,0],
       'common_right_offset_y':[0,1950,2450,2670,2896],'common_right_offset_px':[0,0,31,31,0],'reason':'Open the waist and align the lower jacket opening with body center1117; upper fur remains fixed'},
      'Neck':{'source':'v15/Neck.png','hidden_under_face_margin_px':24,'mask':'Face_Skin alpha>=250, preserve all exposed neck pixels'},
      'Fur_Back':{'source':'parts/fur-back-01.png','crop':'main alpha component bbox','uniform_width':1330,'translate':[452,1370],'z':5,'between':['Hair_Back','Body']},
      'Choker':{'source':'parts/choker-01.png','source_center_x':745,'target_center_x':1117,'origin_y':1322,'scale_xy':[.30,.34],
       'pendant_scale_xy':[.34,.34],'separation':'back arc and dark lining; front surface; rounded buckle; dark throat fabric; connector and round pendant',
       'back_front_overlap_source_px':60,'hidden_connector_starts_source_y':580,'fabric_starts_source_y':580,'masks_and_fill':'Explicit source-space polygons and hidden fills in build.py; no additional output layers'},
      'status':'PNG composite inspected; +/-15px material tests in validation.json; not Cubism/Unity tested'}
    write(LAY/'placement.json',placement)
    log={'count':4,'limit':20,'tool':'image_gen.imagegen','date':'2026-10-12','attempts':[
      {'id':1,'output':'parts/body-01.png','references':['inputs/body-v15.png'],'selected':False,'prompt_summary':'黒い肩紐を取り除き、13歳程度の自然な胴に。白磁の肌・白い服・菱形・腰帯を維持し、肩と上腕を補う。','result':'紐は除けたが腰の細さが十分に減らなかった。'},
      {'id':2,'output':'parts/choker-01.png','references':['../v15/inputs/choker-reference.png'],'selected':True,'prompt_summary':'元絵の首輪を一体で生成。前後の楕円の帯、銀縁の金具、黒い当て布、タブと丸飾り。肩へ伸びる紐なし。','result':'同一の透視と彩色を持つ首輪として採用。既存5層へ分離。'},
      {'id':3,'output':'parts/fur-back-01.png','references':['inputs/fur-context-v15.png'],'selected':True,'prompt_summary':'首の後ろから左右の肩のファーへつながる、連続した横長の後ろ襟だけ。白と淡い青紫、透明背景。','result':'後ろ襟が一続きで、両端をOuterの下へ重ねられるため採用。'},
      {'id':4,'output':'parts/body-02.png','references':['parts/body-01.png'],'selected':True,'prompt_summary':'腰の幅をさらに広げ、極端なくびれと胸の強調を減らす。トップス・腹部・腰帯・スカートを自然につなぐ。','result':'再生成だけでは胴幅の改善が小さかったため、合成時に胴下半分の幅と上着の開きを数値補正して採用。'}]}
    write(GEN/'generation-log.json',log)
    lines=['# v15b 層一覧','', '2172×2896 RGBA。v15の54層に`Fur_Back`だけ追加し55層。既存54層の相対順・z・通常表示・クリップを維持。顔まわり43層を含む45層はv15からファイル単位でコピー。','',
      '| 順 | 層 | z | 通常表示 | 担当 | 動き |','| --- | --- | --- | --- | --- | --- |']
    for i,r in enumerate(state['layers']):
        desc=r['description'] if r['name'] in CHANGED+['Fur_Back'] else 'v15から変更なし'
        lines.append(f"| {i+1} | `{r['name']}` | {r['z']} | {'表示' if r['visible'] else '非表示'} | {desc} | {r['motion']} |")
    lines+=['','`Choker_Inside`の担当は黒い当て布へ変更。首輪内側の暗い面は`Choker_Back`が持つ。`Choker_Pendant`はタブと丸飾りのみ。リグ側でも当て布を丸飾りの揺れから分離する。','',
      '`Fur_Back`は`Hair_Back`の上、`Body`の下。Outer_L/Rと同じ上着の親へ。頭や後ろ髪に単独で追従させない。','',
      '再現：`python scripts/live2d/v15b/build.py` → `python scripts/live2d/v15b/handoff.py` → `python scripts/live2d/v15b/verify.py`。同時実行しない。','',
      'PSDラッパー：`scripts/live2d/v15b/build_psd_with_state.py`。GIMP 3のpython-fu-evalで実行し、`CIEL_PROJECT_ROOT`にリポジトリの絶対パスを指定する。出力は`assets/ciel/psd/ciel-v15b`。今回の書込み範囲外のためラッパーは未実行。']
    (LAY/'layers.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    wrapper=(ROOT/'scripts/live2d/v15/build_psd_with_state.py').read_text(encoding='utf8').replace('v15','v15b')
    (ROOT/'scripts/live2d/v15b/build_psd_with_state.py').write_text(wrapper,encoding='utf8')
    print('Wrote layer metadata, provenance, layers.md and PSD wrapper.')

if __name__=='__main__':main()
