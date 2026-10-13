"""Separate v30 with masks, preserve pixels, and preview a parts replacement."""
from pathlib import Path
import hashlib,json,io,zipfile
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'assets/ciel/generated/v31'
SIZE=(2172,2896);CROP=(550,650,1600,1700)
for p in ('parts','layers','proofs'):(OUT/p).mkdir(parents=True,exist_ok=True)
source=Image.open(ROOT/'assets/ciel/generated/v30/face-details-with-contour.png').convert('RGBA')
a=np.asarray(source);h,w=a.shape[:2];yy,xx=np.indices((h,w))
labels=np.where(xx<490,3,4).astype(np.uint8)
def polygon(points):
    im=Image.new('L',(w,h));ImageDraw.Draw(im).polygon(points,fill=1);return np.asarray(im).astype(bool)
left=polygon([(120,270),(425,270),(425,395),(370,382),(335,375),(285,367),(245,377),(213,394),(190,415),(120,405)])
right=polygon([(570,270),(860,270),(860,405),(790,395),(752,374),(702,365),(660,366),(610,381),(570,397)])
# Include opaque dark lash edge pixels beside the manual boundary.
dark=(a[:,:,:3].max(axis=2)<180)&(a[:,:,3]>0)
left|=dark&(xx<425)&(yy<416);right|=dark&(xx>570)&(yy<410)
labels[left]=1;labels[right]=2
contour=(yy>=410)&dark
labels[contour]=7
labels[(xx>=412)&(xx<580)&(yy>=507)&(yy<605)]=5
labels[(xx>=476)&(xx<509)&(yy>=445)&(yy<477)]=6
names={1:'Eye_R_Happy',2:'Eye_L_Happy',3:'Cheek_R_Blush_Happy',4:'Cheek_L_Blush_Happy',
       5:'Mouth_Happy',6:'Nose',7:'Face_Contour'}
parts={};reconstructed=Image.new('RGBA',source.size)
for k,name in names.items():
    b=a.copy();b[labels!=k]=0;im=Image.fromarray(b);parts[name]=im
    im.save(OUT/'parts'/(name+'.png'));reconstructed.alpha_composite(im)
visible=a[:,:,3]>0
assert np.array_equal(np.asarray(reconstructed)[visible],a[visible])
assert np.array_equal(np.asarray(reconstructed)[:,:,3],a[:,:,3])
# Editable layered document for image editors supporting OpenRaster.
doc=ET.Element('image',{'w':str(w),'h':str(h),'name':'Ciel happy face separated v31','version':'0.0.3'})
stack=ET.SubElement(doc,'stack')
with zipfile.ZipFile(OUT/'face-parts.ora','w') as archive:
    archive.writestr('mimetype','image/openraster',compress_type=zipfile.ZIP_STORED)
    for name in reversed(list(parts)):
        path=f'data/{name}.png'
        ET.SubElement(stack,'layer',{'name':name,'src':path,'x':'0','y':'0','opacity':'1.0',
                                    'visibility':'visible','composite-op':'svg:src-over'})
        archive.write(OUT/'parts'/(name+'.png'),path)
    archive.writestr('stack.xml',ET.tostring(doc,encoding='utf-8',xml_declaration=True))
    buff=io.BytesIO();reconstructed.save(buff,format='PNG');archive.writestr('mergedimage.png',buff.getvalue())

# A single shared transform uses cheek contour width, not separate eye scaling.
# Measured original contour endpoints at source y520 and current Face_Skin y1200.
ref_left,ref_right=(192,520),(788,520)
target_left,target_right=(807,1200),(1398,1200)
scale=(target_right[0]-target_left[0])/(ref_right[0]-ref_left[0])
ox=target_left[0]-scale*ref_left[0];oy=target_left[1]-scale*ref_left[1]
layers={}
for name,im in parts.items():
    layer=im.transform(SIZE,Image.Transform.AFFINE,(1/scale,0,-ox/scale,0,1/scale,-oy/scale),Image.Resampling.BICUBIC)
    layers[name]=layer;layer.save(OUT/'layers'/(name+'.png'))
manifest=json.loads((ROOT/'assets/ciel/current/layers.json').read_text(encoding='utf-8'))
def hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'assets/ciel/current').rglob('*')) if p.is_file()}
before=hashes()
assembled=Image.new('RGBA',SIZE)
for entry in manifest['layers']:
    name=entry['name']
    visible=entry.get('visible',True) and not name.startswith(('Eye_L_','Eye_R_','Mouth_')) and name not in ('Nose','Cheek_Blush')
    if visible:assembled.alpha_composite(Image.open(ROOT/entry['path']).convert('RGBA'))
    if name=='Face_Shadow_Hair':
        # Use extracted blush at its own alpha; do not reuse the old .45 setting.
        assembled.alpha_composite(layers['Cheek_R_Blush_Happy']);assembled.alpha_composite(layers['Cheek_L_Blush_Happy'])
    for slot,part in [('Eye_R_Closed','Eye_R_Happy'),('Eye_L_Closed','Eye_L_Happy'),('Mouth_Large','Mouth_Happy'),('Nose','Nose')]:
        if name==slot:assembled.alpha_composite(layers[part])
assembled.save(OUT/'proofs/happy-assembled.png')
# The extracted contour is an alignment guide, not a second rendered face outline.
diagnostic=assembled.copy();diagnostic.alpha_composite(layers['Face_Contour'])
diagnostic.save(OUT/'proofs/contour-alignment-diagnostic.png')
reference=Image.open(ROOT/'assets/ciel/generated/v30/inputs/happy-reference-face.png').convert('RGBA')
aligned_reference=reference.transform(SIZE,Image.Transform.AFFINE,(1/scale,0,-ox/scale,0,1/scale,-oy/scale),Image.Resampling.BICUBIC)
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',21)
def flat(im,color=(64,72,104)):
    bg=Image.new('RGBA',im.size,color+(255,));bg.alpha_composite(im.convert('RGBA'));return bg.convert('RGB')
def board(panels,path,box=CROP):
    out=Image.new('RGB',(525*len(panels),565),(64,72,104));draw=ImageDraw.Draw(out)
    for i,(label,im) in enumerate(panels):
        out.paste(flat(im.crop(box)).resize((525,525),Image.Resampling.LANCZOS),(i*525,40));draw.text((i*525+8,8),label,font=font,fill='white')
    out.save(path)
board([('見本（頬の輪郭幅を基準）',aligned_reference),('パーツを分離・差し替え合成',assembled)],OUT/'proofs/reference-comparison.png')
board([('前の案（v29）',Image.open(ROOT/'assets/ciel/generated/v29/size-and-contact/happy-assembled.png')),('今回の差し替え合成',assembled)],OUT/'proofs/previous-comparison.png')
board([('既存の顔土台で合成',assembled),('抽出した輪郭を重ねた診断図',diagnostic)],OUT/'proofs/contour-comparison.png')
sheet=Image.new('RGB',(1200,720),(64,72,104));draw=ImageDraw.Draw(sheet)
for i,(name,im) in enumerate(parts.items()):
    x=(i%4)*300;y=(i//4)*360
    alpha=np.asarray(im.getchannel('A'));ay,ax=np.nonzero(alpha>16)
    bbox=(int(ax.min()),int(ay.min()),int(ax.max())+1,int(ay.max())+1)
    patch=flat(im.crop(bbox));patch.thumbnail((280,300),Image.Resampling.LANCZOS)
    sheet.paste(patch,(x+(300-patch.width)//2,y+45+(300-patch.height)//2));draw.text((x+8,y+8),name,font=font,fill='white')
sheet.save(OUT/'proofs/parts-sheet.png')
assert before==hashes()
(OUT/'placement.json').write_text(json.dumps({'source':'assets/ciel/generated/v30/face-details-with-contour.png',
    'method':'Shared scale/translation from cheek outline endpoints; no per-part adjustment',
    'reference_anchors':[ref_left,ref_right],'target_anchors':[target_left,target_right],
    'uniform_scale':scale,'offset':[ox,oy],'contour_used_as_guide_only':True,
    'blush_uses_source_alpha_without_extra_weight':True,
    'parts':{name:{'source_bbox':im.getbbox(),'target_bbox':layers[name].getbbox()} for name,im in parts.items()}},indent=2)+'\n',encoding='utf-8')
(OUT/'verification.json').write_text(json.dumps({'new_generation':False,'part_count':7,'visible_rgba_reconstruction_exact':True,
    'alpha_reconstruction_exact':True,'current_unchanged':True,'rig_imported':False,'all_parts_share_transform':True,
    'contour_rendered_in_final':False,'source_canvas':source.size,'target_canvas':SIZE},indent=2)+'\n',encoding='utf-8')
print('V31_SEPARATION_AND_REPLACEMENT_PROOFS_READY')
