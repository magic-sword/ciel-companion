"""Extract the jitome mouth, flat brows and upper lashes from the full-face guide."""
from pathlib import Path
import sys,json,hashlib,shutil,importlib.util
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import label,binary_fill_holes,distance_transform_edt
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
OUT=ROOT/'assets/ciel/generated/v44';WORK=ROOT/'.local/jitome-integration'
for p in (OUT/'parts',OUT/'layers',WORK/'layers'):p.mkdir(parents=True,exist_ok=True)
source=ROOT/'assets/ciel/generated/v22/expressions/jitome.png';im=Image.open(source).convert('RGBA');a=np.asarray(im);rgb=a[:,:,:3].astype(float);y,x=np.indices(a.shape[:2])
s=228/(1385-1149);ox=1100-s*840;oy=1164-s*1149
def largest(mask):
    regions,n=label(mask);counts=np.bincount(regions.ravel());counts[0]=0
    return binary_fill_holes(regions==counts.argmax())
def extract(mask):
    b=a.copy();b[~mask]=0;return Image.fromarray(b)
pieces={'Mouth_Jitome':extract(largest((x>790)&(x<910)&(y>1220)&(y<1280)&(rgb[:,:,0]-rgb[:,:,1]>8)))}
for side,(x0,x1) in [('R',(480,760)),('L',(930,1210))]:
    region=Image.new('L',im.size);dr=ImageDraw.Draw(region)
    points=[(486,1042),(537,1000),(739,1000),(748,1043),(579,1048),(556,1057),(568,1106),(520,1089)] if side=='R' else [(936,994),(1150,988),(1202,1029),(1179,1067),(1136,1090),(1147,1042),(1122,1037),(932,1039)]
    dr.polygon(points,fill=255)
    mask=largest((np.asarray(region)>0)&(rgb.max(2)<170)&(rgb[:,:,2]-rgb[:,:,1]<30)&(rgb[:,:,1]<90))
    from scipy.ndimage import binary_dilation
    mask=binary_dilation(mask,iterations=1)&(rgb.max(2)<235)
    pieces[f'Eye_{side}_JitomeUpper']=extract(mask)
region=Image.new('L',im.size);dr=ImageDraw.Draw(region)
dr.polygon([(502,863),(570,866),(647,865),(713,855),(717,860),(650,873),(570,873),(502,870)],fill=110)
dr.polygon([(944,848),(1005,853),(1080,850),(1164,848),(1164,854),(1080,858),(1002,859),(944,855)],fill=110)
brow=Image.new('RGBA',im.size,(178,183,203,0));brow.putalpha(region);pieces['Brow_Jitome']=brow
manifest={'canvas':[2172,2896],'out':'.local/jitome-integration/jitome-additions','layers':[]};boxes={}
for name,piece in pieces.items():
    piece.save(OUT/'parts'/(name+'.png'))
    layer=piece.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
    layer.save(OUT/'layers'/(name+'.png'));shutil.copy2(OUT/'layers'/(name+'.png'),WORK/'layers'/(name+'.png'))
    boxes[name]={'source_bbox':piece.getbbox(),'target_bbox':layer.getbbox()}
    manifest['layers'].append({'name':name,'path':'.local/jitome-integration/layers/'+name+'.png','visible':False})
reference=np.asarray(im.convert('RGB').transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC))
m=cc.Model(ROOT/'assets/ciel/runtime/Ciel.model3.json');m.reset();m.update();tex=r.load_textures(m);ds={d['id']:d for d in m.drawables()};fits={}
for side,cx,xs in [('R',920,range(870,971,25)),('L',1285,range(1235,1336,25))]:
    white=ds[f'Eye_{side}_Sclera'];al=r.raster(white,tex[white['texture']],720,240,1,np.array([740,930]))[:,:,3]
    target=[];actual=[];samples=[]
    upper=np.asarray(Image.open(OUT/'layers'/f'Eye_{side}_JitomeUpper.png'))[:,:,3]
    for xx in xs:
        rr=np.flatnonzero(upper[980:1120,xx]>128);mm=np.flatnonzero(al[:200,xx-740]>.5)
        if len(rr) and len(mm):samples.append(xx);target.append(int(rr[-1])+980+.5);actual.append(int(mm[0])+930)
    assert len(samples)>=4,(side,samples)
    from scipy.stats import theilslopes
    slope,intercept,*_=theilslopes(target,samples)
    target=[slope*xx+intercept for xx in samples]
    fits[side]={'samples_x':samples,'reference_y':target,'normal_y':actual,'coefficients':np.polyfit((np.array(samples)-cx)/145,np.array(target)-actual,2).tolist()}
(WORK/'additions.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
data={'reference':str(source.relative_to(ROOT)).replace('\\','/'),'reference_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'shared_scale':s,'offset':[ox,oy],'parts':boxes,'eye_profiles':fits,'lower_edge_offset':12,'iris_y_offset':24,'new_generation':False}
(OUT/'placement.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
(OUT/'generation-provenance.json').write_text(json.dumps({'method':'non-generative separation from registered full-face guide','reference':data['reference'],'new_generation':False,'parts':list(pieces),'brows':'flat guide outlines traced without overlapping hair strokes','approved':False},indent=2)+'\n',encoding='utf-8')
if not (WORK/'jitome-base.cmo3').exists():shutil.copy2(ROOT/'assets/ciel/rig/ciel.cmo3',WORK/'jitome-base.cmo3')
print('JITOME_PARTS_PREPARED',boxes,fits)
