"""Edit skin chroma using the approved master's face and current abdomen.

Preserves alpha, luminance, mesh geometry and blush artwork. Preview edits atlas
pixels only in the selected native drawable UV regions; never publishes a rig.
"""
from pathlib import Path
import importlib.util,json,hashlib,sys
import numpy as np
from PIL import Image,ImageDraw,ImageFilter,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py')
r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
out=ROOT/'assets/ciel/generated/v46';proof=ROOT/'assets/ciel/rig/proofs/skin-v46'
(out/'layers').mkdir(parents=True,exist_ok=True);proof.mkdir(parents=True,exist_ok=True)
weights=np.array([.2126,.7152,.0722])
def median(path,box):
    a=np.asarray(Image.open(path).convert('RGBA').crop(box));rgb=a[:,:,:3].astype(float)
    mask=(a[:,:,3]>240)&(rgb.min(2)>225)&(np.ptp(rgb,axis=2)<25)
    return np.median(rgb[mask],axis=0)
src=ROOT/'assets/ciel/current/layers'
face=median(src/'Face_Skin.png',(1040,1110,1160,1190))
belly=median(src/'Body.png',(920,2420,1290,2590))
master=median(ROOT/'assets/ciel/master/ciel-upper-body-2x.png',(1040,1110,1160,1190))
# Match the abdomen's neutral chroma while retaining the face's brightness.
delta=(belly-belly@weights)-(face-face@weights)
assert abs(delta@weights)<1e-9
def recolor(a):
    b=a.copy();rgb=a[:,:,:3].astype(float)
    bright=np.clip((rgb.min(2)-185)/35,0,1)
    low_chroma=np.clip((45-np.ptp(rgb,axis=2))/15,0,1)
    warm=np.clip((rgb[:,:,0]-rgb[:,:,2]+2)/4,0,1)
    w=bright*low_chroma*warm
    b[:,:,:3]=np.clip(np.round(rgb+w[:,:,None]*delta),0,255).astype(np.uint8)
    return b
names=['Face_Skin','Mouth_Skin_Upper','Mouth_Skin_Lower',
       'Eye_R_LidSkin_Upper','Eye_R_LidSkin_Lower','Eye_L_LidSkin_Upper','Eye_L_LidSkin_Lower']
records=[]
for name in names:
    p=src/(name+'.png');a=np.asarray(Image.open(p).convert('RGBA'));b=recolor(a)
    assert np.array_equal(a[:,:,3],b[:,:,3])
    Image.fromarray(b).save(out/'layers'/(name+'.png'))
    records.append({'name':name,'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                    'changed_pixels':int(np.any(a[:,:,:3]!=b[:,:,:3],axis=2).sum())})
m=cc.Model(ROOT/'assets/ciel/runtime/Ciel.model3.json');m.update();original=r.load_textures(m)
modified=[];atlas_masks=[]
for i,tex in enumerate(original):
    h,w=tex.shape[:2];mask=Image.new('L',(w,h));draw=ImageDraw.Draw(mask)
    for d in m.drawables():
        if d['id'] not in names or d['texture']!=i:continue
        uv=d['uv'];points=np.c_[uv[:,0]*w,(1-uv[:,1])*h]
        for tri in d['tri']:draw.polygon([tuple(points[k]) for k in tri],fill=255)
    # Include the antialiasing border inside the atlas's 3px packing margin.
    mask=mask.filter(ImageFilter.MaxFilter(3));atlas_masks.append(mask)
    a=np.round(tex*255).astype(np.uint8);b=recolor(a);selected=np.asarray(mask)>0
    b[~selected]=a[~selected];assert np.array_equal(a[:,:,3],b[:,:,3])
    modified.append(b.astype(np.float32)/255)
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',20)
def render(values,after,crop,width):
    m.reset();assert not m.set(values);m.update()
    return r.render(m,modified if after else original,2*width/(crop[2]-crop[0]),crop).resize(
        (width,round(width*(crop[3]-crop[1])/(crop[2]-crop[0]))),Image.Resampling.LANCZOS)
poses=[('neutral','通常',{}),('happy','嬉しい',{'ParamHappy':1,'ParamEyeLSmile':1,'ParamEyeRSmile':1}),
       ('embarrassed','照れ',{'ParamEmbarrassed':1,'ParamEarFold':1}),
       ('teary','半泣き',{'ParamTeary':1,'ParamEarFold':1,'ParamCheek':.25})]
for name,label,values in ([] if '--body-only' in sys.argv else poses):
    board=Image.new('RGB',(1200,640),(64,72,104));draw=ImageDraw.Draw(board)
    for col,after in enumerate((False,True)):
        board.paste(render(values,after,(550,650,1600,1700),600),(col*600,40))
        draw.text((col*600+8,7),label+' / '+('肌色調整案' if after else '現状'),font=font,fill='white')
    board.save(proof/(name+'-comparison.png'))
board=Image.new('RGB',(1200,955),(64,72,104));draw=ImageDraw.Draw(board)
for col,after in enumerate((False,True)):
    board.paste(render({},after,(150,0,2050,2896),600),(col*600,40))
    draw.text((col*600+8,7),'顔・首・お腹 / '+('調整案' if after else '現状'),font=font,fill='white')
board.save(proof/'face-and-body-comparison.png')
if '--body-only' in sys.argv:
    print('FACE_AND_BODY_PREVIEW_READY');sys.exit(0)
board=Image.new('RGB',(1500,590),(64,72,104));draw=ImageDraw.Draw(board)
crop=(550,650,1600,1805)
ref=Image.open(ROOT/'assets/ciel/master/ciel-upper-body-2x.png').convert('RGBA').crop(crop)
bg=Image.new('RGBA',ref.size,(64,72,104,255));bg.alpha_composite(ref)
for i,title in enumerate(('マスター','現状','肌色調整案')):draw.text((i*500+8,7),title,font=font,fill='white')
board.paste(bg.convert('RGB').resize((500,550),Image.Resampling.LANCZOS),(0,40))
board.paste(render({},False,crop,500),(500,40));board.paste(render({},True,crop,500),(1000,40))
board.save(proof/'master-comparison.png')
data={'method':'non-generative skin chroma correction','new_generation':False,'approved':False,
      'reference':'assets/ciel/master/ciel-upper-body-2x.png','face_sample_rgb':face.tolist(),
      'master_face_sample_rgb':master.tolist(),'body_abdomen_sample_rgb':belly.tolist(),
      'chroma_delta_rgb':delta.tolist(),'luminance_delta_before_rounding':float(delta@weights),
      'layers':records,'alpha_unchanged':True,'geometry_unchanged':True,'blush_artwork_unchanged':True,
      'neck_and_body_unchanged':True,'cmo_updated':False,'unity_updated':False}
(out/'generation-provenance.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(proof/'material-preview-verification.json').write_text(json.dumps({'stage':'texture color preview','alpha_unchanged':True,
    'geometry_unchanged':True,'modified_materials':names,'poses_rendered':[v[0] for v in poses],
    'cmo_updated':False,'unity_updated':False},indent=2)+'\n',encoding='utf-8')
print('SKIN_TONE_PREVIEW_READY',delta)
