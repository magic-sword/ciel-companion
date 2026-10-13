"""Register generated eyes/blush using uniform scale and translation only."""
from pathlib import Path
import hashlib,json,shutil
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'assets/ciel/generated/v26'
SIZE=(2172,2896);CROP=(550,650,1600,1700)
manifest=json.loads((ROOT/'assets/ciel/current/layers.json').read_text())
snapshot={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'assets/ciel/current').rglob('*')) if p.is_file()}
if not (OUT/'current-before.json').exists():(OUT/'current-before.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
eyes=Image.open(OUT/'keyed/happy-eyes-01.png').convert('RGBA')
placements={};layers={}

def register(image,crop,width,cx,top,name,center_y=None):
    patch=image.crop(crop);a=np.asarray(patch)[:,:,3];yy,xx=np.nonzero(a>16)
    bounds=(max(0,int(xx.min())-2),max(0,int(yy.min())-2),min(patch.width,int(xx.max())+3),min(patch.height,int(yy.max())+3))
    patch=patch.crop(bounds);scale=width/patch.width
    patch=patch.resize((width,round(patch.height*scale)),Image.Resampling.LANCZOS)
    pos=(round(cx-width/2),top if center_y is None else round(center_y-patch.height/2))
    layer=Image.new('RGBA',SIZE);layer.paste(patch,pos)
    placements[name]={'separation_crop':crop,'alpha_bounds':bounds,'uniform_scale':scale,'translate':pos,'bbox':layer.getbbox()}
    return layer

layers['Eye_R_Happy']=register(eyes,(100,440,570,710),260,899,984,'Eye_R_Happy')
layers['Eye_L_Happy']=register(eyes,(720,440,1190,710),260,1309,979,'Eye_L_Happy')
# Black-key matting recovers generated pigment and its translucent falloff.
rgb=np.asarray(Image.open(OUT/'keyed/happy-blush-01.png').convert('RGB'),dtype=np.float32)/255
alpha=rgb.max(axis=2);alpha[alpha<3/255]=0
foreground=np.clip(rgb/np.maximum(alpha[:,:,None],1e-6),0,1)
rgba=np.dstack((foreground,alpha));rgba[alpha==0]=0
blush=Image.fromarray(np.round(rgba*255).astype(np.uint8))
blush_r=register(blush,(200,400,600,720),170,910,0,'Cheek_Blush_R',center_y=1133)
blush_l=register(blush,(650,400,1100,720),170,1300,0,'Cheek_Blush_L',center_y=1128)
layers['Cheek_Blush_Happy']=Image.alpha_composite(blush_r,blush_l)
layers['Mouth_Happy']=Image.open(ROOT/'assets/ciel/generated/v25/layers/Mouth_Happy.png').convert('RGBA')
for name,layer in layers.items():
    layer.save(OUT/'layers'/(name+'.png'))
    placements.setdefault(name,{'source':'../v25/layers/Mouth_Happy.png','operation':'unchanged copy'})
    placements[name]['sha256']=hashlib.sha256((OUT/'layers'/(name+'.png')).read_bytes()).hexdigest()

assembled=Image.new('RGBA',SIZE)
for entry in manifest['layers']:
    name=entry['name'];visible=entry.get('visible',True)
    if name.startswith(('Eye_L_','Eye_R_','Mouth_')):visible=False
    if visible:assembled.alpha_composite(Image.open(ROOT/entry['path']).convert('RGBA'))
    if name=='Face_Shadow_Hair':
        # Preview the expression's display weight; the pigment PNG stays intact.
        blush_preview=layers['Cheek_Blush_Happy'].copy()
        blush_preview.putalpha(blush_preview.getchannel('A').point(lambda value:round(value*.55)))
        assembled.alpha_composite(blush_preview)
    if name=='Eye_R_Closed':assembled.alpha_composite(layers['Eye_R_Happy'])
    if name=='Eye_L_Closed':assembled.alpha_composite(layers['Eye_L_Happy'])
    if name=='Mouth_Large':assembled.alpha_composite(layers['Mouth_Happy'])
assembled.save(OUT/'proofs/happy-assembled.png')
def flat(im):
    result=Image.new('RGBA',im.size,(64,72,104,255));result.alpha_composite(im.convert('RGBA'));return result.convert('RGB')
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',23)
before=Image.open(ROOT/'assets/ciel/generated/v25/proofs/happy-assembled.png').convert('RGBA')
panels=[('承認済みの見本',Image.open(OUT/'inputs/happy-reference-face.png')),('前の修正案（v25）',before.crop(CROP)),('今回の修正案（v26）',assembled.crop(CROP))]
board=Image.new('RGB',(1575,565),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,im) in enumerate(panels):
    board.paste(flat(im).resize((525,525),Image.Resampling.LANCZOS),(i*525,40));draw.text((i*525+10,8),label,font=font,fill='white')
board.save(OUT/'proofs/happy-face-comparison.png')
board=Image.new('RGB',(868,619),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,im) in enumerate([('前の修正案（v25）',before),('今回の修正案（v26）',assembled)]):
    board.paste(flat(im).resize((434,579),Image.Resampling.LANCZOS),(i*434,40));draw.text((i*434+10,8),label,font=font,fill='white')
board.save(OUT/'proofs/happy-front-comparison.png')
assert json.loads((OUT/'current-before.json').read_text())==snapshot
assert all(im.size==SIZE and im.mode=='RGBA' and im.getbbox() for im in layers.values())
assert layers['Mouth_Happy'].tobytes()==Image.open(ROOT/'assets/ciel/generated/v25/layers/Mouth_Happy.png').convert('RGBA').tobytes()
(OUT/'placement.json').write_text(json.dumps(placements,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'verification.json').write_text(json.dumps({'current_unchanged':True,'layers':list(layers),'canvas':list(SIZE),
    'mouth_unchanged_from_v25':True,'blush_preview_weight':.55,'eye_skin_patches':False,'rig_imported':False},indent=2)+'\n',encoding='utf-8')
print('V26_MATERIALS_READY')
