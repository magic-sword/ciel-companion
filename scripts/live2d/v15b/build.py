"""Assemble v15b: 54 preserved layer identities plus one Fur_Back layer.

Writes only v15b directories. Generated source pixels are placed, masked and
fitted here; the head layers are copied without decoding/re-encoding.
"""
import hashlib,json,shutil,warnings
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from scipy import ndimage as ndi

ROOT=Path(__file__).resolve().parents[3]
GEN=ROOT/'assets/ciel/generated/v15b'
LAY=ROOT/'assets/ciel/layers/v15b'
OLD=ROOT/'assets/ciel/layers/v15'
SIZE=(2172,2896)
FONT=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',23)
CHANGED=['Body','Neck','Outer_R','Outer_L','Choker_Back','Choker_Inside','Choker_Front','Choker_Buckle','Choker_Pendant']
BODY_LAYERS=['Hair_Back','Fur_Back','Body','Neck','Neck_Shadow_Chin','Outer_R','Outer_L','Choker_Back','Choker_Inside','Choker_Front','Choker_Buckle','Choker_Pendant']

def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def empty():return Image.new('RGBA',SIZE)
def old(n):return Image.open(OLD/(n+'.png')).convert('RGBA')
def save(n,im):im.save(LAY/(n+'.png'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clean(im):
    a=np.array(im);lab,n=ndi.label(a[:,:,3]>32);sizes=np.bincount(lab.ravel());sizes[0]=0
    keep=ndi.binary_dilation(lab==np.argmax(sizes),iterations=2)
    a[:,:,3][~keep]=0;a[a[:,:,3]==0,:3]=0
    return Image.fromarray(a)

def masked(im,mask):
    a=np.array(im);a[:,:,3]=np.uint8(a[:,:,3].astype(float)*np.asarray(mask)/255)
    return Image.fromarray(a)

def polygon(size,pts,rounded=None):
    s=3;m=Image.new('L',(size[0]*s,size[1]*s));d=ImageDraw.Draw(m)
    if rounded:
        box,r=rounded;d.rounded_rectangle(tuple(v*s for v in box),radius=r*s,fill=255)
    else:d.polygon([(round(x*s),round(y*s)) for x,y in pts],fill=255)
    return m.resize(size,Image.Resampling.LANCZOS)

def map_image(im,size,fn,step=8):
    mesh=[]
    for y in range(0,size[1],step):
        y1=min(size[1],y+step)
        quad=sum((fn(x,yy) for x,yy in [(0,y),(0,y1),(size[0],y1),(size[0],y)]),())
        mesh.append(((0,y,size[0],y1),quad))
    return im.transform(size,Image.Transform.MESH,mesh,Image.Resampling.BICUBIC)

def place_choker(im,pendant=False):
    sx=.34 if pendant else .30
    fitted=im.resize((round(im.width*sx),round(im.height*.34)),Image.Resampling.LANCZOS)
    out=empty();out.alpha_composite(fitted,(round(1117-745*sx),1322));return out

def choker():
    src=clean(Image.open(GEN/'parts/choker-01.png').convert('RGBA'));w,h=src.size
    xs=[0,126,180,240,400,600,745,900,1100,1250,1368,w]
    top=[0,164,207,235,275,299,304,299,274,235,164,0]
    bottom=[0,468,514,551,600,635,648,637,604,550,470,0]
    # The same ring painting supplies both arcs. 60 source-pixel overlap is hidden.
    backpoly=[(0,0),(w,0)]+[(x,y+60) for x,y in reversed(list(zip(xs,top)))]
    # Interior side wall is dark behind the neck, rather than a white see-through wedge.
    support=Image.new('RGBA',src.size)
    ImageDraw.Draw(support).ellipse((178,140,1320,378),fill=(27,34,47,255))
    support.alpha_composite(src)
    back=masked(support,polygon(src.size,backpoly))
    frontmask=polygon(src.size,list(zip(xs,top))+list(reversed(list(zip(xs,bottom)))))
    backing=Image.new('RGBA',src.size,(27,34,47,255))
    backingmask=masked(src,frontmask).getchannel('A')
    backing=masked(backing,backingmask);backing.alpha_composite(back);back=backing
    backpixels=np.array(back)
    backpixels[345:650,620:880,:3]=[27,34,47]
    back=Image.fromarray(backpixels)
    front=np.array(src)
    # Reconstruct the band behind the separate buckle from adjacent painted panels.
    for y in range(345,650):
        for x in range(620,880):
            t=(x-620)/260
            front[y,x,:3]=np.uint8((1-t)*front[y,608,:3].astype(float)+t*front[y,892,:3].astype(float))
            front[y,x,3]=255
    front=masked(Image.fromarray(front),frontmask)
    buckle=masked(src,polygon(src.size,[],rounded=((623,349,874,644),45)))
    pm=Image.new('L',src.size);pd=ImageDraw.Draw(pm)
    pd.polygon([(715,580),(778,580),(778,632),(789,632),(785,670),(774,710),(775,734),(762,738),(762,804),(727,804),(727,738),(714,734),(716,700),(710,675),(715,632)],fill=255)
    pd.ellipse((634,794,855,1012),fill=255)
    extended=np.array(src)
    for y in range(580,645):
        extended[y,715:779]=extended[656,715:779]
    pendant=masked(Image.fromarray(extended),pm)
    # Fabric belongs to Choker_Inside, independent of the moving pendant.
    fabricmask=polygon(src.size,[(490,580),(1000,580),(977,656),(927,716),(866,776),(805,829),(745,857),(685,829),(622,776),(563,714),(515,656)])
    original=np.array(src);fabric=original.copy()
    for y in range(580,858):
        # Adjacent fabric colors provide hidden fill under the connector and pendant.
        sampley=max(660,min(y,773))
        color=(original[sampley,673,:3].astype(float)+original[sampley,816,:3].astype(float))/2
        if y>=790:color=np.array([48,55,69])
        for x in range(490,1001):
            cyan=int(fabric[y,x,1])-int(fabric[y,x,0])>35 and int(fabric[y,x,2])-int(fabric[y,x,0])>35
            if y<650 or pm.getpixel((x,y))>0 or fabric[y,x,3]<200 or cyan:
                fabric[y,x,:3]=np.uint8(color);fabric[y,x,3]=255
    fabric=masked(Image.fromarray(fabric),fabricmask)
    for n,im in [('Choker_Back',back),('Choker_Front',front),('Choker_Buckle',buckle),('Choker_Inside',fabric),('Choker_Pendant',pendant)]:
        save(n,place_choker(im,n=='Choker_Pendant'))

def body():
    src=clean(Image.open(GEN/'parts/body-02.png').convert('RGBA'))
    ys=[0,425,578,780,1020,1360,1507]
    yt=[1256,1724,1892,2200,2450,2790,2937]
    def mapping(x,y):
        sy=float(np.interp(y,yt,ys,left=-1000,right=2000))
        sx=1.10*float(np.interp(sy,[0,400,600,780,960,1020,1150,1300,1507],[1,1,1,1.05,1.26,1.26,1.12,1,1]))
        return 526+(x-1117)/sx,sy
    im=map_image(src,SIZE,mapping)
    a=np.array(im);a[:1440,:,3]=0
    excess=np.maximum(a[:,:,0].astype(float)-a[:,:,2].astype(float),0)
    a[:,:,0]=np.uint8(np.clip(a[:,:,0]-excess*.8,0,255))
    a[:,:,2]=np.uint8(np.clip(a[:,:,2]+excess*.25,0,255))
    save('Body',Image.fromarray(a))
    for n,sign in [('Outer_R',-1),('Outer_L',1)]:
        def outermap(x,y):
            dx=sign*float(np.interp(y,[0,1950,2100,2240,2450,2670,2896],[0,0,0,20,85,45,0]))
            dx+=float(np.interp(y,[0,1950,2450,2670,2896],[0,0,31,31,0]))
            return x-dx,y
        save(n,map_image(old(n),SIZE,outermap))

def hidden_overlap():
    # Extend only pixels hidden by opaque jacket; use a continuous enlarged paint
    # donor, rather than flat-color rectangular strips around the waist/skirt.
    bodyim=Image.open(LAY/'Body.png').convert('RGBA')
    donor=bodyim.transform(SIZE,Image.Transform.AFFINE,(1/1.14,0,1117-1117/1.14,0,1,0),Image.Resampling.BICUBIC)
    a=np.array(bodyim);b=np.array(donor)
    coat=np.maximum(np.array(Image.open(LAY/'Outer_R.png'))[:,:,3],np.array(Image.open(LAY/'Outer_L.png'))[:,:,3])>=250
    mask=coat&(b[:,:,3]>200);mask[:2480]=False
    a[mask]=b[mask];save('Body',Image.fromarray(a))
    Image.fromarray(np.uint8(mask)*255).save(GEN/'proofs/undercoat-padding-mask.png')
    # Add a hidden margin where the unchanged face covers the neck's upper edge.
    roi=(780,1150,1440,1490);neck=old('Neck');n=np.array(neck.crop(roi))
    face=np.array(old('Face_Skin').crop(roi))[:,:,3]>=250
    distance,indices=ndi.distance_transform_edt(n[:,:,3]<=200,return_indices=True)
    fill=(distance>0)&(distance<=24)&face
    sampled=n[indices[0],indices[1]].copy();n[fill]=sampled[fill];n[fill,3]=255
    neck.paste(Image.fromarray(n),roi[:2]);save('Neck',neck)
    Image.fromarray(np.uint8(fill)*255).save(GEN/'proofs/neck-hidden-padding-mask.png')

def fur():
    src=clean(Image.open(GEN/'parts/fur-back-01.png').convert('RGBA'))
    src=src.crop(src.getbbox());scale=1330/src.width
    src=src.resize((1330,round(src.height*scale)),Image.Resampling.LANCZOS)
    im=empty();im.alpha_composite(src,(452,1370));save('Fur_Back',im)

def flatten(im,bg='#424966'):
    out=Image.new('RGBA',im.size,bg);out.alpha_composite(im);return out.convert('RGB')

def composite(state,only=None,shifts=None):
    out=empty();shifts=shifts or {}
    for r in state['layers']:
        n=r['name']
        if not r['visible'] or (only is not None and n not in only):continue
        im=Image.open(ROOT/r['path']).convert('RGBA')
        if n in shifts:
            off=empty();off.alpha_composite(im,shifts[n]);im=off
        out.alpha_composite(im)
    return out

def panel(items,path,width=650,cols=3,crop=None,bg='#424966'):
    first=items[0][1].crop(crop) if crop else items[0][1]
    height=round(first.height*width/first.width)
    out=Image.new('RGB',(cols*width,((len(items)+cols-1)//cols)*(height+44)),'#e8ebf1');d=ImageDraw.Draw(out)
    for i,(label,im) in enumerate(items):
        x=(i%cols)*width;y=(i//cols)*(height+44);d.text((x+12,y+10),label,font=FONT,fill='#202738')
        if crop:im=im.crop(crop)
        out.paste(flatten(im,bg).resize((width,height),Image.Resampling.LANCZOS),(x,y+44))
    out.save(path)

def main():
    state=read(OLD/'layer-state.json')
    for r in state['layers']:
        shutil.copy2(OLD/(r['name']+'.png'),LAY/(r['name']+'.png'))
        r['path']='assets/ciel/layers/v15b/'+r['name']+'.png'
    state['layers'].insert(1,{'name':'Fur_Back','path':'assets/ciel/layers/v15b/Fur_Back.png','z':5,'visible':True,'description':'首の後ろと左右の肩ファーをつなぐ連続した後ろ襟。','hidden_by':'Body・Neck・左右のOuter・顔・手前髪','motion':'上着・肩の共通親、体の呼吸と傾き','group':None,'source':'generated/v15b/parts/fur-back-01.png','clip':None})
    body();hidden_overlap();fur();choker()
    write(LAY/'layer-state.json',state)
    write(LAY/'psd-manifest.json',{'canvas':list(SIZE),'out':'assets/ciel/psd/ciel-v15b','layers':[{k:r[k] for k in ('name','path')} for r in state['layers']]})
    im=composite(state);im.save(GEN/'proofs/v15b-composite.png')
    original=Image.open(ROOT/'assets/ciel/master/ciel-upper-body-2x.png').convert('RGBA')
    prev=Image.open(ROOT/'assets/ciel/generated/v15/proofs/v15-composite.png').convert('RGBA')
    items=[('Original reference',original),('v15',prev),('v15b',im)]
    panel(items,GEN/'proofs/comparison-full.png',width=600)
    panel(items,GEN/'proofs/comparison-neck-shoulders.png',width=760,crop=(370,1260,1830,2060))
    panel(items,GEN/'proofs/comparison-abdomen.png',width=650,crop=(590,2100,1640,2896))
    panel([('Body',Image.open(LAY/'Body.png').convert('RGBA')),('Fur_Back',Image.open(LAY/'Fur_Back.png').convert('RGBA')),('Body + fur + outer',composite(state,only=BODY_LAYERS))],GEN/'proofs/underpainting.png',width=600,crop=(250,1180,1920,2896))
    print('Built 55 v15b layers and first comparisons.')

if __name__=='__main__':main()
