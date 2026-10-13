"""Place reference-derived extraction and translate existing blush; no repaint."""
from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'assets/ciel/generated/v27'
SIZE=(2172,2896);CROP=(550,650,1600,1700)
manifest=json.loads((ROOT/'assets/ciel/current/layers.json').read_text())
def current_hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'assets/ciel/current').rglob('*')) if p.is_file()}
if not (OUT/'current-before.json').exists():(OUT/'current-before.json').write_text(json.dumps(current_hashes(),indent=2),encoding='utf-8')
source=Image.open(OUT/'edits/reference-extracted-01.png').convert('RGBA')
specs={'Eye_R_Happy':((100,360,570,590),260,899,984),
       'Eye_L_Happy':((720,360,1180,590),260,1309,979),
       'Mouth_Happy':((500,670,780,840),130,1108,1220)}
layers={};placements={}
for name,(crop,width,cx,top) in specs.items():
    patch=source.crop(crop);yy,xx=np.nonzero(np.asarray(patch)[:,:,3]>16)
    bounds=(max(0,int(xx.min())-2),max(0,int(yy.min())-2),min(patch.width,int(xx.max())+3),min(patch.height,int(yy.max())+3))
    patch=patch.crop(bounds);scale=width/patch.width
    patch=patch.resize((width,round(patch.height*scale)),Image.Resampling.LANCZOS)
    pos=(round(cx-width/2),top);layer=Image.new('RGBA',SIZE);layer.paste(patch,pos);layers[name]=layer
    placements[name]={'source':'edits/reference-extracted-01.png','separation_crop':crop,'alpha_crop':bounds,
                     'uniform_scale':scale,'translate':pos,'bbox':layer.getbbox()}
blush=Image.open(ROOT/'assets/ciel/current/layers/Cheek_Blush.png').convert('RGBA')
shifted=Image.new('RGBA',SIZE);shifted.paste(blush,(0,-41));layers['Cheek_Blush_Happy']=shifted
placements['Cheek_Blush_Happy']={'source':'assets/ciel/current/layers/Cheek_Blush.png',
    'uniform_scale':1,'translate':[0,-41],'preview_weight':.45,'note':'Same pigment and strength as v25, translated upward only'}
for name,layer in layers.items():
    layer.save(OUT/'layers'/(name+'.png'));placements[name]['sha256']=hashlib.sha256((OUT/'layers'/(name+'.png')).read_bytes()).hexdigest()

assembled=Image.new('RGBA',SIZE)
for entry in manifest['layers']:
    name=entry['name'];visible=entry.get('visible',True)
    if name.startswith(('Eye_L_','Eye_R_','Mouth_')):visible=False
    if visible:assembled.alpha_composite(Image.open(ROOT/entry['path']).convert('RGBA'))
    if name=='Face_Shadow_Hair':
        preview=shifted.copy();preview.putalpha(preview.getchannel('A').point(lambda v:round(v*.45)));assembled.alpha_composite(preview)
    if name=='Eye_R_Closed':assembled.alpha_composite(layers['Eye_R_Happy'])
    if name=='Eye_L_Closed':assembled.alpha_composite(layers['Eye_L_Happy'])
    if name=='Mouth_Large':assembled.alpha_composite(layers['Mouth_Happy'])
assembled.save(OUT/'proofs/happy-assembled.png')
def flat(im):
    bg=Image.new('RGBA',im.size,(64,72,104,255));bg.alpha_composite(im.convert('RGBA'));return bg.convert('RGB')
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',23)
panels=[('承認済みの見本',Image.open(OUT/'inputs/happy-reference-face.png')),
        ('前の案（v26）',Image.open(ROOT/'assets/ciel/generated/v26/proofs/happy-assembled.png').crop(CROP)),
        ('見本から取り出した案（v27）',assembled.crop(CROP))]
board=Image.new('RGB',(1575,565),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,picture) in enumerate(panels):
    board.paste(flat(picture).resize((525,525),Image.Resampling.LANCZOS),(i*525,40));draw.text((i*525+10,8),label,font=font,fill='white')
board.save(OUT/'proofs/happy-face-comparison.png')
board=Image.new('RGB',(868,619),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,picture) in enumerate([('前の案（v26）',Image.open(ROOT/'assets/ciel/generated/v26/proofs/happy-assembled.png')),('今回の案（v27）',assembled)]):
    board.paste(flat(picture).resize((434,579),Image.Resampling.LANCZOS),(i*434,40));draw.text((i*434+10,8),label,font=font,fill='white')
board.save(OUT/'proofs/happy-front-comparison.png')
# Compare the extraction's shape to the actual reference before registration.
reference=Image.open(OUT/'inputs/happy-reference-face.png').convert('RGBA')
refboxes={'Eye_R_Happy':(145,290,410,420),'Eye_L_Happy':(585,285,845,420),'Mouth_Happy':(420,515,570,595)}
board=Image.new('RGB',(840,240*3),(224,227,234));draw=ImageDraw.Draw(board)
for i,name in enumerate(specs):
    orig=reference.crop(refboxes[name]);layer=layers[name];crop=layer.getbbox();piece=layer.crop((crop[0]-5,crop[1]-5,crop[2]+5,crop[3]+5))
    for j,(label,picture) in enumerate([('見本の描かれた部分',orig),('抽出・配置後（透明素材）',piece)]):
        bg=Image.new('RGBA',picture.size,(224,227,234,255));bg.alpha_composite(picture.convert('RGBA'));picture=bg.convert('RGB');picture.thumbnail((400,190))
        board.paste(picture,(j*420+(420-picture.width)//2,i*240+45+(190-picture.height)//2));draw.text((j*420+10,i*240+8),label,font=font,fill=(25,32,48))
board.save(OUT/'proofs/reference-extraction-details.png')
assert all(im.size==SIZE and im.mode=='RGBA' and im.getbbox() for im in layers.values())
assert np.array_equal(np.asarray(shifted)[:-41],np.asarray(blush)[41:])
assert json.loads((OUT/'current-before.json').read_text())==current_hashes()
(OUT/'placement.json').write_text(json.dumps(placements,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'verification.json').write_text(json.dumps({'current_unchanged':True,'layer_count':4,'canvas':list(SIZE),
    'blush_pixels_preserved_after_translation':True,'blush_preview_weight':.45,'reference_pixel_identical':False,
    'reference_note':'Image tool extraction has redraw differences; details show actual source and extraction',
    'rig_imported':False},indent=2)+'\n',encoding='utf-8')
print('V27_REFERENCE_MATERIALS_READY')
