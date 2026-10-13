"""Keep reference facial ink; separate contextual generated folded ears for a draft."""
from pathlib import Path
import json,hashlib,shutil
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import label
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'assets/ciel/generated/v35';WORK=ROOT/'.local/angry-integration'
for p in (OUT/'parts',OUT/'layers',WORK/'layers'):p.mkdir(parents=True,exist_ok=True)
reference=ROOT/'assets/ciel/generated/v22/expressions/angry.png';ref=Image.open(reference).convert('RGBA');a=np.asarray(ref);rgb=a[:,:,:3].astype(float);y,x=np.indices(a.shape[:2])
s=228/(1394-1151);ox=1100-s*840;oy=1164-s*1151
masks={}
masks['Mouth_Angry']=(x>800)&(x<890)&(y>1195)&(y<1260)&(rgb[:,:,0]-rgb[:,:,1]>5)
# Trace the complete wedge rather than a straight band through crossing hair.
brow_region=Image.new('L',ref.size);draw=ImageDraw.Draw(brow_region)
draw.polygon([(529,855),(580,882),(635,907),(690,930),(736,940),(722,952),(690,952),(633,936),(578,908)],fill=255)
draw.polygon([(938,932),(981,926),(1040,908),(1100,881),(1161,852),(1112,897),(1050,925),(988,945),(954,945)],fill=255)
masks['Brow_Angry']=np.asarray(brow_region)>0
source=OUT/'edits/angry-face-ears-with-contour.png';gen=Image.open(source).convert('RGBA');g=np.asarray(gen);gy,gx=np.indices(g.shape[:2]);factor=gen.width/1280
target_left=np.array([178,384])*s+[ox,oy];target_right=np.array([1488,384])*s+[ox,oy]
ear_s=(target_right[0]-target_left[0])/(1205*factor);ear_ox=target_left[0]-23*factor*ear_s;ear_oy=target_left[1]-386*factor*ear_s
manifest={'canvas':[2172,2896],'out':'.local/angry-integration/angry-additions','layers':[]};boxes={}
for name in ('Mouth_Angry','Brow_Angry','Ear_R_Folded','Ear_L_Folded'):
    if name in masks:
        b=a.copy();b[~masks[name]]=0
        if name=='Brow_Angry':
            # Clean intersecting hair strokes by filling the manually traced brow outline.
            # This is image editing of the reference silhouette, not a new generation.
            b[:,:,:3]=(178,183,203);b[:,:,3]=masks[name].astype(np.uint8)*155
        piece=Image.fromarray(b);scale,tx,ty=s,ox,oy
    else:
        region=(gy>120*factor)&(gy<730*factor)&((gx<600*factor) if '_R_' in name else (gx>690*factor))
        components,n=label(region&(g[:,:,3]>8));sizes=np.bincount(components.ravel());sizes[0]=0;mask=components==sizes.argmax()
        b=g.copy();b[~mask]=0;piece=Image.fromarray(b);scale,tx,ty=ear_s,ear_ox,ear_oy
    assert piece.getbbox(),name;piece.save(OUT/'parts'/(name+'.png'))
    layer=piece.transform((2172,2896),Image.Transform.AFFINE,(1/scale,0,-tx/scale,0,1/scale,-ty/scale),Image.Resampling.BICUBIC)
    layer.save(OUT/'layers'/(name+'.png'));shutil.copy2(OUT/'layers'/(name+'.png'),WORK/'layers'/(name+'.png'))
    boxes[name]={'source_bbox':piece.getbbox(),'target_bbox':layer.getbbox()}
    manifest['layers'].append({'name':name,'path':'.local/angry-integration/layers/'+name+'.png','visible':False})
(WORK/'additions.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(OUT/'placement.json').write_text(json.dumps({'reference':str(reference.relative_to(ROOT)).replace('\\','/'),'reference_sha256':hashlib.sha256(reference.read_bytes()).hexdigest(),'face_scale':s,'face_offset':[ox,oy],'ear_pair_scale':ear_s,'ear_pair_offset':[ear_ox,ear_oy],'ear_registration':'shared transform from the two visible reference ear tips','parts':boxes},indent=2)+'\n',encoding='utf-8')
if not (WORK/'ciel-before.cmo3').exists():shutil.copy2(ROOT/'assets/ciel/rig/ciel.cmo3',WORK/'ciel-before.cmo3')
shutil.copy2(WORK/'ciel-before.cmo3',WORK/'angry-base.cmo3')
print('ANGRY_PARTS_PREPARED',json.dumps(boxes))
