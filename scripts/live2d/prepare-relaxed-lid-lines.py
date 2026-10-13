"""Separate existing v32 lower-lid ink, without generating or painting."""
from pathlib import Path
import json,shutil
import numpy as np
from PIL import Image
from scipy.ndimage import label
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'assets/ciel/generated/v33';WORK=ROOT/'.local/lid-boundary-integration'
for p in (OUT/'parts',OUT/'layers',WORK/'layers'):p.mkdir(parents=True,exist_ok=True)
im=Image.open(ROOT/'assets/ciel/generated/v32/edits/relaxed-details-with-contour-01.png').convert('RGBA');a=np.asarray(im)
rgb=a[:,:,:3].astype(int);ink=(rgb.max(axis=2)<215)&(rgb.min(axis=2)>60)&((rgb.max(axis=2)-rgb.min(axis=2))<60)&(a[:,:,3]>32)
y,x=np.indices(ink.shape);p=json.loads((ROOT/'assets/ciel/generated/v32/placement.json').read_text());s=p['shared_scale'];ox,oy=p['offset']
manifest={'canvas':[2172,2896],'out':'.local/lid-boundary-integration/lid-lines','layers':[]}
for side,box in [('R',(205,550,485,584)),('L',(775,548,1080,584))]:
    mask=ink&(x>=box[0])&(x<box[2])&(y>=box[1])&(y<box[3]);components,n=label(mask)
    sizes=np.bincount(components.ravel());sizes[0]=0;mask=components==sizes.argmax()
    # Preserve the source color and alpha exactly; discarded pixels belong to other parts.
    b=a.copy();b[~mask]=0;piece=Image.fromarray(b);name=f'Eye_{side}_RelaxedLowerLine'
    piece.save(OUT/'parts'/(name+'.png'))
    layer=piece.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
    layer.save(OUT/'layers'/(name+'.png'));shutil.copy2(OUT/'layers'/(name+'.png'),WORK/'layers'/(name+'.png'))
    manifest['layers'].append({'name':name,'path':str((WORK/'layers'/(name+'.png')).relative_to(ROOT)).replace('\\','/'),'visible':False})
(WORK/'additions.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
shutil.copy2(ROOT/'assets/ciel/rig/ciel.cmo3',WORK/'ciel-before.cmo3')
shutil.copy2(WORK/'ciel-before.cmo3',WORK/'boundary-base.cmo3')
print('LID_LINES_SEPARATED')
