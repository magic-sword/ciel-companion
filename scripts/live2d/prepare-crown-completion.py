"""Complete occluded crown sides with cloned hair, keeping the approved center.

Image-editing material preview; current CMO and SDK remain untouched.
"""
from pathlib import Path
import importlib.util,json,sys,hashlib,argparse
import numpy as np
from scipy.interpolate import PchipInterpolator,RegularGridInterpolator
from PIL import Image,ImageDraw,ImageFilter,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-layers',default='assets/ciel/current/layers')
parser.add_argument('--source-runtime',default='assets/ciel/runtime')
parser.add_argument('--output',default='assets/ciel/generated/v47')
parser.add_argument('--proof-output',default='assets/ciel/rig/proofs/crown-v47')
parser.add_argument('--roll-only',action='store_true');parser.add_argument('--before',action='store_true')
args=parser.parse_args()
out=ROOT/args.output;proof=ROOT/args.proof_output
if (out/'generation-provenance.json').exists() and json.loads((out/'generation-provenance.json').read_text(encoding='utf-8')).get('approved'):
    raise SystemExit('Approved originals are protected. Supply a separate --output and --proof-output.')
sources=ROOT/args.source_layers
(out/'layers').mkdir(parents=True,exist_ok=True);proof.mkdir(parents=True,exist_ok=True)
source=sources/'Hair_Crown.png'
im=Image.open(source).convert('RGBA');a=np.asarray(im);H,W=a.shape[:2]
anchors=[(760,400),(835,332),(915,286),(970,264),(1045,253),
         (1100,253),(1170,258),(1240,272),(1310,293),(1390,334),(1460,400)]
curve=PchipInterpolator(*np.array(anchors).T)
xx=np.arange(760,1461);yy=curve(xx)
mask=Image.new('L',im.size)
ImageDraw.Draw(mask).polygon([(int(x),float(y)) for x,y in zip(xx,yy)]+[(1460,530),(760,530)],fill=255)
mask=mask.filter(ImageFilter.GaussianBlur(.65))
y,x=np.indices((H,W));alpha=np.asarray(mask).astype(float)/255
alpha*=np.clip((530-y)/50,0,1)
# Extend the visible upper crown's soft blue-purple shading around the sides.
# Samples stay above the master's front-hair line; no ear pixels are cloned.
sx=np.clip(1140+np.abs(x-1100)*.2,1140,1215).astype(int)
top=curve(np.clip(x,760,1460))
sy=np.clip(267+(y-top)*.25,267,286).astype(int)
rgb=a[sy,sx,:3].astype(float)
# Keep the old center and all covered lower artwork, with a feathered join.
keep=Image.new('L',im.size)
ImageDraw.Draw(keep).rectangle((975,270,1210,530),fill=255)
keep=keep.filter(ImageFilter.GaussianBlur(14))
k=np.asarray(keep).astype(float)/255*(a[:,:,3]/255)
rgb=rgb*(1-k[:,:,None])+a[:,:,:3]*k[:,:,None]
b=np.zeros_like(a);b[:,:,:3]=np.round(rgb).astype(np.uint8);b[:,:,3]=np.round(alpha*255).astype(np.uint8)
# Fine outer contour sampled from the master palette, without the old ear seam.
line=Image.new('RGBA',im.size);ImageDraw.Draw(line).line([(int(v),float(w)) for v,w in zip(xx,yy)],fill=(190,196,216,100),width=2)
result=Image.fromarray(b);result.alpha_composite(line);b=np.asarray(result).copy();b[b[:,:,3]==0]=0
result=Image.fromarray(b);result.save(out/'layers/Hair_Crown.png')
back_source=sources/'Hair_Back.png'
back=np.asarray(Image.open(back_source).convert('RGBA')).copy()
back[:,:,3]=np.round(back[:,:,3]*np.clip((np.arange(H)[:,None]-500)/100,0,1)).astype(np.uint8)
Image.fromarray(back).save(out/'layers/Hair_Back.png')
bg=Image.new('RGBA',(900,420),(64,72,104,255));bg.alpha_composite(result.crop((650,180,1550,600)))
bg.convert('RGB').save(proof/'crown-part.png')
m=cc.Model(ROOT/args.source_runtime/'Ciel.model3.json');textures=r.load_textures(m);textures.append(b.astype(np.float32)/255)
original_textures=textures
textures=[q.copy() for q in original_textures]
m.update();back_mesh=next(q for q in m.drawables() if q['id']=='Hair_Back')
uv=back_mesh['uv'];axis=int(np.argmax(np.abs(np.corrcoef(np.c_[back_mesh['pos'][:,1],uv].T)[0,1:])))
direction=np.corrcoef(back_mesh['pos'][:,1],uv[:,axis])[0,1]
original_back=np.asarray(Image.open(back_source).convert('RGBA'));bys,bxs=np.nonzero(original_back[:,:,3]>4)
back_y0=max(0,int(bys.min())-6);back_y1=min(H,int(bys.max())+7)
ti=back_mesh['texture'];th,tw=textures[ti].shape[:2]
region=Image.new('L',(tw,th));dr=ImageDraw.Draw(region)
uvpoints=np.c_[uv[:,0]*tw,(1-uv[:,1])*th]
for ids in back_mesh['tri']:dr.polygon([tuple(uvpoints[k]) for k in ids],fill=255)
ay,ax=np.indices((th,tw));coord=(ax+.5)/tw if axis==0 else 1-(ay+.5)/th
fraction=(coord-uv[:,axis].min())/np.ptp(uv[:,axis])
if direction<0:fraction=1-fraction
source_y=back_y0+fraction*(back_y1-back_y0)
fade=np.clip((source_y-500)/100,0,1)
textures[ti][:,:,3]*=np.where(np.asarray(region)>0,fade,1)
oldbox=im.getbbox();oldbox=(oldbox[0]-4,oldbox[1]-4,oldbox[2]+4,oldbox[3]+4)
box=result.getbbox();box=(box[0]-4,box[1]-4,box[2]+4,box[3]+4)
gx=np.linspace(box[0],box[2],33);gy=np.linspace(box[1],box[3],17)
px,py=np.meshgrid(gx,gy);points=np.c_[px.ravel(),py.ravel()]
tri=[]
for j in range(16):
 for i in range(32):
  v=j*33+i;tri.extend([(v,v+1,v+34),(v+34,v+33,v)])
class Preview:
    canvas=m.canvas
    def __init__(self,after):self.after=after
    def drawables(self):
        ds=m.drawables()
        if self.after:
            d=next(q for q in ds if q['id']=='Hair_Crown');assert len(d['pos'])==231
            f=RegularGridInterpolator((np.linspace(oldbox[1],oldbox[3],11),np.linspace(oldbox[0],oldbox[2],21)),d['pos'].reshape(11,21,2),bounds_error=False,fill_value=None)
            d.update(pos=f(points[:,::-1]),uv=np.c_[points[:,0]/W,1-points[:,1]/H],tri=np.array(tri),texture=len(textures)-1)
        return ds
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',20)
def draw(values,after,crop,width):
    m.reset();assert not m.set(values);m.update()
    return r.render(Preview(after),textures if after else original_textures,2*width/(crop[2]-crop[0]),crop).resize((width,round(width*(crop[3]-crop[1])/(crop[2]-crop[0]))),Image.Resampling.LANCZOS)
if '--roll-only' in sys.argv:
    board=Image.new('RGB',(1500,500),(64,72,104));d=ImageDraw.Draw(board)
    for i,angle in enumerate((-30,0,30)):
        board.paste(draw({'ParamTroubled':1,'ParamEarFold':1,'ParamAngleZ':angle},'--before' not in sys.argv,(250,0,1950,1550),500),(i*500,40))
        d.text((500*i+8,7),f'折れ耳 / Z={angle}',font=font,fill='white')
    board.save(proof/('head-roll-before.png' if '--before' in sys.argv else 'head-roll.png'))
    checked=0
    for fold in (0,.5,1):
     for angle in (-30,0,30):
      for hair in (-1,0,1):
        m.reset();m.set({'ParamEarFold':fold,'ParamAngleX':angle,'ParamAngleY':-angle,'ParamAngleZ':angle,'ParamHairFront':hair});m.update()
        original=m.drawables();proposal=Preview(True).drawables()
        for before,after in zip(original,proposal):
            assert np.isfinite(after['pos']).all()
            if before['id']!='Hair_Crown':assert np.array_equal(before['pos'],after['pos'])
        checked+=1
    p=proof/'verification.json';v=json.loads(p.read_text(encoding='utf-8'));v.update(preview_head_roll=[-30,0,30],finite_combined_poses=checked)
    p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8');print('CROWN_ROLL_PREVIEWS_READY',checked);sys.exit(0)
poses=[('troubled','困り',{'ParamTroubled':1,'ParamEarFold':1,'ParamCheek':.2}),
       ('teary','半泣き',{'ParamTeary':1,'ParamEarFold':1,'ParamCheek':.25}),
       ('neutral','通常',{}),('thinking','考え中・未調整',{'ParamEyeBallX':-.5,'ParamEyeBallY':.6,'ParamBrowLY':.4,'ParamMouthForm':-.3})]
for name,title,values in poses:
    board=Image.new('RGB',(1200,640),(64,72,104));d=ImageDraw.Draw(board)
    for col,after in enumerate((False,True)):
        board.paste(draw(values,after,(250,0,1950,1700),600),(col*600,40));d.text((col*600+8,7),title+' / '+('頭頂部の補完案' if after else '現状'),font=font,fill='white')
    board.save(proof/(name+'-comparison.png'))
board=Image.new('RGB',(1200,4*300),(64,72,104));d=ImageDraw.Draw(board)
for row,(name,title,values) in enumerate(poses):
 for col,after in enumerate((False,True)):
    board.paste(draw(values,after,(650,150,1550,540),600),(col*600,row*300+40));d.text((col*600+8,row*300+7),title+' / '+('補完案' if after else '現状'),font=font,fill='white')
board.save(proof/'crown-detail-comparison.png')
board=Image.new('RGB',(1500,500),(64,72,104));d=ImageDraw.Draw(board)
for i,angle in enumerate((-30,0,30)):
    v={'ParamTroubled':1,'ParamEarFold':1,'ParamAngleX':angle,'ParamAngleY':-angle}
    board.paste(draw(v,True,(250,0,1950,1550),500),(i*500,40));d.text((500*i+8,7),f'折れ耳 / X={angle}, Y={-angle}',font=font,fill='white')
board.save(proof/'head-angles.png')
assert np.array_equal(back[600:],original_back[600:])
(out/'generation-provenance.json').write_text(json.dumps({'method':'non-generative crown completion with adjacent hair clone and contour retouch','new_generation':False,'approved':False,'source':str(source.relative_to(ROOT)).replace('\\','/'),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'contour_anchors':anchors,'preserved_center':'feathered x975..1210, below y270','donor_region':[1140,267,1215,286],'target_bbox':result.getbbox(),'back_hair_source':str(back_source.relative_to(ROOT)).replace('\\','/'),'back_hair_source_sha256':hashlib.sha256(back_source.read_bytes()).hexdigest(),'back_hair_alpha_fade_y':[500,600],'back_hair_below_y600_unchanged':True,'cmo_updated':False,'unity_updated':False},indent=2)+'\n',encoding='utf-8')
(proof/'verification.json').write_text(json.dumps({'stage':'material preview using native crown vertices and interpolated extension','original_vertices':231,'other_mesh_positions_changed':False,'materials_changed':['Hair_Crown','Hair_Back'],'back_hair_below_y600_unchanged':True,'preview_head_angles':[-30,0,30],'poses':[p[0] for p in poses],'cmo_updated':False,'unity_updated':False},indent=2)+'\n',encoding='utf-8')
print('CROWN_COMPLETION_PREVIEWS_READY')
