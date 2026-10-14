"""Soften the diffuse blush without losing the reference hatch strokes."""
from pathlib import Path
import json
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'assets/ciel/generated/v38/layers/Cheek_Embarrassed.png'
out=ROOT/'assets/ciel/generated/v39';(out/'layers').mkdir(parents=True,exist_ok=True)
a=np.asarray(Image.open(source).convert('RGBA'));alpha=a[:,:,3].astype(float)/255
low=gaussian_filter(alpha,18);detail=np.clip(alpha-gaussian_filter(alpha,3),0,None)
y,x=np.indices(alpha.shape);x0,y0,x1,y1=Image.open(source).getbbox()
edge=np.minimum.reduce([x-x0,x1-1-x,y-y0,y1-1-y]);t=np.clip(edge/22,0,1);gate=t*t*(3-2*t)
new=np.clip((.55*low+.7*detail)*gate,0,1)
b=np.zeros_like(a);b[:,:,:3]=[255,165,175];b[:,:,3]=np.round(new*255).astype(np.uint8)
Image.fromarray(b).save(out/'layers/Cheek_Embarrassed.png')
meta={'new_generation':False,'source':source.relative_to(ROOT).as_posix(),'smooth_sigma_canvas_px':18,'detail_sigma_canvas_px':3,'diffuse_weight':.55,'stroke_weight':.7,'edge_feather_canvas_px':22,'blush_rgb':[255,165,175],'mean_alpha_before':float(alpha[alpha>0].mean()),'mean_alpha_after_on_original_support':float(new[alpha>0].mean())}
(out/'blush-adjustment.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
print('BLUSH_REFINED')
