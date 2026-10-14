"""Extract the sad reference mouth and clean its brow contours without generation."""
from pathlib import Path
import json,hashlib,shutil
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'assets/ciel/generated/v36';WORK=ROOT/'.local/sad-integration'
for p in (OUT/'parts',OUT/'layers',WORK/'layers'):p.mkdir(parents=True,exist_ok=True)
source=ROOT/'assets/ciel/generated/v22/expressions/sad.png';im=Image.open(source).convert('RGBA');a=np.asarray(im);rgb=a[:,:,:3].astype(float);y,x=np.indices(a.shape[:2])
s=228/(1385-1149);ox=1100-s*840;oy=1164-s*1149
mask=(x>790)&(x<900)&(y>1200)&(y<1280)&(rgb[:,:,0]-rgb[:,:,1]>5)
b=a.copy();b[~mask]=0;mouth=Image.fromarray(b)
region=Image.new('L',im.size);draw=ImageDraw.Draw(region)
draw.polygon([(553,900),(597,883),(641,866),(685,848),(733,835),(726,845),(687,865),(643,880),(598,894)],fill=155)
draw.polygon([(935,835),(977,850),(1020,870),(1065,887),(1127,899),(1067,894),(1021,883),(978,864),(942,845)],fill=155)
brow=Image.new('RGBA',im.size,(178,183,203,0));brow.putalpha(region)
manifest={'canvas':[2172,2896],'out':'.local/sad-integration/sad-additions','layers':[]};boxes={}
for name,piece in [('Mouth_Sad',mouth),('Brow_Sad',brow)]:
    piece.save(OUT/'parts'/(name+'.png'))
    layer=piece.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
    layer.save(OUT/'layers'/(name+'.png'));shutil.copy2(OUT/'layers'/(name+'.png'),WORK/'layers'/(name+'.png'))
    boxes[name]={'source_bbox':piece.getbbox(),'target_bbox':layer.getbbox()}
    manifest['layers'].append({'name':name,'path':'.local/sad-integration/layers/'+name+'.png','visible':False})
(WORK/'additions.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(OUT/'placement.json').write_text(json.dumps({'reference':str(source.relative_to(ROOT)).replace('\\','/'),'reference_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'shared_scale':s,'offset':[ox,oy],'registration':'nose and chin','parts':boxes,'brow_cleanup':'reference outlines traced to remove intersecting hair','new_generation':False,'reused_ears':'v35 folded ears'},indent=2)+'\n',encoding='utf-8')
if not (WORK/'sad-base.cmo3').exists():shutil.copy2(ROOT/'.local/sad-adoption/adopted-drafts/angry/angry.cmo3',WORK/'sad-base.cmo3')
print('SAD_PARTS_PREPARED',boxes)
