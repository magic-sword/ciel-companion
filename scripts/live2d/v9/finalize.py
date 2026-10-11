"""Export explicitly reviewed candidate06 and static review-A proof sheets.

No generation calls, automatic candidate selection, PSD or rig modifications.
Run: python -I scripts/live2d/v9/finalize.py
"""
import sys
import copy
import shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build import *

def panel_backgrounds(im,box,scale,path):
    w,h=round((box[2]-box[0])*scale),round((box[3]-box[1])*scale)
    out=Image.new('RGB',(w*3,h+48),(40,44,58))
    for j,(color,label) in enumerate([((250,250,252,255),'白背景'),((128,128,138,255),'中間灰'),((18,22,34,255),'暗背景')]):
        out.paste(on_bg(im,color).crop(box).resize((w,h),Image.Resampling.LANCZOS),(j*w,48))
        ImageDraw.Draw(out).text((j*w+10,10),label,font=font(22),fill='white')
    out.save(path)

def measure(comp,layers):
    master=rgba(ROOT/'assets/ciel/master/ciel-upper-body-2x.png')
    v8=rgba(ROOT/'assets/ciel/layers/v8/_compose.png')
    result={'canvas':list(SIZE),'comparison_head_crop':list(HEAD),'measurements_are_auxiliary_not_aesthetic_scores':True}
    for n,im in [('master',master),('v8',v8),('v9',comp)]:
        a=np.asarray(im)
        result[n]={}
        for label,box in [('neck',(1080,1390,1150,1410)),('face',(1070,1170,1130,1200))]:
            x,y,u,v=box
            result[n][label]={'box':box,'mean_rgb':np.mean(a[y:v,x:u,:3],axis=(0,1)).round(2).tolist()}
        for side,box in [('Eye_R',(820,955,1020,1145)),('Eye_L',(1190,945,1400,1140))]:
            x,y,u,v=box
            sub=a[y:v,x:u,:3].astype(int)
            mask=(sub[:,:,2]-sub[:,:,0]>80)&(sub[:,:,1]>65)&(sub[:,:,2]>150)
            yy,xx=np.where(mask)
            result[n][side+'_cyan_bbox']=[int(xx.min()+x),int(yy.min()+y),int(xx.max()+x+1),int(yy.max()+y+1)]
    p=np.asarray(layers['Choker_Pendant'])[:,:,3]
    yy,xx=np.where(p>128)
    result['pendant_alpha128_bbox']=[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)]
    body=np.asarray(layers['Body'])
    sub=body[1600:1950,980:1240,:3].astype(int)
    dark=(sub.mean(axis=2)<115)
    rows=np.where(dark.sum(axis=1)>12)[0]
    gem_top=int(rows.min()+1600)
    result['chest_gem_dark_top_y']=gem_top
    result['pendant_to_gem_vertical_gap_px']=gem_top-int(yy.max()+1)
    return result

def main():
    c=read_json(GEN/'placement-candidate06.json')
    c['stage']='段階2: Codexが正面合成を確認した確認A提出案。ユーザー未承認。'
    c['review']={'single_parts':'inspected','frontal_composite':'inspected','user_A':'pending','animation':'not tested','PSD':'not exported'}
    c['generation_calls']=4
    c['generation_limit']=30
    c['dependencies']={'python':'3.8.8','Pillow':'10.4.0','numpy':'1.24.4','scipy':'1.6.2 (installed version warns about numpy range; labeling completed and outputs checked)'}
    for p in c['layers']:
        p['status']='正面合成確認済み／ユーザー確認A待ち／動作未確認'
        if p['name']=='Hair_FrontAssembly':
            p['adoption_reason']='候補01〜03の小片状・重なり過多を避け、候補04で中央束、頬の曲線、胸への連続性を一枚で確立。候補05でアルファと髪影を調整、候補06の両目とも重ねて再確認。'
            p['mask_reason']='アルファ32超の最大連結成分を支持域とし周囲2原本pxを残す。離れた塵のみ除去し、連続する輪郭には閾値を適用しない。内部A253をA255へ補正。'
        if p['name'].startswith('Eye_'):
            p['adoption_reason']='100/105/110%を同一髪・顔で比較後、右108%・左100%＋内側25px/下3pxを個別比較。左右の虹彩径と原画の間隔、髪との釣り合いで候補06を選択。'
    write_json(OUT/'placement.json',c)
    layers,comp=render(c,OUT,True)
    master=rgba(ROOT/'assets/ciel/master/ciel-upper-body-2x.png')
    v8=rgba(ROOT/'assets/ciel/layers/v8/_compose.png')
    proofs=OUT/'proofs';proofs.mkdir(exist_ok=True)
    sheet([master,v8,comp],['原画','v8','v9 提出案'],proofs/'A-face.png',HEAD,.5)
    sheet([master,v8,comp],['原画','v8','v9 提出案'],proofs/'A-upper.png',scale=.3)
    on_bg(comp).crop(HEAD).save(proofs/'A-face-v9-100pct.png')
    # Phone proxies: each character panel is exactly 240/360/480 px wide, uncropped.
    for width in [240,360,480]:
        sheet([master,v8,comp],['原画','v8','v9 提出案'],proofs/('A-phone-'+str(width)+'.png'),scale=width/SIZE[0])
        on_bg(comp).resize((width,round(SIZE[1]*width/SIZE[0])),Image.Resampling.LANCZOS).save(proofs/('phone-v9-'+str(width)+'.png'))
    panel_backgrounds(comp,HEAD,.4,proofs/'edges-head.png')
    panel_backgrounds(comp,(0,0,*SIZE),.23,proofs/'edges-upper.png')
    panel_backgrounds(layers['Hair_FrontAssembly'],(400,260,1820,1830),.5,proofs/'edges-front-hair.png')
    # Native-scale transparent-edge patches.
    patches=[('頭頂',(840,260,1360,620)),('頬髪',(630,980,1150,1340)),('胸の毛先',(650,1430,1170,1790))]
    patches_out=Image.new('RGB',(1040,3*408),(35,39,50))
    for j,(label,box) in enumerate(patches):
        for k,col in enumerate([(250,250,252,255),(18,22,34,255)]):
            patches_out.paste(on_bg(layers['Hair_FrontAssembly'],col).crop(box),(k*520,j*408+48))
            ImageDraw.Draw(patches_out).text((k*520+8,j*408+10),label+' 100%',font=font(22),fill='white')
    patches_out.save(proofs/'edges-detail-100pct.png')
    hair_names=[n for n in layers if n.startswith('Hair_')]
    face_names=['Face_Skin','Face_Shadow_Hair','Eye_R','Eye_L','Brow_R','Brow_L','Nose','Mouth']
    nohair=composite(layers,hair_names+['Face_Shadow_Hair'])
    noface=composite(layers,face_names)
    haironly=composite({n:im for n,im in layers.items() if n in hair_names})
    sheet([comp,nohair,noface],['通常','髪と髪影を外した顔','顔と表情パーツを外した髪'],proofs/'diagnostics-head.png',HEAD,.4)
    sheet([haironly,layers['Hair_FrontAssembly']],['髪のみ','採用した前面髪の一続きの形'],proofs/'diagnostics-hair.png',(260,190,1910,1840),.4)
    neck_names=['Choker_Back','Choker_Inside','Neck','Neck_Shadow_Chin','Choker_Front','Choker_Pendant']
    neck=composite({n:im for n,im in layers.items() if n in neck_names})
    no_shadow=composite(layers,['Neck_Shadow_Chin','Face_Shadow_Hair'])
    sheet([comp,no_shadow,neck],['通常','独立した影を非表示','首・首輪・飾りのみ'],proofs/'diagnostics-neck.png',(820,1240,1420,1790),1)
    shutil.copyfile(GEN/'candidate05/eye-options.png',proofs/'eye-options.png')
    shutil.copyfile(GEN/'candidate06/eye-balance.png',proofs/'eye-balance-final.png')
    stage1=rgba(GEN/'stage1/compose.png')
    sheet([v8,stage1,comp],['v8','段階1: 配置調整','段階2: 提出案'],proofs/'stages-face.png',HEAD,.4)
    sheet([v8,stage1,comp],['v8','段階1: 配置調整','段階2: 提出案'],proofs/'stages-upper.png',scale=.25)
    # Static displacement coverage check, explicitly not a rig/angle test.
    moved=[]
    for dx,dy in [(-16,0),(0,0),(16,8)]:
        moved_layers=dict(layers)
        shifted=Image.new('RGBA',SIZE)
        shifted.paste(layers['Hair_FrontAssembly'],(dx,dy))
        moved_layers['Hair_FrontAssembly']=shifted
        moved.append(composite(moved_layers))
    sheet(moved,['髪だけ左16px','正面','髪だけ右16/下8px'],proofs/'coverage-translation-only.png',HEAD,.4)
    # All layers at a common .18 canvas scale; no fit-to-box ambiguity.
    tile_w,tile_h=391,566
    contacts=Image.new('RGB',(tile_w*5,tile_h*math.ceil(len(layers)/5)),BG[:3])
    for j,(n,im) in enumerate(layers.items()):
        x,y=(j%5)*tile_w,(j//5)*tile_h
        view=on_bg(im).resize((391,521),Image.Resampling.LANCZOS)
        contacts.paste(view,(x,y+45))
        ImageDraw.Draw(contacts).text((x+6,y+10),n+' ×0.18',font=font(15),fill='white')
    contacts.save(proofs/'layers-common-scale.png')
    write_json(OUT/'measurements.json',measure(comp,layers))
    manifest={}
    for p in sorted(OUT.rglob('*.png')):
        with Image.open(p) as im:
            manifest[p.relative_to(OUT).as_posix()]={'sha256':sha(p),'size':list(im.size),'mode':im.mode}
    write_json(OUT/'output-manifest.json',manifest)
    prior=read_json(GEN/'input-sha256.json')
    changed=[n for n,h in prior.items() if sha(ROOT/n)!=h]
    reconstruction=composite({n:rgba(OUT/(n+'.png')) for n in layers})
    exact=bool(np.array_equal(np.asarray(reconstruction),np.asarray(comp)))
    checks={'existing_input_files_checked':len(prior),'changed_existing_inputs':changed,'layer_count':len(layers),'all_layers_rgba_2172x2896':all(im.mode=='RGBA' and im.size==SIZE for im in layers.values()),'exported_layers_recompose_exactly':exact,'generation_calls':4,'limit':30,'animation_tested':False,'user_A_approved':False}
    write_json(OUT/'validation.json',checks)
    if changed or not exact:raise RuntimeError(checks)
    print(json.dumps(checks,ensure_ascii=False))

if __name__=='__main__':main()
