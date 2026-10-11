"""v15 material assembly. All outputs are confined to the three v15 folders."""
import copy
import hashlib
import json
import shutil
import warnings
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageChops
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / 'assets/ciel/generated/v15'
LAY = ROOT / 'assets/ciel/layers/v15'
OLD = ROOT / 'assets/ciel/layers/v14c'
SIZE = (2172, 2896)
ALLOWED = ['Hair_Back','Body','Neck','Neck_Shadow_Chin','Outer_L','Outer_R','Choker_Back','Choker_Inside','Choker_Front','Choker_Buckle','Choker_Pendant']
FONT = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 23)

def read(p): return json.loads(p.read_text(encoding='utf8'))
def write(p, x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def empty(): return Image.new('RGBA', SIZE)
def old(n): return Image.open(OLD/(n+'.png')).convert('RGBA')
def save(n, im): im.save(LAY/(n+'.png'))

def clean(im, count=1):
    """Remove disconnected generation debris; retain antialiasing at main boundaries."""
    a=np.array(im); labs,num=ndi.label(a[:,:,3]>32)
    sizes=np.bincount(labs.ravel());sizes[0]=0
    ids=np.argsort(sizes)[-count:]
    keep=ndi.binary_dilation(np.isin(labs,ids),iterations=2)
    a[:,:,3][~keep]=0
    a[a[:,:,3]==0,:3]=0
    return Image.fromarray(a)

def place(im,s,x,y):
    im=im.resize((round(im.width*s),round(im.height*s)),Image.Resampling.LANCZOS)
    out=empty();out.alpha_composite(im,(round(x),round(y)));return out

def translate(im,dx=0,dy=0):
    out=empty();out.alpha_composite(im,(dx,dy));return out

def fit_fur(im):
    # Second generation opens the shoulders too far; recover moderate original volume.
    # Inverse mesh keeps sleeves below source y610 fixed; no alpha cross-fade.
    mesh=[]; w,h=im.size;mid=w//2
    def source(x,y,side):
        sy=float(np.interp(y,[0,90,225,400,610,h],[0,130,280,430,610,h]))
        s=1+.16*(1-np.clip((sy-130)/480,0,1))
        pivot=160 if side==0 else w-160
        return pivot+(x-pivot)/s,sy
    for side,(x0,x1) in enumerate([(0,mid),(mid,w)]):
        for y0 in range(0,h,16):
            y1=min(y0+16,h)
            quad=sum((source(x,y,side) for x,y in [(x0,y0),(x0,y1),(x1,y1),(x1,y0)]),())
            mesh.append(((x0,y0,x1,y1),quad))
    return im.transform(im.size,Image.Transform.MESH,mesh,Image.Resampling.BICUBIC)

def vertical_fit(im,ys,yt):
    mesh=[]
    for y0 in range(0,SIZE[1],8):
        y1=min(y0+8,SIZE[1]);s0=float(np.interp(y0,yt,ys));s1=float(np.interp(y1,yt,ys))
        mesh.append(((0,y0,SIZE[0],y1),(0,s0,0,s1,SIZE[0],s1,SIZE[0],s0)))
    return im.transform(SIZE,Image.Transform.MESH,mesh,Image.Resampling.BICUBIC)

def flatten(im,bg='#424966'):
    out=Image.new('RGBA',im.size,bg);out.alpha_composite(im);return out.convert('RGB')

def composite(state, shifts=None, only=None):
    out=empty(); shifts=shifts or {}
    for r in state['layers']:
        n=r['name']
        if not r['visible'] or (only is not None and n not in only):continue
        im=Image.open(ROOT/r['path']).convert('RGBA')
        if n in shifts:im=translate(im,*shifts[n])
        out.alpha_composite(im)
    return out

def panel(items,path,cols=3,width=600,crop=None,bg='#424966'):
    first=items[0][1].crop(crop) if crop else items[0][1]
    height=round(first.height*width/first.width)
    out=Image.new('RGB',(cols*width,((len(items)+cols-1)//cols)*(height+44)),'#e8ebf1');d=ImageDraw.Draw(out)
    for i,(label,im) in enumerate(items):
        x=(i%cols)*width;y=(i//cols)*(height+44)
        d.text((x+12,y+10),label,font=FONT,fill='#202738')
        if crop: im=im.crop(crop)
        im=flatten(im,bg).resize((width,height),Image.Resampling.LANCZOS)
        out.paste(im,(x,y+44))
    out.save(path)

def main():
    LAY.mkdir(exist_ok=True);(GEN/'proofs').mkdir(exist_ok=True)
    state=read(OLD/'layer-state.json')
    for r in state['layers']:
        shutil.copy2(OLD/(r['name']+'.png'),LAY/(r['name']+'.png'))
        r['path']='assets/ciel/layers/v15/'+r['name']+'.png'
    body=clean(Image.open(GEN/'parts/body-01.png').convert('RGBA'))
    body=place(body,1.10,553,1286)
    a=np.array(body);a[:1420,:,3]=0;body=Image.fromarray(a)
    save('Body',body)
    outer=clean(Image.open(GEN/'parts/outer-02.png').convert('RGBA'),2)
    outer=fit_fur(outer)
    outer=place(outer,2172/outer.width,0,1280)
    for name,left in [('Outer_R',True),('Outer_L',False)]:
        a=np.array(outer)
        if left:a[:,1086:,3]=0
        else:a[:,:1086,3]=0
        save(name,Image.fromarray(a))
    # Extend waist/skirt beneath the jacket; sampled interior color avoids extruding
    # the original silhouette ink. Every new/retouched pixel is hidden at neutral.
    a=np.array(body);coat=np.array(outer)[:,:,3]>=250
    padding=np.zeros((SIZE[1],SIZE[0]),np.uint8)
    for y in range(2300,SIZE[1]):
        xs=np.flatnonzero(a[y,:,3]>200)
        if not len(xs):continue
        lo,hi=int(xs[0]),int(xs[-1])
        for start,end,sample in [(max(0,lo-40),lo+9,lo+18),(hi-8,min(SIZE[0],hi+41),hi-18)]:
            mask=coat[y,start:end]
            segment=a[y,start:end]
            color=a[y,sample,:3].copy()
            segment[mask,:3]=color;segment[mask,3]=255
            padding[y,start:end][mask]=255
    body=Image.fromarray(a);save('Body',body)
    Image.fromarray(padding).save(GEN/'proofs/undercoat-padding-mask.png')
    # Upper head remains exactly stationary; narrow only the long lower back hair.
    hair=old('Hair_Back');arr=np.array(hair)
    for y in range(1400,SIZE[1]):
        t=min(1,(y-1400)/1000);t=t*t*(3-2*t);s=1-.14*t
        row=hair.crop((0,y,SIZE[0],y+1)).resize((round(SIZE[0]*s),1),Image.Resampling.LANCZOS)
        arr[y,:,:]=0;start=round((SIZE[0]-row.width)/2);arr[y,start:start+row.width]=np.array(row)[0]
    save('Hair_Back',Image.fromarray(arr))
    for n in ['Neck','Neck_Shadow_Chin']:
        a=np.array(old(n));a[1470:,:,3]=0;save(n,Image.fromarray(a))
    for n in ['Choker_Back','Choker_Inside']:
        save(n,translate(old(n),0,48))
    band=clean(Image.open(GEN/'parts/choker-front-01.png').convert('RGBA'))
    band=band.crop(band.getbbox()).resize((372,168),Image.Resampling.LANCZOS)
    front=empty();front.alpha_composite(band,(931,1377));save('Choker_Front',front)
    save('Choker_Buckle',vertical_fit(old('Choker_Buckle'),[0,1428,1520,2896],[0,1443,1546,2896]))
    pendant=clean(old('Choker_Pendant'))
    # Remove the old buckle's silver fragment at the hidden top of its triangular tab.
    a=np.array(pendant)
    for y in range(1490,1501):
        for x in range(1043,1190):
            if a[y,x,3] and min(a[y,x,:3])>110:
                a[y,x,:3]=a[1506,x,:3]
    pendant=Image.fromarray(a)
    pendant=vertical_fit(pendant,[0,1490,1535,1660,2896],[0,1520,1592,1723,2896])
    save('Choker_Pendant',pendant)
    write(LAY/'layer-state.json',state)
    manifest=read(OLD/'psd-manifest.json');manifest['out']='assets/ciel/psd/ciel-v15';manifest['layers']=[{k:r[k] for k in ('name','path')} for r in state['layers']]
    write(LAY/'psd-manifest.json',manifest)
    im=composite(state);im.save(GEN/'proofs/v15-composite.png')
    master=Image.open(ROOT/'assets/ciel/master/ciel-upper-body-2x.png').convert('RGBA')
    prev=Image.open(GEN/'inputs/v14c-composite.png').convert('RGBA')
    items=[('Approved original',master),('v14c material composite',prev),('v15',im)]
    panel(items,GEN/'proofs/comparison-full.png',width=600)
    panel(items,GEN/'proofs/comparison-shoulders.png',width=800,crop=(320,1270,1860,2200))
    print('Built 54 layers and draft comparisons.')

if __name__=='__main__':main()
