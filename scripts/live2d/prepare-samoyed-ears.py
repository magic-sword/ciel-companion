"""Separate contextual ear artwork and preview it behind the unchanged model hair.

This is an image-editing separation and static material preview, not a CMO/SDK export.
"""
from pathlib import Path
import sys, json, hashlib, importlib.util
import numpy as np
from PIL import Image, ImageDraw, ImageFont
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer', HERE/'render-moc.py')
r=importlib.util.module_from_spec(sp); sp.loader.exec_module(r)
revision=int(sys.argv[1]) if len(sys.argv)>1 else 41
assert revision in (41,42)
OUT=ROOT/f'assets/ciel/generated/v{revision}'
PROOF=ROOT/f'assets/ciel/rig/proofs/samoyed-ears-v{revision}'
for p in (OUT/'parts',OUT/'layers',PROOF): p.mkdir(parents=True,exist_ok=True)
src=OUT/'edits/teary-samoyed-ears-context.png'
im=Image.open(src).convert('RGBA'); a=np.asarray(im).copy()
W,H=im.size
assert (W,H)==(1354,1161), im.size
# Mask paths extend under the existing crown hair. No pixels are painted or generated here.
polys={
 'R':[(175,175),(565,175),(530,208),(490,233),(454,261),(421,294),(394,325),(375,355),(356,392),(338,439),(320,455),(175,455)],
 'L':[(789,175),(1190,175),(1190,455),(1034,455),(1016,439),(998,392),(979,355),(960,325),(933,294),(900,261),(864,233),(824,208)]
}
if revision==42:
    right=[(20,170),(565,170),(540,207),(500,235),(465,265),(428,310),(395,355),(365,405),(340,452),(311,520),(285,590),(268,647),(230,640),(225,605),(190,590),(155,575),(20,540)]
    polys={'R':right,'L':[(W-x,y) for x,y in reversed(right)]}
# The generation used a slate background; remove that matte only within ear regions.
alpha=np.clip((a[:,:,:3].max(2).astype(float)-110)/40,0,1)
s=1750/W; offset=[200,50]
parts={}; metadata={}
for side,points in polys.items():
    mask=Image.new('L',im.size); ImageDraw.Draw(mask).polygon(points,fill=255)
    b=a.copy(); b[:,:,3]=np.round(alpha*np.asarray(mask)).astype(np.uint8)
    b[b[:,:,3]==0]=0
    piece=Image.fromarray(b); name=f'Ear_{side}_Folded'
    piece.save(OUT/'parts'/(name+'.png'))
    layer=piece.transform((2172,2896),Image.Transform.AFFINE,
        (1/s,0,-offset[0]/s,0,1/s,-offset[1]/s),Image.Resampling.BICUBIC)
    layer.save(OUT/'layers'/(name+'.png')); parts[side]=layer
    metadata[name]={'source_bbox':piece.getbbox(),'target_bbox':layer.getbbox()}

model=cc.Model(ROOT/'assets/ciel/rig/drafts/teary/runtime/Ciel.model3.json')
textures=r.load_textures(model)
eartex=[np.asarray(parts[side]).astype(np.float32)/255 for side in 'RL']
class Preview:
    canvas=model.canvas
    def drawables(self):
        ds=model.drawables()
        for side,texture in zip('RL',range(len(textures),len(textures)+2)):
            d=next(d for d in ds if d['id']==f'Ear_{side}_Folded')
            # Replace only the ear's static material plane. Native face and hair are untouched.
            d.update(pos=np.array([[0,0],[2172,0],[2172,2896],[0,2896]],float),
                uv=np.array([[0,1],[1,1],[1,0],[0,0]],float),
                tri=np.array([[0,1,2],[0,2,3]]),texture=texture)
        return ds
preview=Preview(); font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',20)
crop=(200,-150,1950,1550); scale=.35; size=(612,595)
def render(m,t):
    return r.render(m,t,scale*2,crop).resize(size,Image.Resampling.LANCZOS)
poses=[('半泣き',{'ParamTeary':1,'ParamCheek':.25}),
       ('ぷんすか',{'ParamAngry':1}),('しょんぼり',{'ParamSad':1}),
       ('困り',{'ParamTroubled':1}),('照れ',{'ParamEmbarrassed':1})]
board=Image.new('RGB',(size[0]*2,(size[1]+38)*len(poses)),(64,72,104)); dr=ImageDraw.Draw(board)
unchanged=[]
for row,(title,values) in enumerate(poses):
    model.reset(); assert not model.set({**values,'ParamEarFold':1}); model.update()
    before=render(model,textures); after=render(preview,textures+eartex)
    y=row*(size[1]+38)
    for col,(label,pic) in enumerate([('現在',before),('サモエド耳の修正案',after)]):
        board.paste(pic,(col*size[0],y+38)); dr.text((col*size[0]+8,y+5),title+'：'+label,font=font,fill='white')
    # All source drawable data except the two substituted ear planes are retained.
    old={d['id']:d for d in model.drawables()}; new={d['id']:d for d in preview.drawables()}
    for name,d in old.items():
        if name in ('Ear_R_Folded','Ear_L_Folded'): continue
        assert np.array_equal(d['pos'],new[name]['pos']) and d['opacity']==new[name]['opacity'],name
    unchanged.append(title)
    if row==0:
        after.save(PROOF/'teary.png')
        board.crop((0,0,size[0]*2,size[1]+38)).save(PROOF/'teary-comparison.png')
        after_teary=after; before_teary=before
board.save(PROOF/'shared-expressions-comparison.png')
model.reset(); model.update()
normal=render(model,textures)
comparison=Image.new('RGB',(size[0]*3,size[1]+38),(64,72,104)); cd=ImageDraw.Draw(comparison)
for col,(label,pic) in enumerate([('通常：耳の量感の基準',normal),('半泣き：現在の耳',before_teary),('半泣き：大きさを見直した耳',after_teary)]):
    comparison.paste(pic,(col*size[0],38));cd.text((col*size[0]+8,5),label,font=font,fill='white')
comparison.save(PROOF/'normal-and-teary-comparison.png')
# A material sheet on slate reveals the separation boundaries for review.
sheet=Image.new('RGBA',(900,420),(64,72,104,255))
for col,side in enumerate('RL'):
    box=parts[side].getbbox(); pic=parts[side].crop(box); pic.thumbnail((420,360),Image.Resampling.LANCZOS)
    sheet.alpha_composite(pic,(col*450+15,25))
sheet.convert('RGB').save(PROOF/'ear-parts.png')
data={'method':'contextual image edit followed by non-generative mask separation',
 'generator':'image_gen','image_edit_count':3 if revision==42 else 2,'selected_edit':3 if revision==42 else 2,
 'rejected_edit_reason':'First proposal produced long floppy ears instead of short folded triangular ears',
 'reference':'assets/ciel/rig/proofs/teary-v40/teary.png',
 'additional_references':['inputs/normal-ears-reference.png','assets/ciel/generated/v22/expressions/teary.png'] if revision==42 else [],
 'previous_candidate_rejected': 'v41: visible size change was too small' if revision==42 else None,
 'original':'edits/teary-samoyed-ears-context.png',
 'original_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
 'shared_scale':s,'offset':offset,'parts':metadata,
 'preview_method':'Static material planes substituted at native folded-ear render order; all other native drawables unchanged',
 'reviewed_expressions':unchanged,'approved':False,'cubism_integrated':False,'unity_applied':False}
(OUT/'generation-provenance.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(PROOF/'verification.json').write_text(json.dumps({'preview_only':True,'previous_non_ear_drawables_unchanged':unchanged,'canvas':[2172,2896],'alpha_separated':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('SAMOYED_EAR_PREVIEW_READY',metadata)
