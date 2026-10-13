"""Extract the reference round mouth by image masking, without new generation."""
from pathlib import Path
import json,shutil,hashlib
import numpy as np
from PIL import Image
from scipy.ndimage import label,binary_fill_holes
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'assets/ciel/generated/v34';WORK=ROOT/'.local/surprised-integration'
for p in (OUT/'parts',OUT/'layers',WORK/'layers'):p.mkdir(parents=True,exist_ok=True)
source=ROOT/'assets/ciel/generated/v22/expressions/surprised.png';im=Image.open(source).convert('RGBA');a=np.asarray(im)
rgb=a[:,:,:3].astype(float);y,x=np.indices(a.shape[:2]);roi=(x>800)&(x<890)&(y>1200)&(y<1300)
components,n=label(roi&(rgb[:,:,0]-rgb[:,:,1]>12));sizes=np.bincount(components.ravel());sizes[0]=0
mask=binary_fill_holes(components==sizes.argmax());b=a.copy();b[~mask]=0;piece=Image.fromarray(b)
box=piece.getbbox();assert box[0]>805 and box[2]<885 and box[1]>1205 and box[3]<1295,box
piece.save(OUT/'parts/Mouth_Surprised.png')
factor=im.width/1600;s=228/(230*factor);ox=1100-s*808*factor;oy=1164-s*1104*factor
layer=piece.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
layer.save(OUT/'layers/Mouth_Surprised.png');shutil.copy2(OUT/'layers/Mouth_Surprised.png',WORK/'layers/Mouth_Surprised.png')
(OUT/'placement.json').write_text(json.dumps({'source':str(source.relative_to(ROOT)).replace('\\','/'),
    'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'shared_scale':s,'offset':[ox,oy],
    'nose_chin_registration':True,'mouth_source_bbox':box,'new_generation':False},indent=2)+'\n',encoding='utf-8')
(WORK/'additions.json').write_text(json.dumps({'canvas':[2172,2896],'out':'.local/surprised-integration/surprised-mouth',
    'layers':[{'name':'Mouth_Surprised','path':'.local/surprised-integration/layers/Mouth_Surprised.png','visible':False}]},indent=2)+'\n',encoding='utf-8')
print('SURPRISED_MOUTH_READY',box,layer.getbbox())
