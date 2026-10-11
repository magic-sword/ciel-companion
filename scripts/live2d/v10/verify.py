"""Render review plates and measure exported PNGs, without a Cubism dependency."""
from pathlib import Path
import json,hashlib,math,re,warnings
import numpy as np
from PIL import Image,ImageDraw,ImageFont
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from scipy import ndimage as ndi

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'assets/ciel/layers/v10'; GEN=ROOT/'assets/ciel/generated/v10'; SRC=ROOT/'assets/ciel/layers/v9'
W,H=2172,2896
state=json.loads((OUT/'layer-state.json').read_text(encoding='utf-8'))
rows=state['layers']
images={r['name']:Image.open(ROOT/r['path']).convert('RGBA') for r in rows}
fontpath='C:/Windows/Fonts/arial.ttf'
font=ImageFont.truetype(fontpath,23); smallfont=ImageFont.truetype(fontpath,17)
def savejson(path,d): path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def translate(im,dx,dy):
    out=Image.new('RGBA',(W,H)); out.paste(im,(dx,dy)); return out
def render(eyes='open',mouth='closed',exclude=(),offsets=None,clip_eyes=False):
    out=Image.new('RGBA',(W,H))
    for r in rows:
        n=r['name']; visible=r['visible']
        if n.startswith('Mouth_') and r['group']: visible=r['group']=='mouth_'+mouth
        if n.startswith('Eye_'):
            visible=(n.endswith('_Closed') if eyes=='closed' else not n.endswith('_Closed'))
        if any(n.startswith(p) for p in exclude): visible=False
        if visible:
            im=images[n]
            if offsets and n in offsets: im=translate(im,*offsets[n])
            if clip_eyes and n.startswith('Eye_') and n.endswith(('_Iris','_Highlight')):
                a=np.array(im); mask=np.asarray(images[n[:5]+'_Sclera'])[:,:,3]
                a[:,:,3]=np.uint8(np.rint(a[:,:,3].astype(float)*mask/255))
                im=Image.fromarray(a)
            out.alpha_composite(im)
    return out
def background(im,dark=False):
    c=Image.new('RGBA',im.size,(58,64,82,255) if dark else (231,233,240,255)); c.alpha_composite(im); return c.convert('RGB')
def plate(name,items,crop,scale,cols=2,dark=False):
    width=round((crop[2]-crop[0])*scale); height=round((crop[3]-crop[1])*scale)
    result=Image.new('RGB',(cols*width,math.ceil(len(items)/cols)*(height+54)),(246,247,250)); d=ImageDraw.Draw(result)
    for i,(label,im) in enumerate(items):
        x=(i%cols)*width; y=(i//cols)*(height+54)
        d.text((x+12,y+8),label,font=font,fill=(30,35,50))
        d.text((x+12,y+33),f'{scale:g}x | crop {crop}',font=smallfont,fill=(70,75,90))
        result.paste(background(im.crop(crop),dark).resize((width,height),Image.Resampling.LANCZOS),(x,y+54))
    result.save(OUT/'proofs'/name)

neutral=render(); neutral.save(OUT/'proofs/compose.png')
old=Image.open(SRC/'compose.png').convert('RGBA')
plate('compare-face.png',[('v9 approved',old),('v10 reconstructed',neutral)],(450,230,1710,1480),.7)
plate('compare-upper.png',[('v9 approved',old),('v10 reconstructed',neutral)],(0,0,W,H),.30)
closed=render(eyes='closed'); sm=render(mouth='small'); lg=render(mouth='large')
plate('expressions.png',[('Open / closed smile',neutral),('Closed eyes / closed smile',closed),('Open / small mouth',sm),('Open / large mouth',lg)],(700,820,1510,1400),.85)
plate('expressions-front.png',[('Open / closed smile',neutral),('Closed eyes / closed smile',closed),('Small mouth',sm),('Large mouth',lg)],(420,200,1760,1700),.45,4)
nohair=render(exclude=('Hair_','Ear_','Face_Shadow_Hair'))
plate('face-without-hair.png',[('Face / no hair, ears or cast shadow',nohair),('Closed eyes / no hair',render(eyes='closed',exclude=('Hair_','Ear_','Face_Shadow_Hair')))],(600,470,1650,1450),.85)
plate('eyes-detail.png',[(n,images[n]) for n in images if n.startswith('Eye_')],(730,910,1475,1165),1,2)
plate('mouth-detail.png',[(n,images[n]) for n in images if n.startswith('Mouth_')],(1010,1190,1210,1360),2,4)
gaze=[]
for dx,dy in [(-20,0),(20,0),(0,-20),(0,20)]:
    offsets={n:(dx,dy) for n in images if n.startswith('Eye_') and n.endswith(('_Iris','_Highlight'))}
    gaze.append((f'Iris + highlight ({dx:+d},{dy:+d}) px / sclera clip',render(offsets=offsets,clip_eyes=True)))
plate('move-iris-clipped.png',gaze,(740,900,1470,1165),1,2)

# Individual bounded thumbnails, with part names and actual magnification.
tw,th=350,390; cols=4; per_page=20
for page in range(math.ceil(len(rows)/per_page)):
    subset=rows[page*per_page:(page+1)*per_page]
    atlas=Image.new('RGB',(tw*cols,th*math.ceil(len(subset)/cols)),(234,236,244)); d=ImageDraw.Draw(atlas)
    for i,r in enumerate(subset):
        im=images[r['name']]; box=im.getbbox(); x=(i%cols)*tw; y=(i//cols)*th
        d.text((x+8,y+9),r['name'],font=smallfont,fill=(25,30,45))
        if box:
            crop=im.crop(box); scale=min((tw-24)/crop.width,(th-75)/crop.height,3)
            tile=background(crop,True).resize((round(crop.width*scale),round(crop.height*scale)),Image.Resampling.LANCZOS)
            atlas.paste(tile,(x+(tw-tile.width)//2,y+53))
            d.text((x+8,y+32),f'{scale:.3f}x | {"ON" if r["visible"] else "OFF"} | {box}',font=smallfont,fill=(50,55,70))
    atlas.save(OUT/'proofs'/f'exploded-{page+1:02d}.png')

# Orthogonal and diagonal independent translations. Each moving part has its own
# full-resolution inspection image; the atlas is only a navigation aid.
groups={
 'Hair_Front_2':['Hair_Front_2'],
 'Hair_Front_1':['Hair_Front_1'],
 'Hair_Front_3':['Hair_Front_3'],
 'Hair_Side_R_Inner':['Hair_Side_R_Inner'],
 'Hair_Side_L_Inner':['Hair_Side_L_Inner'],
 'Hair_Side_R_LongFront':['Hair_Side_R_LongFront'],
 'Hair_Side_L_LongFront':['Hair_Side_L_LongFront'],
 'Ear_R':[n for n in images if n.startswith('Ear_R')],
 'Ear_L':[n for n in images if n.startswith('Ear_L')],
 'Choker_Buckle':['Choker_Buckle'],
}
directions=[(-20,0),(20,0),(0,-20),(0,20),(-20,-20),(20,20)]
coverage=[]
hairnames=[n for n in images if n.startswith(('Hair_Front_','Hair_Side_'))]
original_hair=np.asarray(Image.open(SRC/'Hair_FrontAssembly.png'))[:,:,3]
interior=ndi.distance_transform_edt(original_hair>250)>32
for group,names in groups.items():
    tests=[(f'{group} ({dx:+d},{dy:+d}) px',render(offsets={n:(dx,dy) for n in names})) for dx,dy in directions]
    crop=(420,260,1770,1790) if group.startswith('Hair') else ((420,0,1770,880) if group.startswith('Ear') else (900,1350,1320,1570))
    plate('move-'+group+'.png',tests,crop,.40 if group.startswith(('Hair','Ear')) else 1.2,3,True)
    if group.startswith('Hair'):
        for dx,dy in directions:
            trans=np.ones((H,W),np.float32)
            for hn in hairnames:
                im=translate(images[hn],dx,dy) if hn in names else images[hn]
                trans *= 1-np.asarray(im)[:,:,3].astype(np.float32)/255
            gaps=interior&(trans>15/255)
            ys,xs=np.where(gaps)
            coverage.append(dict(part=group,offset=[dx,dy],interior_pixels_below_alpha_240=int(gaps.sum()),
                bounds=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)] if len(xs) else None))

# Separate uncovered backing views, since unchanged front pixels alone cannot
# prove that a hidden root or eyelid is complete.
plate('hidden-hair.png',[(n,images[n]) for n in ['Hair_Back','Hair_Front_1','Hair_Front_2','Hair_Front_3',
    'Hair_Side_R_Inner','Hair_Side_L_Inner','Hair_Side_R_LongFront','Hair_Side_L_LongFront']],(400,260,1775,1780),.3,3,True)

tests=[]
for r in rows:
    n=r['name']; im=images[n]; a=np.asarray(im)
    tests.append(dict(name=n,size=list(im.size),mode=im.mode,nonempty=bool(im.getbbox()),transparent=bool((a[:,:,3]==0).any()),
        sha256=hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()))
assert len({r['name'] for r in rows})==len(rows)
assert all(re.fullmatch('[A-Za-z0-9_]+',r['name']) for r in rows)
assert all(t['size']==[W,H] and t['mode']=='RGBA' and t['nonempty'] and t['transparent'] for t in tests)
before=json.loads((GEN/'input-sha256.json').read_text(encoding='utf-8'))
unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in before.items())
assert unchanged
metrics={}
for label,box in [('full',(0,0,W,H)),('face',(700,790,1510,1400)),('eyes',(740,910,1470,1150)),('mouth',(1030,1210,1190,1340))]:
    a=np.asarray(background(old).crop(box)).astype(float); b=np.asarray(background(neutral).crop(box)).astype(float)
    diff=np.abs(a-b)
    metrics[label]=dict(mean_absolute_rgb=float(diff.mean()),rms=float(np.sqrt((diff**2).mean())),pixels_changed=int((diff.max(2)>0).sum()),pixels_over_10=int((diff.max(2)>10).sum()),maximum=float(diff.max()))
diff=np.abs(np.asarray(background(old)).astype(float)-np.asarray(background(neutral)).astype(float))
Image.fromarray(np.uint8(np.minimum(diff*5,255))).save(OUT/'proofs/difference-5x.png')
savejson(OUT/'validation.json',dict(canvas=[W,H],layer_count=len(rows),normal_visible=sum(r['visible'] for r in rows),source_unchanged=unchanged,
    layers=tests,comparison=metrics,translation_cases=len(groups)*len(directions),hair_interior_coverage=coverage,
    coverage_definition='元の髪alpha>250の外縁から32px以上内側。髪7層だけを合成し、alpha<240の穴を数える。外形の移動で現れる顔は判定外。',
    translation_scope='PNG平行移動の確認図。メッシュ変形・連続補間・Cubism未確認。',
    psd_roundtrip='未確認',cubism='未確認',unity='未確認'))
print(json.dumps(dict(layers=len(rows),comparison=metrics,source_unchanged=unchanged),ensure_ascii=False,indent=2))
