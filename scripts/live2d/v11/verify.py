"""Render v11 proofs, record geometric checks and validate the layer contract."""
from pathlib import Path
import json, hashlib, math, warnings, re
import numpy as np
from PIL import Image, ImageDraw, ImageFont
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from scipy import ndimage as ndi
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'assets/ciel/layers/v11'; SRC=ROOT/'assets/ciel/layers/v10'; GEN=ROOT/'assets/ciel/generated/v11'
PROOF=OUT/'proofs'; PROOF.mkdir(exist_ok=True)
SIZE=(2172,2896)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
states={v:json.loads((ROOT/f'assets/ciel/layers/{v}/layer-state.json').read_text(encoding='utf-8')) for v in ['v10','v11']}
def dump(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def render(v,eyes='open',mouth='closed',exclude=()):
    out=Image.new('RGBA',SIZE)
    for r in states[v]['layers']:
        n=r['name']; visible=r['visible']
        if n.startswith('Mouth_') and r['group']: visible=r['group']=='mouth_'+mouth
        if n.startswith('Eye_'): visible=n.endswith('_Closed') if eyes=='closed' else not n.endswith('_Closed')
        if any(n.startswith(e) for e in exclude): visible=False
        if visible:
            with Image.open(ROOT/r['path']) as im: out.alpha_composite(im.convert('RGBA'))
    return out
def bg(im,color=(231,233,240,255)):
    out=Image.new('RGBA',im.size,color);out.alpha_composite(im.convert('RGBA'));return out.convert('RGB')
def plate(name,items,box,scale,cols=2):
    w=round((box[2]-box[0])*scale);h=round((box[3]-box[1])*scale)
    out=Image.new('RGB',(w*cols,(h+56)*math.ceil(len(items)/cols)),(246,247,251)); d=ImageDraw.Draw(out)
    for i,(label,im) in enumerate(items):
        x=i%cols*w;y=i//cols*(h+56)
        d.text((x+10,y+6),label,font=font,fill=(28,36,52))
        d.text((x+10,y+32),f'{scale:g}x / crop {box}',font=small,fill=(65,74,91))
        out.paste(bg(im.crop(box)).resize((w,h),Image.Resampling.LANCZOS),(x,y+56))
    out.save(PROOF/name)
    return out
def threshold_bounds(im):
    a=np.array(im)[:,:,3]>128
    yy,xx=np.where(a)
    return [int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)]
def joined(v,prefix):
    im=Image.new('RGBA',SIZE)
    for r in states[v]['layers']:
        if r['name'].startswith(prefix): im.alpha_composite(Image.open(ROOT/r['path']).convert('RGBA'))
    return im

def main():
    neutral={v:render(v) for v in states}
    closed={v:render(v,eyes='closed') for v in states}
    sm={v:render(v,mouth='small') for v in states};lg={v:render(v,mouth='large') for v in states}
    master=Image.open(ROOT/'assets/ciel/master/ciel-upper-body-2x.png').convert('RGBA')
    for n,im in [('compose',neutral['v11']),('blink',closed['v11']),('talk-small',sm['v11']),('talk-large',lg['v11'])]: im.save(PROOF/(n+'.png'))
    plate('compare-face.png',[('Reference',master),('v10',neutral['v10']),('v11',neutral['v11'])],(450,300,1730,1490),.55,3)
    plate('compare-closed-face.png',[('v10 closed eyes',closed['v10']),('v11 closed eyes',closed['v11'])],(600,650,1590,1460),.8)
    plate('compare-upper.png',[('Reference',master),('v10',neutral['v10']),('v11',neutral['v11'])],(0,0,*SIZE),.27,3)
    plate('expressions.png',[('v11 neutral',neutral['v11']),('v11 blink',closed['v11']),('v11 small open',sm['v11']),('v11 large open',lg['v11'])],(690,860,1520,1420),.85,2)
    plate('expressions-upper.png',[('Neutral',neutral['v11']),('Blink',closed['v11']),('Small mouth',sm['v11']),('Large mouth',lg['v11'])],(0,0,*SIZE),.23,4)
    refs={}
    for m in ['closed','small','large']:
        path=ROOT/'assets/ciel/reference/mouth'/('mouth-closed.png' if m=='closed' else 'mouth-'+m+'-open.png')
        im=Image.new('RGBA',SIZE);im.paste(Image.open(path).convert('RGBA'),(318,236));refs[m]=im
    mouthitems=[]
    for label,collection in [('Reference',refs),('v10',{'closed':neutral['v10'],'small':sm['v10'],'large':lg['v10']}),('v11',{'closed':neutral['v11'],'small':sm['v11'],'large':lg['v11']})]:
        for m in ['closed','small','large']: mouthitems.append((label+' / '+m,collection[m]))
    plate('mouth-three-stages-reference.png',mouthitems,(980,1160,1235,1350),2,3)
    plate('mouth-faces-reference.png',mouthitems,(720,900,1510,1410),.62,3)
    # All eyes stay at the SAME coordinates. Guides align inner/outer corners;
    # horizontal guides show the open aperture's middle and lower edge.
    eyeitems=[]; metrics={}
    for v,mode,im in [('v10','open',neutral['v10']),('v10','closed',closed['v10']),('v11','open',neutral['v11']),('v11','closed',closed['v11'])]:
        marked=im.copy(); d=ImageDraw.Draw(marked)
        for left,right,mid,bottom in [(748,1011,1040,1120),(1199,1456,1030,1110)]:
            for x in [left,right]: d.line((x,920,x,1140),fill=(22,150,163,210),width=2)
            d.line((left,mid,right,mid),fill=(242,161,38,180),width=1)
            d.line((left,bottom,right,bottom),fill=(95,152,182,180),width=1)
        eyeitems.append((v+' '+mode+' / same corner guides',marked))
    plate('eyes-width-height.png',eyeitems,(700,920,1500,1140),1,2)
    for s in ['R','L']:
        metrics[s]={}
        for v in states:
            for p in ['LashUpper','Closed']:
                im=Image.open(ROOT/f'assets/ciel/layers/{v}/Eye_{s}_{p}.png')
                b=threshold_bounds(im); metrics[s][v+'_'+p]=dict(alpha_gt_128_bounds=b,width=b[2]-b[0],height=b[3]-b[1])
    # Visual jaw overlay uses master pixels as fixed reference; coloured edges
    # are exported base silhouettes, no per-image recentering.
    overlay=master.copy(); arr=np.array(overlay)
    face_rows={}
    for v,color in [('v10',(224,64,153,255)),('v11',(10,151,162,255))]:
        a=np.array(Image.open(ROOT/f'assets/ciel/layers/{v}/Face_Skin.png'))[:,:,3]>128
        edge=a&~ndi.binary_erosion(a,iterations=2);edge[:1200]=False;edge[1400:]=False
        arr[edge]=color
        face_rows[v]={}
        for y in [900,1000,1100,1200,1250,1300,1350,1380,1385]:
            xs=np.where(a[y])[0];face_rows[v][y]=dict(left=int(xs[0]),right=int(xs[-1]),center=float((xs[0]+xs[-1])/2))
        yy,xx=np.where(a); bottom=yy.max();lastx=np.where(a[bottom])[0]
        face_rows[v]['chin']=dict(x=float((lastx[0]+lastx[-1])/2),y=int(bottom))
    overlay=Image.fromarray(arr)
    d=ImageDraw.Draw(overlay);d.line((1113,1190,1113,1420),fill=(234,160,29,255),width=1)
    plate('jaw-reference-overlay.png',[('Master + v10 magenta / v11 teal',overlay)],(770,1180,1420,1430),1.7,1)
    plate('face-base-neck.png',[(v+' / hair and cast shadow hidden',render(v,exclude=('Hair_','Ear_','Face_Shadow_Hair'))) for v in states],(650,800,1540,1510),.75)
    plate('cheeks-hair-neck.png',[('v10',neutral['v10']),('v11',neutral['v11'])],(740,1130,1470,1570),1.0)
    # Generated mouth components, cavity alone and reassembly at original scale.
    parts=[]; mouth_metrics={}
    for mode in ['Small','Large']:
        for part in ['Inside','Tongue','Teeth','Line_Upper','Line_Lower']:
            im=Image.open(OUT/f'Mouth_{mode}_{part}.png').convert('RGBA');parts.append((mode+' '+part,im))
        for v in states:
            im=joined(v,'Mouth_'+mode+'_');b=threshold_bounds(im)
            mouth_metrics[v+'_'+mode]=dict(bounds=b,width=b[2]-b[0],height=b[3]-b[1])
    plate('mouth-parts.png',parts,(990,1170,1220,1340),2,5)
    # Integrity checks; old inputs were snapshotted before any edits.
    rows=states['v11']['layers']; manifest=json.loads((OUT/'psd-manifest.json').read_text(encoding='utf-8'))
    assert [r['name'] for r in rows]==[r['name'] for r in states['v10']['layers']]==[r['name'] for r in manifest['layers']]
    assert manifest['out']=='assets/ciel/psd/ciel-v11' and len(rows)==62
    assert sum(r['visible'] for r in rows)==50
    tests=[]
    for r in rows:
        p=ROOT/r['path'];im=Image.open(p);a=np.array(im)
        assert im.size==SIZE and im.mode=='RGBA' and im.getbbox() and (a[:,:,3]==0).any()
        assert re.fullmatch('[A-Za-z0-9_]+',r['name'])
        tests.append(dict(name=r['name'],bounds=im.getbbox(),sha256=sha(p),identical_to_v10=sha(p)==sha(SRC/p.name)))
    before=json.loads((GEN/'input-sha256.json').read_text(encoding='utf-8'))
    changed_inputs=[p for p,h in before.items() if sha(ROOT/p)!=h];assert not changed_inputs
    # All states have opaque face interiors at former eye/mouth locations.
    states_check={}
    for n,im in [('neutral',neutral['v11']),('blink',closed['v11']),('small',sm['v11']),('large',lg['v11'])]:
        states_check[n]=int((np.array(im.crop((800,950,1400,1350)))[:,:,3]<250).sum())
    assert not any(states_check.values())
    result=dict(layers=62,visible=50,hidden=12,unchanged_inputs=True,input_files_checked=len(before),
                identical_layer_copies=sum(t['identical_to_v10'] for t in tests),eye_metrics=metrics,mouth_metrics=mouth_metrics,
                face_rows=face_rows,expression_interior_transparent_pixels=states_check,files=tests)
    dump(OUT/'validation.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['files']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
