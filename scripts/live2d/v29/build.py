"""Controlled eye-size and hair-contact comparisons using existing artwork."""
from pathlib import Path
import json, hashlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'assets/ciel/generated/v29'
SIZE=(2172,2896); CROP=(550,650,1600,1700)
OUT.mkdir(parents=True,exist_ok=True); (OUT/'proofs').mkdir(exist_ok=True)
manifest=json.loads((ROOT/'assets/ciel/current/layers.json').read_text(encoding='utf-8'))
p27=json.loads((ROOT/'assets/ciel/generated/v27/placement.json').read_text(encoding='utf-8'))
p28=json.loads((ROOT/'assets/ciel/generated/v28/placement.json').read_text(encoding='utf-8'))
source=Image.open(ROOT/'assets/ciel/generated/v27/edits/reference-extracted-01.png').convert('RGBA')
def hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'assets/ciel/current').rglob('*')) if p.is_file()}
before=hashes()
placements={}; outputs={}
for variant in ('size-only','contact-only','size-and-contact'):
    folder=OUT/variant/'layers'; folder.mkdir(parents=True,exist_ok=True)
    layers={}; info={}
    for name,side in [('Eye_R_Happy','R'),('Eye_L_Happy','L')]:
        crop=p27[name]['separation_crop']; b=p27[name]['alpha_crop']
        patch=source.crop((crop[0]+b[0],crop[1]+b[1],crop[0]+b[2],crop[1]+b[3]))
        width=260 if variant!='contact-only' else p28[name]['size'][0]
        s=width/patch.width; patch=patch.resize((width,round(patch.height*s)),Image.Resampling.LANCZOS)
        old=p28[name]; cx=old['translate'][0]+old['size'][0]/2
        x=round(cx-width/2); top=old['translate'][1]
        # Dark outer lash tip, distinct from the lighter crease above it.
        a=np.asarray(patch); mask=(a[:,:,:3].max(axis=2)<150)&(a[:,:,3]>128)
        yy,xx=np.nonzero(mask); tipx=int(xx.min() if side=='R' else xx.max())
        tipy=int(round(np.median(yy[np.abs(xx-tipx)<=2])))
        hair=np.asarray(Image.open(ROOT/f'assets/ciel/current/layers/Hair_Side_{side}_Inner.png'))[:,:,3]
        if variant!='size-only':
            if variant=='size-and-contact': top=1008 if side=='R' else 1003
            row=top+tipy
            hx=np.flatnonzero(hair[row]>128)
            boundary=int(hx.max() if side=='R' else hx.min())
            # A 3px overlap avoids a bright skin gap; hair is composited above the eye.
            x=boundary-tipx+(-3 if side=='R' else 3)
        tip=(x+tipx,top+tipy)
        hx=np.flatnonzero(hair[tip[1]]>128)
        boundary=int(hx.max() if side=='R' else hx.min())
        gap=tip[0]-boundary if side=='R' else boundary-tip[0]
        layer=Image.new('RGBA',SIZE);layer.paste(patch,(x,top));layers[name]=layer
        info[name]={'width':width,'uniform_scale':s,'translate':[x,top],'lash_tip':tip,
                    'hair_boundary_x':boundary,'skin_gap_px':gap,'bbox':layer.getbbox()}
    for name in ('Mouth_Happy','Cheek_Blush_Happy'):
        layers[name]=Image.open(ROOT/f'assets/ciel/generated/v28/layers/{name}.png').convert('RGBA')
    for name,im in layers.items():im.save(folder/(name+'.png'))
    assembled=Image.new('RGBA',SIZE)
    for entry in manifest['layers']:
        name=entry['name']
        if entry.get('visible',True) and not name.startswith(('Eye_L_','Eye_R_','Mouth_')):
            assembled.alpha_composite(Image.open(ROOT/entry['path']).convert('RGBA'))
        if name=='Face_Shadow_Hair':
            blush=layers['Cheek_Blush_Happy'].copy();blush.putalpha(blush.getchannel('A').point(lambda a:round(a*.45)))
            assembled.alpha_composite(blush)
        for slot,part in [('Eye_R_Closed','Eye_R_Happy'),('Eye_L_Closed','Eye_L_Happy'),('Mouth_Large','Mouth_Happy')]:
            if name==slot:assembled.alpha_composite(layers[part])
    assembled.save(OUT/variant/'happy-assembled.png');outputs[variant]=assembled; placements[variant]=info

reference=Image.open(ROOT/'assets/ciel/generated/v25/inputs/happy-reference-face.png').convert('RGBA')
r=p28['registration'];s=r['scale'];ox,oy=r['offset']
reference=reference.transform(SIZE,Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',21)
def board(panels,path,box=CROP,panel_size=(525,525)):
    w,h=panel_size; result=Image.new('RGB',(w*len(panels),h+40),(64,72,104)); draw=ImageDraw.Draw(result)
    for i,(label,im) in enumerate(panels):
        patch=im.convert('RGBA').crop(box);bg=Image.new('RGBA',patch.size,(64,72,104,255));bg.alpha_composite(patch)
        result.paste(bg.convert('RGB').resize((w,h),Image.Resampling.LANCZOS),(i*w,40));draw.text((i*w+8,8),label,font=font,fill='white')
    result.save(path)
old=Image.open(ROOT/'assets/ciel/generated/v28/proofs/happy-assembled.png')
board([('見本（鼻・顎基準）',reference),('前の案（v28）',old),('目の幅＋髪との接点を調整',outputs['size-and-contact'])],OUT/'proofs/happy-face-comparison.png')
board([('前の案（v28）',old),('幅だけ260pxへ',outputs['size-only']),('接点だけ調整',outputs['contact-only']),('幅・接点・高さを調整',outputs['size-and-contact'])],OUT/'proofs/controlled-comparison.png',panel_size=(420,420))
board([('見本',reference),('前の案（v28）',old),('幅・接点・高さを調整',outputs['size-and-contact'])],OUT/'proofs/eye-contact-details.png',box=(710,940,1490,1190),panel_size=(624,200))
assert before==hashes()
assert all(p['skin_gap_px']==-3 for v in ('contact-only','size-and-contact') for p in placements[v].values())
(OUT/'placement.json').write_text(json.dumps(placements,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'verification.json').write_text(json.dumps({'current_unchanged':True,'rig_imported':False,'artwork_redrawn':False,
    'variants':3,'contact_overlap_px':3,'canvas':SIZE,'blush_preview_weight':.45},indent=2)+'\n',encoding='utf-8')
print(json.dumps(placements,ensure_ascii=False,indent=2))
