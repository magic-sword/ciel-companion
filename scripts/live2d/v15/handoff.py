"""Write material provenance, layer documentation and the deferred PSD wrapper."""
import sys
sys.dont_write_bytecode=True
from build import *

DETAILS={
 'Hair_Back':('v14c/Hair_Back.png','頭部の画素をy1400まで保持。下半分を中心x1086に向けて滑らかに最大14%縮幅。','顔・耳・前髪・体','頭XY＋後ろ髪揺れ'),
 'Body':('v15/parts/body-01.png','肩・上腕・ホルターの黒縁・白いトップス・菱形・腹部・腰帯・スカートを一体で再生成。上着の下の腰と裾に40pxの下地を補完。','首・上着・ファー・横髪・首輪','体の傾き＋呼吸。宝石と腰帯も同じ層'),
 'Neck':('v14c/Neck.png','顎下までの既存首を維持し、y1470以降の旧い裾を除去。新Bodyの首元と50px重ねる。','顔・首輪','首／頭の付け根'),
 'Neck_Shadow_Chin':('v14c/Neck_Shadow_Chin.png','承認済み顔につながる顎影を保持。首の新しい下端へクリップ。','顔・首輪','首＋頭XY、Neckへクリッピング'),
 'Outer_R':('v15/parts/outer-02.png','画面左。肩を覆う高いファーを再描画し、初稿と二稿の合成比較から量感を補正。上着・袖・裏地は一体。','手前の横髪','肩・体の傾き＋呼吸'),
 'Outer_L':('v15/parts/outer-02.png','画面右。画面左と同一生成キャンバスから分離。肩外側へ下がるファー、白い袖とシアンの裏地。','手前の横髪','肩・体の傾き＋呼吸'),
 'Choker_Back':('v14c/Choker_Back.png','後帯を48px下げ、元絵の首後ろの高さへ合わせる。','首・前帯','首輪の共通親'),
 'Choker_Inside':('v14c/Choker_Inside.png','楕円形の首輪内側の暗部。後帯と一緒に48px下げる。首輪下の三角とは別。','Neck・Choker_Front','首輪の共通親'),
 'Choker_Front':('v15/parts/choker-front-01.png','前帯を再生成。旧金具の輪郭と下端の白い残片を除去し、金具の下まで連続する帯にした。','Choker_Buckle','首輪の共通親＋帯の曲げ'),
 'Choker_Buckle':('v14c/Choker_Buckle.png','前帯に合わせて縦位置・高さを補正。幅と中心x1116は保持。','なし','首輪追従、剛性を保つ'),
 'Choker_Pendant':('v14c/Choker_Pendant.png','黒い三角と接続タブを延長し、丸飾りを元絵の高さへ。上端の旧金具残片を除去。','上端は前帯・金具','首輪の共通親＋小さな飾り揺れ'),
}

def main():
    state=read(LAY/'layer-state.json')
    for r in state['layers']:
        n=r['name']
        if n in DETAILS:
            source,description,hidden,motion=DETAILS[n]
            r.update(source=source,description=description,hidden_by=hidden,motion=motion)
    write(LAY/'layer-state.json',state)
    transforms={
      'Body':{'source':'assets/ciel/generated/v15/parts/body-01.png','uniform_scale':1.10,'translate':[553,1286],'alpha_cut_above_y':1420,'hidden_undercoat_extension':{'start_y':2300,'side_extension_px':40,'color_source':'18px inside the generated silhouette on the same row','neutral_mask':'Outer alpha >=250'}},
      'Outer_R/Outer_L':{'source':'assets/ciel/generated/v15/parts/outer-02.png','source_y':[0,130,280,430,610,1082],'target_y':[0,90,225,400,610,1082],'upper_fur_x_scale':'1+0.16*(1-clamp((source_y-130)/480,0,1))','x_pivots':[160,1294],'full_canvas_scale':'2172/source_width','translate':[0,1280],'split_canvas_x':1086,'reason':'二稿の肩露出が原画より大きかったため、袖を固定してファー上部の量感を戻す。'},
      'Hair_Back':{'source':'assets/ciel/layers/v14c/Hair_Back.png','fixed_y_max':1399,'center_x':1086,'x_scale':'1 - 0.14*smoothstep(clamp((y-1400)/1000,0,1))','reason':'頭の外形を維持し、胴の左右だけを細くする。'},
      'Neck/Neck_Shadow_Chin':{'source':'v14c corresponding layers','keep_y_below':1470,'reason':'旧服の上を覆う首の裾を除去。顎側の描き足しは既存y1194から維持。'},
      'Choker_Back/Choker_Inside':{'source':'v14c corresponding layers','translate':[0,48]},
      'Choker_Front':{'source':'assets/ciel/generated/v15/parts/choker-front-01.png','crop':'largest connected component bounding box with antialias fringe','target_bbox':[931,1377,1303,1545],'anchors':'左右の前後帯の接点、中央x1117、金具下端1546'},
      'Choker_Buckle':{'source':'assets/ciel/layers/v14c/Choker_Buckle.png','source_y':[0,1428,1520,2896],'target_y':[0,1443,1546,2896]},
      'Choker_Pendant':{'source':'assets/ciel/layers/v14c/Choker_Pendant.png','source_y':[0,1490,1535,1660,2896],'target_y':[0,1520,1592,1723,2896],'cleaning':'disconnected debris removed; silver buckle remnant at y1490..1500 replaced using y1506 tab colors'},
    }
    sources={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (GEN/'parts').glob('*.png')}
    write(LAY/'placement.json',{'canvas':SIZE,'coordinates':'native 2172x2896; L/R are character perspective','transforms':transforms,'generated_source_sha256':sources,'selected':[p for p in sources if not p.endswith('outer-01.png')],'rejected':['assets/ciel/generated/v15/parts/outer-01.png'],'accepted_state':'composite visually inspected; translation checks in validation.json; not approved by user or rig-tested'})
    log={'count':4,'limit':30,'tool':'image_gen.imagegen','date':'2026-10-12','attempts':[
      {'id':1,'output':'parts/body-01.png','references':['inputs/torso-reference.png'],'prompt_summary':'元絵の胴だけを残し、髪・ファー・上着・首輪を外す。裸の肩、黒いホルター縁、白い服と菱形、裾、腹部、腰帯、スカートを維持し、隠れた肩と上腕を描く。','selected':True,'reason':'ホルターと肩のつながりを再建。菱形の寸法・高さと裾は合成で配置調整。'},
      {'id':2,'output':'parts/outer-01.png','references':['inputs/body-reference.png'],'prompt_summary':'元絵から左右の上着・ファー・シアンの裏地だけを一枚の透明キャンバスへ。隠れた上着を描き足す。','selected':False,'reason':'内側のファーが高く、合成でも肩を覆いすぎた。'},
      {'id':3,'output':'parts/outer-02.png','references':['inputs/body-reference.png','parts/outer-01.png'],'prompt_summary':'初稿の袖を保ち、ファーの内側の高い盛り上がりを除去。肩の外側へ下がる形へ。','selected':True,'reason':'肩を露出できた。原画より開きすぎた量は上部だけの幾何補正で戻した。'},
      {'id':4,'output':'parts/choker-front-01.png','references':['inputs/choker-front-existing.png','inputs/choker-reference.png'],'prompt_summary':'前帯だけを透明で再生成。金具跡と白い残片を消し、黒い上下縁とシアンの連続面を整える。後帯・金具・丸飾りは含めない。','selected':True,'reason':'金具が動いたときに旧輪郭が露出する問題を解消。'}]}
    write(GEN/'generation-log.json',log)
    lines=['# v15 層一覧','', '2172×2896 RGBA。v14cと同じ54層、以下は奥→手前。L/Rはキャラクター視点。顔の43層はファイル単位でコピー。','', '| 順 | 層 | 通常表示 | 担当・変更 | 動き |','| --- | --- | --- | --- | --- |']
    for i,r in enumerate(state['layers']):
        n=r['name'];desc=r['description'] if n in DETAILS else 'v14cから変更なし'
        lines.append(f"| {i+1} | `{n}` | {'表示' if r['visible'] else '非表示'} | {desc} | {r['motion']} |")
    lines+=['','影・目のクリッピング、表情切り替え、口差分の表示条件は`layer-state.json`のv14c設定をそのまま継承。','',
      'Bodyは肩・上腕・服・胸の菱形・腹部・腰帯・スカートを含む。Outer_L/Rはファー・上着・袖・裏地を含む。今回は追加層なし。',
      '呼吸・体の傾きはBodyとOuterを共通の親へ。首輪の5層は共通親に置き、丸飾りの揺れは接続タブの根元を固定する。±15px図は素材の平行移動確認であり、リグの変形確認ではない。','',
      '再現: `python scripts/live2d/v15/build.py` → `python scripts/live2d/v15/handoff.py` → `python scripts/live2d/v15/verify.py`。同時に実行しない。','',
      'PSD: `scripts/live2d/v15/build_psd_with_state.py`をGIMP 3のpython-fu-evalで実行するラッパーを同梱。`CIEL_PROJECT_ROOT`にプロジェクトの絶対パスを指定。出力先は`assets/ciel/psd/ciel-v15`。今回の書込み許可範囲外なので実行していない。']
    (LAY/'layers.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    wrapper=(ROOT/'scripts/live2d/v14c/build_psd_with_state.py').read_text(encoding='utf8').replace('v14c','v15')
    (ROOT/'scripts/live2d/v15/build_psd_with_state.py').write_text(wrapper,encoding='utf8')
    print('Wrote state descriptions, placement, generation log, layers.md and PSD wrapper.')

if __name__=='__main__':main()
