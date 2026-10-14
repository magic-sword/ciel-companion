"""Extract contextual reference parts and measure the teary upper-lid profile."""
from pathlib import Path
import sys,json,hashlib,shutil,importlib.util
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import label,binary_fill_holes
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
OUT=ROOT/'assets/ciel/generated/v40';WORK=ROOT/'.local/teary-integration'
for p in (OUT/'parts',OUT/'layers',WORK/'layers'):p.mkdir(parents=True,exist_ok=True)
source=ROOT/'assets/ciel/generated/v22/expressions/teary.png';im=Image.open(source).convert('RGBA');a=np.asarray(im);rgb=a[:,:,:3].astype(float);y,x=np.indices(a.shape[:2])
s=228/(1385-1149);ox=1100-s*840;oy=1164-s*1149
mask=(x>780)&(x<930)&(y>1230)&(y<1280)&(rgb[:,:,0]-rgb[:,:,1]>8)
b=a.copy();b[~mask]=0;mouth=Image.fromarray(b)
region=Image.new('L',im.size);draw=ImageDraw.Draw(region)
draw.polygon([(548,911),(609,879),(652,850),(709,835),(717,841),(652,858),(611,888),(551,917)],fill=130)
draw.polygon([(948,836),(1003,858),(1077,885),(1150,902),(1148,908),(1076,893),(1000,867),(946,844)],fill=130)
brow=Image.new('RGBA',im.size,(178,183,203,0));brow.putalpha(region)
tears={}
for side in 'RL':
 mask=Image.new('L',im.size);dr=ImageDraw.Draw(mask)
 if side=='R':
  dr.polygon([(592,1102),(603,1095),(626,1095),(644,1100),(652,1114),(645,1124),(626,1130),(607,1129),(590,1123),(588,1110)],fill=255)
  dr.ellipse((566,1101,604,1128),fill=255);dr.ellipse((692,1096,721,1117),fill=255)
 else:
  dr.polygon([(1036,1103),(1040,1097),(1055,1092),(1077,1091),(1091,1096),(1096,1109),(1091,1120),(1077,1126),(1056,1125),(1042,1118)],fill=255)
  dr.ellipse((1084,1095,1120,1127),fill=255);dr.ellipse((964,1090,992,1112),fill=255)
 from PIL import ImageFilter
 alpha=np.asarray(mask.filter(ImageFilter.GaussianBlur(.7))).astype(float)*.85
 b=a.copy();b[:,:,3]=np.round(alpha).astype(np.uint8);b[b[:,:,3]==0]=0;tears[side]=Image.fromarray(b)
manifest={'canvas':[2172,2896],'out':'.local/teary-integration/teary-additions','layers':[]};boxes={}
for name,piece in [('Mouth_Teary',mouth),('Brow_Teary',brow),('Tears_R_Teary',tears['R']),('Tears_L_Teary',tears['L'])]:
    piece.save(OUT/'parts'/(name+'.png'));layer=piece.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
    layer.save(OUT/'layers'/(name+'.png'));shutil.copy2(OUT/'layers'/(name+'.png'),WORK/'layers'/(name+'.png'))
    boxes[name]={'source_bbox':piece.getbbox(),'target_bbox':layer.getbbox()};manifest['layers'].append({'name':name,'path':'.local/teary-integration/layers/'+name+'.png','visible':False})
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
(OUT/'placement.json').write_text(json.dumps({'reference':str(source.relative_to(ROOT)).replace('\\','/'),'reference_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'shared_scale':s,'offset':[ox,oy],'parts':boxes,'eye_profiles':fits,'new_generation':False,'iris_y_scale':.98,'iris_y_offset':16,'highlight_y_offset':32,'iris_top_extension':18},indent=2)+'\n',encoding='utf-8')
if not (WORK/'teary-base.cmo3').exists():shutil.copy2(ROOT/'assets/ciel/rig/ciel.cmo3',WORK/'teary-base.cmo3')
print('TEARY_PARTS_PREPARED',boxes, fits)
