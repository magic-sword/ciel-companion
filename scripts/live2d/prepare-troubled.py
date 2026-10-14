"""Extract contextual reference parts and measure the troubled upper-lid profile."""
from pathlib import Path
import sys,json,hashlib,shutil,importlib.util
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import label,binary_fill_holes
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
OUT=ROOT/'assets/ciel/generated/v37';WORK=ROOT/'.local/troubled-integration'
for p in (OUT/'parts',OUT/'layers',WORK/'layers'):p.mkdir(parents=True,exist_ok=True)
source=ROOT/'assets/ciel/generated/v22/expressions/troubled.png';im=Image.open(source).convert('RGBA');a=np.asarray(im);rgb=a[:,:,:3].astype(float);y,x=np.indices(a.shape[:2])
s=228/(1385-1149);ox=1100-s*840;oy=1164-s*1149
mask=(x>790)&(x<910)&(y>1215)&(y<1300)&(rgb[:,:,0]-rgb[:,:,1]>5)
b=a.copy();b[~mask]=0;mouth=Image.fromarray(b)
region=Image.new('L',im.size);draw=ImageDraw.Draw(region)
draw.polygon([(551,904),(591,885),(637,858),(682,831),(733,815),(730,823),(690,846),(646,871),(597,894)],fill=140)
draw.polygon([(947,812),(991,833),(1034,858),(1081,884),(1145,904),(1085,894),(1037,870),(993,848),(950,823)],fill=140)
brow=Image.new('RGBA',im.size,(178,183,203,0));brow.putalpha(region)
roi=(x>1120)&(x<1220)&(y>870)&(y<1010);labels,n=label(roi&(rgb[:,:,2]-rgb[:,:,0]>25)&(rgb[:,:,1]-rgb[:,:,0]>10))
candidates=[]
for i in range(1,n+1):
    yy,xx=np.nonzero(labels==i)
    if len(xx)>30 and xx.max()-xx.min()>15 and yy.max()-yy.min()>25:candidates.append((len(xx),i))
assert candidates,'No isolated sweat contour';_,chosen=max(candidates);mask=binary_fill_holes(labels==chosen)
b=a.copy();b[~mask]=0;sweat=Image.fromarray(b)
manifest={'canvas':[2172,2896],'out':'.local/troubled-integration/troubled-additions','layers':[]};boxes={}
for name,piece in [('Mouth_Troubled',mouth),('Brow_Troubled',brow),('Sweat_Troubled',sweat)]:
    piece.save(OUT/'parts'/(name+'.png'));layer=piece.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
    layer.save(OUT/'layers'/(name+'.png'));shutil.copy2(OUT/'layers'/(name+'.png'),WORK/'layers'/(name+'.png'))
    boxes[name]={'source_bbox':piece.getbbox(),'target_bbox':layer.getbbox()};manifest['layers'].append({'name':name,'path':'.local/troubled-integration/layers/'+name+'.png','visible':False})
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
(OUT/'placement.json').write_text(json.dumps({'reference':str(source.relative_to(ROOT)).replace('\\','/'),'reference_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'shared_scale':s,'offset':[ox,oy],'parts':boxes,'eye_profiles':fits,'new_generation':False,'iris_y_scale':.95,'iris_y_offset':18,'iris_top_extension':18},indent=2)+'\n',encoding='utf-8')
if not (WORK/'troubled-base.cmo3').exists():shutil.copy2(ROOT/'assets/ciel/rig/ciel.cmo3',WORK/'troubled-base.cmo3')
print('TROUBLED_PARTS_PREPARED',boxes, fits)
