"""Inspect the corrected separations locally without re-rendering the full model."""
from pathlib import Path
import json, warnings
import numpy as np
from PIL import Image,ImageDraw,ImageFont
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from scipy import ndimage as ndi
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'assets/ciel/layers/v11';GEN=ROOT/'assets/ciel/generated/v11'
box=(990,1170,1220,1340);w,h=460,340
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19)
sheet=Image.new('RGB',(w*3,(h+38)*2),(232,234,241));d=ImageDraw.Draw(sheet)
tests={}
for row,mode in enumerate(['Small','Large']):
    ims={p:Image.open(OUT/f'Mouth_{mode}_{p}.png').convert('RGBA').crop(box) for p in ['Inside','Tongue','Teeth','Line_Upper','Line_Lower']}
    combined=Image.new('RGBA',ims['Inside'].size)
    for im in ims.values():combined.alpha_composite(im)
    outline=Image.new('RGBA',combined.size)
    outline.alpha_composite(ims['Line_Upper']);outline.alpha_composite(ims['Line_Lower'])
    for col,(label,im) in enumerate([('Cavity alone',ims['Inside']),('Upper + lower line',outline),('Five layers recomposed',combined)]):
        base=Image.new('RGBA',im.size,(232,234,241,255));base.alpha_composite(im)
        x=col*w;y=row*(h+38)
        d.text((x+8,y+8),mode+' / '+label,font=font,fill=(22,32,49))
        sheet.paste(base.convert('RGB').resize((w,h),Image.Resampling.LANCZOS),(x,y+38))
    teeth=np.array(ims['Teeth'])[:,:,3]>128
    labels,count=ndi.label(teeth);sizes=np.bincount(labels.ravel())[1:]
    substantial=int((sizes>=2).sum())
    assert substantial==2,(mode,substantial)
    cavity=np.array(ims['Inside']); inside=cavity[:,:,3]>250
    assert inside.any()
    tests[mode]=dict(two_canines=substantial,opaque_cavity_pixels=int(inside.sum()),cavity_rgb_min=cavity[:,:,:3][inside].min(0).tolist(),cavity_rgb_max=cavity[:,:,:3][inside].max(0).tolist())
sheet.save(GEN/'candidates/02-mouth-separation.png')
(GEN/'mouth-separation-checks.json').write_text(json.dumps(tests,indent=2)+'\n',encoding='utf-8')
print(json.dumps(tests,indent=2))
