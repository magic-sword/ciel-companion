"""Reproducible v11 assembly. Writes only the three explicitly allowed v11 roots.
Run python -B scripts/live2d/v11/build.py (no generation calls).
"""
from pathlib import Path
import json, shutil, hashlib, warnings
import numpy as np
from PIL import Image, ImageFilter, ImageChops
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from scipy import ndimage as ndi

ROOT=Path(__file__).resolve().parents[3]
SRC=ROOT/'assets/ciel/layers/v10'
OUT=ROOT/'assets/ciel/layers/v11'
GEN=ROOT/'assets/ciel/generated/v11'
SIZE=(2172,2896)
changes={}
def dump(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def read(n): return Image.open(SRC/(n+'.png')).convert('RGBA')
def blank(): return Image.new('RGBA',SIZE)
def save(n,im,record):
    a=np.array(im); a[a[:,:,3]==0,:3]=0
    Image.fromarray(a).save(OUT/(n+'.png'))
    changes[n]=record
def rows_warp(im,sy,src_center,dst_center,scale):
    # Resample premultiplied RGBA once; outside original alpha remains transparent.
    a=np.array(im.convert('RGBa')); yy,xx=np.mgrid[:SIZE[1],:SIZE[0]].astype('float32')
    yy[:]=sy[:,None]
    xx[:]=(xx-dst_center[:,None])/scale[:,None]+src_center[:,None]
    b=np.stack([ndi.map_coordinates(a[:,:,c],[yy,xx],order=1,mode='constant',cval=0,prefilter=False) for c in range(4)],2)
    return Image.fromarray(b,'RGBa').convert('RGBA')
def feature(sheet,box,target):
    im=sheet.crop(box); a=np.array(im)
    # Largest connected opaque form plus 2 source pixels of antialias support.
    lab,count=ndi.label(a[:,:,3]>32)
    sizes=np.bincount(lab.ravel()); sizes[0]=0
    support=ndi.binary_dilation(lab==int(sizes.argmax()),iterations=2)
    a[:,:,3]=np.uint8(np.minimum(255,np.rint(a[:,:,3].astype(float)*255/253)))
    a[~support]=0
    im=Image.fromarray(a); bbox=im.getbbox(); im=im.crop(bbox)
    resized=im.convert('RGBa').resize((target[2]-target[0],target[3]-target[1]),Image.Resampling.LANCZOS).convert('RGBA')
    full=blank(); full.paste(resized,target[:2])
    return full,dict(sheet_crop=box,trim_box_in_crop=bbox,target=target,scale_xy=[resized.width/im.width,resized.height/im.height],alpha='largest alpha>32 component + 2px antialias; alpha x255/253; premultiplied Lanczos')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    state=json.loads((SRC/'layer-state.json').read_text(encoding='utf-8'))
    for r in state['layers']:
        shutil.copyfile(SRC/(r['name']+'.png'),OUT/(r['name']+'.png'))
        r['path']=r['path'].replace('/v10/','/v11/')
    ys=np.arange(SIZE[1],dtype=float)
    old=read('Face_Skin'); a=np.array(old)[:,:,3]
    # Above the visible jaw: +18px. At the jaw: match individually traced master
    # cheek/chin coordinates, interpolating continuous centers and widths.
    sy=ys.copy(); centers=np.full(SIZE[1],1094.); dest=centers+18; scales=np.ones(SIZE[1])
    anchors=[(1200,820,1401),(1230,838,1383),(1250,851,1358),(1260,858,1350),
             (1270,865,1342),(1280,873,1331),(1290,884,1319),(1300,896,1304),
             (1310,913,1288),(1320,933,1270),(1330,954,1250),(1340,980,1228),
             (1350,1006,1208),(1360,1033,1184),(1370,1062,1162),(1380,1092,1135)]
    knot_y=[]; knot_src=[]; knot_dst=[]; knot_scale=[]
    for y,left,right in anchors:
        occupied=np.where(a[y]>128)[0]; lo,hi=occupied[[0,-1]]
        knot_y.append(y); knot_src.append((lo+hi)/2); knot_dst.append((left+right)/2); knot_scale.append((right-left)/(hi-lo))
    knot_y.extend([1387,1425]); knot_src.extend([1095.,1095.]); knot_dst.extend([1113.,1113.]); knot_scale.extend([1.,1.])
    region=ys>=1200
    centers[region]=np.interp(ys[region],knot_y,knot_src)
    dest[region]=np.interp(ys[region],knot_y,knot_dst)
    scales[region]=np.interp(ys[region],knot_y,knot_scale)
    face=rows_warp(old,sy,centers,dest,scales)
    save('Face_Skin',face,dict(method='rowwise contour warp of v10; face outline and baked cheek shade move together',upper_dx=18,master_jaw_anchors=anchors,chin_target_x=1113,interpolation='linear row anchors; premultiplied bilinear, y unchanged'))
    # Keep collar attachment fixed, taper the neck correction down to zero.
    neckdx=np.interp(ys,[0,1350,1430,1510,2895],[8,8,4,0,0])
    neck=rows_warp(read('Neck'),ys,np.zeros_like(ys),neckdx,np.ones_like(ys))
    save('Neck',neck,dict(method='horizontal row shift',y=[0,1350,1430,1510,2895],dx=[8,8,4,0,0],reason='center upper neck beneath corrected jaw, fix collar junction'))
    shadow=rows_warp(read('Neck_Shadow_Chin'),ys,np.zeros_like(ys),neckdx,np.ones_like(ys))
    sa=np.array(shadow); sa[:,:,3]=np.minimum(sa[:,:,3],np.array(neck)[:,:,3])
    save('Neck_Shadow_Chin',Image.fromarray(sa),dict(method='same deformation as Neck; clip alpha to Neck'))
    hair=Image.open(ROOT/'assets/ciel/layers/v9/Hair_FrontAssembly.png').getchannel('A')
    shifted=Image.new('L',SIZE); shifted.paste(hair,(5,12)); shifted=shifted.filter(ImageFilter.GaussianBlur(3))
    alpha=ImageChops.multiply(shifted,face.getchannel('A')).point(lambda v:round(v*.25))
    sh=Image.new('RGBA',SIZE,(171,159,187,0)); sh.putalpha(alpha)
    save('Face_Shadow_Hair',sh,dict(method='recompute stationary hair cast shadow against corrected face alpha',offset=[5,12],blur=3,opacity=.25,color=[171,159,187]))
    # Skin patches stay at feature positions; resample their colour from new base.
    for n in ['Mouth_Skin_Upper','Mouth_Skin_Lower']+[f'Eye_{s}_LidSkin_{p}' for s in ['R','L'] for p in ['Upper','Lower']]:
        patch=np.array(face); patch[:,:,3]=np.minimum(patch[:,:,3],np.array(read(n))[:,:,3])
        save(n,Image.fromarray(patch),dict(method='refresh skin RGB from corrected Face_Skin; keep existing feature mask/position'))
    sheet=Image.open(GEN/'parts/Expressions_01.png').convert('RGBA')
    for side,box,target in [('R',(0,120,740,450),(748,1036,1012,1098)),('L',(800,120,1536,450),(1199,1026,1457,1088))]:
        im,rec=feature(sheet,box,target)
        save('Eye_'+side+'_Closed',im,dict(source='Expressions_01',**rec,reason='full open eye corner width; lower-middle eyelid height, cool dark lashes'))
    for mode,box,target in [('Small',(100,650,700,870),(1045,1228,1168,1264)),('Large',(850,540,1450,960),(1014,1191,1199,1324))]:
        full,rec=feature(sheet,box,target)
        # Work on a local crop for masks and underpainting; every part remains a
        # full-canvas exported PNG. Original generated colour is retained.
        im=full.crop(target); a=np.array(im); rgb=a[:,:,:3].astype(float); occ=a[:,:,3]>0
        yy,xx=np.mgrid[:im.height,:im.width]
        teeth=(rgb.min(2)>185)&(rgb.max(2)-rgb.min(2)<60)&(yy<im.height*.40)&occ
        teeth=ndi.binary_dilation(teeth,iterations=1)&occ
        tongue=(rgb[:,:,0]>205)&(rgb[:,:,1]>112)&(rgb[:,:,0]-rgb[:,:,1]>45)&(yy>im.height*.20)&occ&~teeth
        tongue=ndi.binary_dilation(tongue,iterations=1)&occ&~teeth
        distance=ndi.distance_transform_edt(a[:,:,3]>128)
        line=occ&(distance<=2.5)
        teeth &= ~line; tongue &= ~line
        # Continuous cavity under tongue, teeth AND detached border. Smooth
        # underpaint colour comes from unoccluded generated cavity texels.
        cavity=occ&~ndi.binary_dilation(teeth|tongue|line,iterations=2)
        # Fit the unoccluded cavity's gentle colour field, excluding teeth and
        # borders. Nearest-neighbour fill creates radial streaks under the tongue.
        nx=(xx-im.width/2)/im.width; ny=yy/im.height
        design=np.stack([np.ones_like(nx),nx,ny,nx*nx,nx*ny,ny*ny],2)
        coeff=np.linalg.lstsq(design[cavity],rgb[cavity],rcond=None)[0]
        field=design@coeff
        field=np.clip(field,np.percentile(rgb[cavity],5,axis=0),np.percentile(rgb[cavity],95,axis=0))
        inside=a.copy(); fill=teeth|tongue|line
        inside[:,:,:3]=np.uint8(np.rint(field))
        # Solid interior; use original silhouette alpha at the outside edge.
        for part,mask in [('Inside',None),('Tongue',tongue),('Teeth',teeth),('Line_Upper',line&(yy<im.height*.35)),('Line_Lower',line&(yy>=im.height*.35))]:
            b=inside.copy() if mask is None else a.copy()
            if mask is not None: b[~mask]=0
            out=blank(); out.paste(Image.fromarray(b),target[:2])
            save('Mouth_'+mode+'_'+part,out,dict(source='Expressions_01',**rec,part=part,split='colour masks + 2.5px line from alpha>128 edge; cavity quadratic colour-field fit from unobscured pixels (clamped 5-95 percentile); no teeth/tongue/outline baked into Inside'))
    for r in state['layers']:
        n=r['name']
        if n in changes:
            r['source']='v11補正 / generated/v11/corrections.json'
            r['description']=({'Face_Skin':'お手本の頬・顎に合わせた顔土台。目鼻口の座標は保持。','Neck':'上端を右8px、首輪接続で0pxへ減衰。','Neck_Shadow_Chin':'補正首へ追従した顎影。','Face_Shadow_Hair':'固定髪の影を補正顔へ再クリップ。'}.get(n) or ('開眼と同幅の新規閉じ目。開眼層と排他。' if n.endswith('_Closed') else 'v11表情素材／顔補正に対応。詳細は補正記録。'))
            if '_LidSkin_' in n or n.startswith('Mouth_Skin_'):
                r['description']='既存の位置・肌マスクを保ち、補正後のFace_Skinから色を再採取。'
            if n.startswith(('Mouth_Small_','Mouth_Large_')):
                part=n.split('_',2)[2]
                r['description']=('小口123×36px配置。' if n.startswith('Mouth_Small_') else '大口185×133px配置。')+{'Inside':'歯・舌・輪郭を焼き込まない連続したローズモーブの口腔。','Tongue':'生成した淡いピンクの舌。','Teeth':'左右の小さな八重歯。','Line_Upper':'生成口の連続した上縁と口角。','Line_Lower':'生成口の連続した側縁下部と下縁。'}[part]
    manifest=json.loads((SRC/'psd-manifest.json').read_text(encoding='utf-8'))
    manifest['out']='assets/ciel/psd/ciel-v11'
    manifest['layers']=[dict(name=r['name'],path=r['path']) for r in state['layers']]
    dump(OUT/'psd-manifest.json',manifest); dump(OUT/'layer-state.json',state)
    dump(GEN/'corrections.json',changes)
    log=json.loads((GEN/'generation-log.json').read_text(encoding='utf-8'))
    log['calls'][0]['sha256']=hashlib.sha256((GEN/'parts/Expressions_01.png').read_bytes()).hexdigest()
    dump(GEN/'generation-log.json',log)
    print('Built',len(state['layers']),'layers;',len(changes),'changed;',len(state['layers'])-len(changes),'byte-identical copies')

if __name__=='__main__': main()
