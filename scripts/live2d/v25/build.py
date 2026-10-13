"""Separate and register generated overlays; no painting or nonuniform warping."""
from pathlib import Path
import hashlib,json,importlib.util
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'assets/ciel/generated/v25'
SIZE=(2172,2896); CROP=(550,650,1600,1700)
manifest=json.loads((ROOT/'assets/ciel/current/layers.json').read_text())
source=Image.open(OUT/'keyed/happy-overlay-01.png').convert('RGBA')
specs={
    'Eye_R_Happy':((100,500,550,720),260,(899,1000)),
    'Eye_L_Happy':((750,500,1180,720),260,(1309,995)),
    'Mouth_Happy':((520,800,790,980),130,(1108,1220)),
}
layers={};placement={}
for name,(crop,width,(cx,y)) in specs.items():
    patch=source.crop(crop)
    # Remove only the empty surround using the alpha extent. Keep generated
    # ink/glints/interior and antialiased edge RGB exactly as supplied.
    alpha=np.asarray(patch)[:,:,3]; yy,xx=np.nonzero(alpha>16)
    bounds=(max(0,int(xx.min())-2),max(0,int(yy.min())-2),min(patch.width,int(xx.max())+3),min(patch.height,int(yy.max())+3))
    patch=patch.crop(bounds);scale=width/patch.width
    resized=patch.resize((width,round(patch.height*scale)),Image.Resampling.LANCZOS)
    position=(round(cx-width/2),y)
    layer=Image.new('RGBA',SIZE);layer.paste(resized,position);layer.save(OUT/'layers'/(name+'.png'))
    layers[name]=layer
    placement[name]={'source':'keyed/happy-overlay-01.png','separation_crop':crop,'alpha_crop':bounds,
                     'uniform_scale':scale,'translate':position,'bbox':layer.getbbox(),
                     'sha256':hashlib.sha256((OUT/'layers'/(name+'.png')).read_bytes()).hexdigest()}

def assemble(new=True):
    result=Image.new('RGBA',SIZE)
    for entry in manifest['layers']:
        name=entry['name']; visible=entry.get('visible',True)
        if name.startswith(('Eye_L_','Eye_R_','Mouth_')):visible=False
        if visible:result.alpha_composite(Image.open(ROOT/entry['path']).convert('RGBA'))
        if name=='Face_Shadow_Hair':
            blush=Image.open(ROOT/'assets/ciel/current/layers/Cheek_Blush.png').convert('RGBA')
            a=blush.getchannel('A').point(lambda v:round(v*.45));blush.putalpha(a);result.alpha_composite(blush)
        if name=='Eye_R_Closed':result.alpha_composite(layers['Eye_R_Happy'] if new else Image.open(ROOT/'assets/ciel/current/layers/Eye_R_Happy.png'))
        if name=='Eye_L_Closed':result.alpha_composite(layers['Eye_L_Happy'] if new else Image.open(ROOT/'assets/ciel/current/layers/Eye_L_Happy.png'))
        if name=='Mouth_Large':result.alpha_composite(layers['Mouth_Happy'] if new else Image.open(ROOT/'assets/ciel/current/layers/Mouth_Large.png'))
    return result

def flat(im,bg=(64,72,104)):
    result=Image.new('RGBA',im.size,bg+(255,));result.alpha_composite(im.convert('RGBA'));return result.convert('RGB')

candidate=assemble();candidate.save(OUT/'proofs/happy-assembled.png')
before=assemble(False);before.save(OUT/'proofs/happy-before-assembled.png')
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',23)
panels=[('承認済みの見本',Image.open(OUT/'inputs/happy-reference-face.png')),
        ('現状の素材',before.crop(CROP)),('修正案（素材合成）',candidate.crop(CROP))]
board=Image.new('RGB',(525*3,565),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,im) in enumerate(panels):
    board.paste(flat(im).resize((525,525),Image.Resampling.LANCZOS),(i*525,40));draw.text((i*525+12,8),label,font=font,fill='white')
board.save(OUT/'proofs/happy-face-comparison.png')
board=Image.new('RGB',(434*2,619),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,im) in enumerate([('現状の素材',before),('修正案（素材合成）',candidate)]):
    board.paste(flat(im).resize((434,579),Image.Resampling.LANCZOS),(i*434,40));draw.text((i*434+10,8),label,font=font,fill='white')
board.save(OUT/'proofs/happy-front-comparison.png')
# Details are generated compositions, not manual drawing edits.
details=Image.new('RGB',(420*3,300),(224,227,234));draw=ImageDraw.Draw(details)
for i,(name,layer) in enumerate(layers.items()):
    bbox=layer.getbbox();area=(bbox[0]-25,bbox[1]-25,bbox[2]+25,bbox[3]+25)
    panel=flat(layer.crop(area),(224,227,234));panel.thumbnail((400,235))
    details.paste(panel,(i*420+(420-panel.width)//2,55+(235-panel.height)//2));draw.text((i*420+10,10),name,font=font,fill=(25,32,48))
details.save(OUT/'proofs/layers-detail.png')
(OUT/'placement.json').write_text(json.dumps(placement,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
beforehash=json.loads((OUT/'current-before.json').read_text())
now={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'assets/ciel/current').rglob('*')) if p.is_file()}
verification={'current_unchanged':beforehash==now,'layer_count':3,'canvas':[2172,2896],
              'all_rgba':all(im.mode=='RGBA' for im in layers.values()),'operations':'rectangular separation, alpha bounding crop, uniform resize, translation',
              'eye_skin_backing':False,'rig_imported':False}
assert verification['current_unchanged']
(OUT/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
print('V25_LAYERS_READY')
