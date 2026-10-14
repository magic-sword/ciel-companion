"""Separate the master's crown with image editing, then preview behind native hair.

No generative image model; no changes to the CMO or current package.
"""
from pathlib import Path
import importlib.util, hashlib, json, sys
import numpy as np
from scipy.ndimage import distance_transform_edt
from PIL import Image, ImageDraw, ImageFilter, ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py')
r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
out=ROOT/'assets/ciel/generated/v45';proof=ROOT/'assets/ciel/rig/proofs/crown-v45'
for p in (out/'parts',out/'layers',proof):p.mkdir(parents=True,exist_ok=True)
source=ROOT/'assets/ciel/master/ciel-upper-body-2x.png'
master=Image.open(source).convert('RGBA');assert master.size==(2172,2896)
# Crown silhouette follows the master. Lower and side cuts are hidden by front hair.
polygon=[(862,365),(936,280),(972,266),(1009,260),(1045,259),(1080,260),
         (1110,259),(1150,259),(1190,266),(1254,280),(1355,385),
         (1360,505),(855,505)]
mask=Image.new('L',master.size);ImageDraw.Draw(mask).polygon(polygon,fill=255)
mask=mask.filter(ImageFilter.GaussianBlur(.65))
a=np.asarray(master).copy();alpha=np.asarray(mask).astype(float)/255
# Feather the covered lower edge; preserve the visible upper contour.
y=np.arange(2896)[:,None];alpha*=np.clip((505-y)/50,0,1)
a[:,:,3]=np.round(alpha*255).astype(np.uint8)
# The source ahoge overlaps the crown. Replace only that overlap with a nearby
# strip of master hair, translated without scaling; the native ahoge remains.
repair=Image.new('L',master.size)
ImageDraw.Draw(repair).polygon([(999,250),(1068,250),(1078,279),(1094,307),
                              (1115,335),(1085,349),(1053,327),(1025,290)],fill=255)
repair=repair.filter(ImageFilter.GaussianBlur(3))
weight=np.asarray(repair).astype(float)/255
rgb=a[:,:,:3].astype(float)
# Adjacent crown contains the same soft blue-purple hair shading.
donor=np.asarray(master)[:,:,:3].astype(float)
donor=np.roll(donor,-130,axis=1)
donor=donor[np.clip(np.arange(2896)+15,270,290)]
rgb=rgb*(1-weight[:,:,None])+donor*weight[:,:,None]
a[:,:,:3]=np.round(rgb).astype(np.uint8)
# Retouch dark cutout debris along the source contour with its nearest intact
# hair pixels, then use the clean contour mask for alpha (no black matte holes).
region=a[230:510,850:1365,:3]
bad=region.min(axis=2)<140
nearest=distance_transform_edt(bad,return_distances=False,return_indices=True)
region[bad]=region[nearest[0][bad],nearest[1][bad]]
a[a[:,:,3]==0]=0
part=Image.fromarray(a);part.save(out/'parts/Hair_Crown.png')
# Native hair is displaced by approximately -4 px from the source canvas.
layer=part.transform(master.size,Image.Transform.AFFINE,(1,0,0,0,1,4),Image.Resampling.BICUBIC)
layer.save(out/'layers/Hair_Crown.png')
(out/'placement.json').write_text(json.dumps({'canvas':list(master.size),'source':str(source.relative_to(ROOT)).replace('\\','/'),'part':'Hair_Crown','offset':[0,-4],'scale':1,'source_mask_polygon':polygon,'source_ahoge_overlap_repair':'adjacent master crown strip (x+130, y clamped to 270..290), feathered 3px','contour_cleanup':'dark cutout debris replaced with nearest intact hair pixels','target_bbox':layer.getbbox()},indent=2)+'\n',encoding='utf-8')
model_path=ROOT/'assets/ciel/rig/drafts/jitome/runtime/Ciel.model3.json'
if not model_path.exists():model_path=ROOT/'.local/crown-adoption/adopted-jitome-draft/runtime/Ciel.model3.json'
m=cc.Model(model_path);textures=r.load_textures(m)
textures.append(np.asarray(layer).astype(np.float32)/255)
class Preview:
    canvas=m.canvas
    def __init__(self,enabled):self.enabled=enabled
    def drawables(self):
        ds=m.drawables()
        if self.enabled:
            d=next(d for d in ds if d['id']=='Hair_Back').copy()
            # Independent material plane; native front hair, ears and ahoge overlap it.
            d.update(id='Hair_Crown',index=len(ds),render_order=d['render_order']+.5,
                opacity=1,visible=True,texture=len(textures)-1,masks=[],
                pos=np.array([[0,0],[2172,0],[2172,2896],[0,2896]],float),
                uv=np.array([[0,1],[1,1],[1,0],[0,0]],float),tri=np.array([[0,1,2],[0,2,3]]))
            ds.append(d)
        return ds
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',20)
def draw(values,enabled,crop,width):
    m.reset();assert not m.set(values);m.update()
    return r.render(Preview(enabled),textures,2*width/(crop[2]-crop[0]),crop).resize(
        (width,round(width*(crop[3]-crop[1])/(crop[2]-crop[0]))),Image.Resampling.LANCZOS)
poses=[('neutral','通常',{}),('jitome','ジト目',{'ParamJitome':1,'ParamEar':-.35,'ParamCheek':.15}),
       ('excited','わくわく',{'ParamExcited':1,'ParamEar':1}),
       ('teary','半泣き',{'ParamTeary':1,'ParamEarFold':1})]
for name,label,values in poses:
    board=Image.new('RGB',(1000,540),(64,72,104));d=ImageDraw.Draw(board)
    for col,enabled in enumerate((False,True)):
        board.paste(draw(values,enabled,(250,0,1950,1700),500),(500*col,40))
        d.text((500*col+8,7),label+' / '+('素材修正案' if enabled else '現状'),font=font,fill='white')
    board.save(proof/(name+'-comparison.png'))
board=Image.new('RGB',(1500,360),(64,72,104));d=ImageDraw.Draw(board)
crop=(650,150,1500,650)
ref=master.crop(crop);bg=Image.new('RGBA',ref.size,(64,72,104,255));bg.alpha_composite(ref)
board.paste(bg.convert('RGB').resize((500,294)),(0,40))
for col,title in enumerate(('マスター','現状','頭頂部の素材修正案')):d.text((500*col+8,7),title,font=font,fill='white')
board.paste(draw({},False,crop,500),(500,40));board.paste(draw({},True,crop,500),(1000,40));board.save(proof/'master-crown-comparison.png')
bg=Image.new('RGBA',(850,450),(64,72,104,255));bg.alpha_composite(layer.crop((650,150,1500,600)));bg.convert('RGB').save(proof/'crown-part.png')
(out/'generation-provenance.json').write_text(json.dumps({'method':'non-generative master extraction and feathered clone repair','new_generation':False,'source':str(source.relative_to(ROOT)).replace('\\','/'),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'approved':False,'part':'Hair_Crown','source_hair_scaling':False},indent=2)+'\n',encoding='utf-8')
(proof/'material-preview-verification.json').write_text(json.dumps({'stage':'static material preview','native_model':'assets/ciel/rig/drafts/jitome/runtime/Ciel.model3.json','source_image_scaled':False,'source_dimensions':[2172,2896],'other_materials_changed':False,'poses_rendered':[q[0] for q in poses],'cmo_updated':False,'unity_updated':False},indent=2)+'\n',encoding='utf-8')
print('CROWN_MATERIAL_READY')
