"""Extract the excited mouth, blush and sparkling irises from the full-face guide."""
from pathlib import Path
import sys,json,hashlib,shutil,importlib.util
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import label,binary_fill_holes,distance_transform_edt
from scipy.spatial import ConvexHull
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
OUT=ROOT/'assets/ciel/generated/v43';WORK=ROOT/'.local/excited-integration'
for p in (OUT/'parts',OUT/'layers',WORK/'layers'):p.mkdir(parents=True,exist_ok=True)
source=ROOT/'assets/ciel/generated/v22/expressions/excited.png';im=Image.open(source).convert('RGBA');a=np.asarray(im);rgb=a[:,:,:3].astype(float);y,x=np.indices(a.shape[:2])
s=228/(1385-1149);ox=1100-s*840;oy=1164-s*1149
def largest(mask):
    regions,n=label(mask);counts=np.bincount(regions.ravel());counts[0]=0
    return binary_fill_holes(regions==counts.argmax())
def extract(mask):
    b=a.copy();b[~mask]=0;return Image.fromarray(b)
pieces={'Mouth_Excited':extract(largest((x>740)&(x<950)&(y>1180)&(y<1390)&(rgb[:,:,0]-rgb[:,:,1]>12)))}
for side,(x0,x1) in [('R',(560,760)),('L',(950,1150))]:
    mask=largest((x>x0)&(x<x1)&(y>930)&(y<1140)&(rgb[:,:,2]-rgb[:,:,0]>25))
    # Bright stars can connect to the lower rim, so filling binary holes alone loses them.
    yy,xx=np.nonzero(mask);points=np.c_[xx,yy];hull=ConvexHull(points)
    outline=Image.new('L',im.size);ImageDraw.Draw(outline).polygon([tuple(p) for p in points[hull.vertices]],fill=255)
    mask=np.asarray(outline)>0
    pieces[f'Eye_{side}_ExcitedIris']=extract(mask)
roi=Image.new('L',im.size);dr=ImageDraw.Draw(roi)
dr.polygon([(535,1134),(585,1120),(691,1122),(743,1137),(748,1205),(670,1230),(574,1210)],fill=255)
dr.polygon([(940,1125),(987,1118),(1100,1123),(1164,1142),(1134,1213),(1020,1227),(942,1202)],fill=255)
alpha=np.clip((rgb[:,:,0]-rgb[:,:,1]-3)/110,0,.5)*np.asarray(roi)/255
alpha*=np.clip(distance_transform_edt(np.asarray(roi)>0)/18,0,1)
b=np.zeros_like(a);b[:,:,:3]=[249,150,169];b[:,:,3]=np.round(alpha*255).astype(np.uint8);pieces['Cheek_Excited']=Image.fromarray(b)
manifest={'canvas':[2172,2896],'out':'.local/excited-integration/excited-additions','layers':[]};boxes={}
for name,piece in pieces.items():
    piece.save(OUT/'parts'/(name+'.png'))
    layer=piece.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
    layer.save(OUT/'layers'/(name+'.png'));shutil.copy2(OUT/'layers'/(name+'.png'),WORK/'layers'/(name+'.png'))
    boxes[name]={'source_bbox':piece.getbbox(),'target_bbox':layer.getbbox()}
    manifest['layers'].append({'name':name,'path':'.local/excited-integration/layers/'+name+'.png','visible':False})
reference=np.asarray(im.convert('RGB').transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC))
m=cc.Model(ROOT/'assets/ciel/runtime/Ciel.model3.json');m.reset();m.update();tex=r.load_textures(m);ds={d['id']:d for d in m.drawables()};fits={}
for side,cx,xs in [('R',920,range(820,971,25)),('L',1285,range(1235,1386,25))]:
    lash=ds[f'Eye_{side}_LashUpper'];al=r.raster(lash,tex[lash['texture']],720,200,1,np.array([740,930]))[:,:,3]
    target=[];actual=[];samples=[]
    for xx in xs:
        rr=np.flatnonzero(reference[930:1080,xx,:].max(1)<110);mm=np.flatnonzero(al[:150,xx-740]>.5)
        if len(rr) and len(mm):samples.append(xx);target.append(int(rr[0])+930);actual.append(int(mm[0])+930)
    assert len(samples)>=5,(side,samples)
    fits[side]={'samples_x':samples,'reference_y':target,'normal_y':actual,'coefficients':np.polyfit((np.array(samples)-cx)/145,np.array(target)-actual,2).tolist()}
(WORK/'additions.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
data={'reference':str(source.relative_to(ROOT)).replace('\\','/'),'reference_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'shared_scale':s,'offset':[ox,oy],'parts':boxes,'eye_profiles':fits,'lower_edge_offset':10,'new_generation':False}
(OUT/'placement.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
(OUT/'generation-provenance.json').write_text(json.dumps({'method':'non-generative separation from registered full-face guide','reference':data['reference'],'new_generation':False,'parts':list(pieces),'blush':'skin removed by red-channel difference with feathered region masks','approved':False},indent=2)+'\n',encoding='utf-8')
if not (WORK/'excited-base.cmo3').exists():shutil.copy2(ROOT/'assets/ciel/rig/ciel.cmo3',WORK/'excited-base.cmo3')
print('EXCITED_PARTS_PREPARED',boxes,fits)
