"""Extract contextual reference parts and measure the embarrassed upper-lid profile."""
from pathlib import Path
import sys,json,hashlib,shutil,importlib.util
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import label,binary_fill_holes,distance_transform_edt
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
OUT=ROOT/'assets/ciel/generated/v38';WORK=ROOT/'.local/embarrassed-integration'
for p in (OUT/'parts',OUT/'layers',WORK/'layers'):p.mkdir(parents=True,exist_ok=True)
source=ROOT/'assets/ciel/generated/v22/expressions/embarrassed.png';im=Image.open(source).convert('RGBA');a=np.asarray(im);rgb=a[:,:,:3].astype(float);y,x=np.indices(a.shape[:2])
s=228/(1385-1149);ox=1100-s*840;oy=1164-s*1149
mask=(x>790)&(x<910)&(y>1215)&(y<1290)&(rgb[:,:,0]-rgb[:,:,1]>8)
regions,n=label(mask);counts=np.bincount(regions.ravel());counts[0]=0;mask=binary_fill_holes(regions==counts.argmax());b=a.copy();b[~mask]=0;mouth=Image.fromarray(b)
region=Image.new('L',im.size);draw=ImageDraw.Draw(region)
draw.polygon([(547,908),(604,879),(650,856),(722,841),(717,849),(653,865),(607,888),(551,914)],fill=120)
draw.polygon([(948,842),(1004,861),(1080,884),(1148,894),(1148,900),(1080,892),(1001,870),(946,849)],fill=120)
brow=Image.new('RGBA',im.size,(178,183,203,0));brow.putalpha(region)
roi=Image.new('L',im.size);rd=ImageDraw.Draw(roi)
rd.polygon([(538,1117),(616,1106),(700,1105),(779,1100),(831,1091),(894,1100),(970,1099),(1085,1106),(1166,1119),(1133,1220),(1040,1235),(959,1218),(873,1195),(797,1197),(714,1218),(625,1228),(557,1188)],fill=255)
alpha=np.clip((rgb[:,:,0]-rgb[:,:,1]-4)/105,0,.65)*np.asarray(roi)/255
alpha*=np.clip(distance_transform_edt(np.asarray(roi)>0)/25,0,1)
near=(x-840)**2+(y-1149)**2
alpha[near<36]=np.median(alpha[(near>36)&(near<144)])
b=np.zeros_like(a);b[:,:,:3]=[249,140,154];b[:,:,3]=np.round(alpha*255).astype(np.uint8);cheek=Image.fromarray(b)
manifest={'canvas':[2172,2896],'out':'.local/embarrassed-integration/embarrassed-additions','layers':[]};boxes={}
for name,piece in [('Mouth_Embarrassed',mouth),('Brow_Embarrassed',brow),('Cheek_Embarrassed',cheek)]:
    piece.save(OUT/'parts'/(name+'.png'));layer=piece.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
    layer.save(OUT/'layers'/(name+'.png'));shutil.copy2(OUT/'layers'/(name+'.png'),WORK/'layers'/(name+'.png'))
    boxes[name]={'source_bbox':piece.getbbox(),'target_bbox':layer.getbbox()};manifest['layers'].append({'name':name,'path':'.local/embarrassed-integration/layers/'+name+'.png','visible':False})
reference=np.asarray(im.convert('RGB').transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC))
m=cc.Model(ROOT/'assets/ciel/runtime/Ciel.model3.json');m.reset();m.update();tex=r.load_textures(m);ds={d['id']:d for d in m.drawables()};fits={}
for side,cx,xs in [('R',920,range(820,971,25)),('L',1285,range(1235,1386,25))]:
    lash=ds[f'Eye_{side}_LashUpper'];alpha=r.raster(lash,tex[lash['texture']],720,200,1,np.array([740,930]))[:,:,3]
    target=[];actual=[];samples=[]
    for xx in xs:
        rr=np.flatnonzero(reference[930:1080,xx,:].max(1)<110);mm=np.flatnonzero(alpha[:150,xx-740]>.5)
        if len(rr) and len(mm):samples.append(xx);target.append(int(rr[0])+930);actual.append(int(mm[0])+930)
    assert len(samples)>=5,(side,samples)
    fits[side]={'samples_x':samples,'reference_y':target,'normal_y':actual,'coefficients':np.polyfit((np.array(samples)-cx)/145,np.array(target)-actual,2).tolist()}
(WORK/'additions.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(OUT/'placement.json').write_text(json.dumps({'reference':str(source.relative_to(ROOT)).replace('\\','/'),'reference_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'shared_scale':s,'offset':[ox,oy],'parts':boxes,'eye_profiles':fits,'new_generation':False,'iris_y_scale':.95,'iris_y_offset':20,'highlight_y_offset':35,'iris_top_extension':18},indent=2)+'\n',encoding='utf-8')
if not (WORK/'embarrassed-base.cmo3').exists():shutil.copy2(ROOT/'assets/ciel/rig/ciel.cmo3',WORK/'embarrassed-base.cmo3')
print('EMBARRASSED_PARTS_PREPARED',boxes, fits)
