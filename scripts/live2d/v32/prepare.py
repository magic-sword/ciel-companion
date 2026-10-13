"""Separate generated relaxed mouth/blush; eyes remain a shape reference."""
from pathlib import Path
import json,hashlib,shutil
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'assets/ciel/generated/v32';WORK=ROOT/'.local/relaxed-integration'
for folder in (OUT/'parts',OUT/'layers',WORK/'layers'):folder.mkdir(parents=True,exist_ok=True)
source=Image.open(OUT/'edits/relaxed-details-with-contour-01.png').convert('RGBA')
a=np.asarray(source);y,x=np.indices(a.shape[:2])
masks={'Mouth_Relaxed':(x>=535)&(x<725)&(y>=745)&(y<805),
    'Cheek_Relaxed':(((x>130)&(x<535))|((x>735)&(x<1130)))&(y>=575)&(y<825)&(a[:,:,:3].max(axis=2)>180)}
# Shared registration: generated nose/chin -> original nose/chin -> model cheek width.
s1=(697-459)/(990-635);ox1=491-s1*628;oy1=459-s1*635
p=json.loads((ROOT/'assets/ciel/generated/v31/placement.json').read_text())
s=p['uniform_scale']*s1;ox=p['offset'][0]+p['uniform_scale']*ox1;oy=p['offset'][1]+p['uniform_scale']*oy1
for name,mask in masks.items():
    b=a.copy();b[~mask]=0;piece=Image.fromarray(b);piece.save(OUT/'parts'/(name+'.png'))
    layer=piece.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
    layer.save(OUT/'layers'/(name+'.png'));shutil.copy2(OUT/'layers'/(name+'.png'),WORK/'layers'/(name+'.png'))
registered=source.transform((970,970),Image.Transform.AFFINE,(1/s1,0,-ox1/s1,0,1/s1,-oy1/s1),Image.Resampling.BICUBIC)
registered.save(OUT/'registered-reference-details.png')
manifest={'canvas':[2172,2896],'out':'.local/relaxed-integration/relaxed-additions','layers':[
    {'name':n,'path':str((WORK/'layers'/(n+'.png')).relative_to(ROOT)).replace('\\','/'),'visible':False}
    for n in ('Cheek_Relaxed','Mouth_Relaxed')]}
(WORK/'additions.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
if not (WORK/'ciel-before.cmo3').exists():shutil.copy2(ROOT/'assets/ciel/rig/ciel.cmo3',WORK/'ciel-before.cmo3')
shutil.copy2(WORK/'ciel-before.cmo3',WORK/'relaxed-base.cmo3')
(OUT/'placement.json').write_text(json.dumps({'raw_nose':[628,635],'raw_chin':[632,990],
    'shared_scale':s,'offset':[ox,oy],'blush_opacity':.5,
    'eye_artwork_reference_only':True,'current_eye_parts_reused':True},indent=2)+'\n',encoding='utf-8')
print('RELAXED_MATERIALS_PREPARED')
