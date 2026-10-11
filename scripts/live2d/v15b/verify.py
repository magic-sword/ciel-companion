"""Verify v15b preservation, layer structure, overlaps and translation coverage."""
import sys
sys.dont_write_bytecode=True
from build import *

DIRECTIONS=[(x,y) for y in (-15,0,15) for x in (-15,0,15) if (x,y)!=(0,0)]

def shifted(a,dx,dy):
    out=np.zeros_like(a);h,w=a.shape
    x0=max(0,dx);x1=min(w,w+dx);y0=max(0,dy);y1=min(h,h+dy)
    out[y0:y1,x0:x1]=a[y0-dy:y1-dy,x0-dx:x1-dx];return out

def main():
    state=read(LAY/'layer-state.json');prior=read(OLD/'layer-state.json');manifest=read(LAY/'psd-manifest.json')
    rows=state['layers'];names=[r['name'] for r in rows]
    assert len(rows)==55 and len(set(names))==55
    assert names[:3]==['Hair_Back','Fur_Back','Body']
    assert [n for n in names if n!='Fur_Back']==[r['name'] for r in prior['layers']]
    assert manifest['out']=='assets/ciel/psd/ciel-v15b'
    assert manifest['layers']==[{k:r[k] for k in ('name','path')} for r in rows]
    priorrows={r['name']:r for r in prior['layers']}
    unchanged={};changed={};cache={};alphas={};head=empty();head_nohair=empty()
    solid=np.zeros((SIZE[1],SIZE[0]),np.int16);struct=solid.copy();structure_names=[]
    for r in rows:
        n=r['name'];p=LAY/(n+'.png');im=Image.open(p).convert('RGBA')
        assert im.size==SIZE and Image.open(p).mode=='RGBA'
        if n!='Fur_Back':
            assert all(r[k]==priorrows[n][k] for k in ['z','visible','group','clip'])
            equal=sha(p)==sha(OLD/(n+'.png'))
            if n not in CHANGED:assert equal,n;unchanged[n]=sha(p)
            else:assert not equal,n;changed[n]=sha(p)
        if not r['visible']:continue
        a=np.array(im.getchannel('A'))>200;solid+=a
        if n not in ['Hair_Back','Neck_Shadow_Chin','Face_Shadow_Hair'] and not n.startswith(('Hair_','Ear_')):
            struct+=a;structure_names.append(n)
        if n in BODY_LAYERS:cache[n]=im;alphas[n]=a
        else:
            head.alpha_composite(im)
            if not n.startswith(('Hair_','Ear_')):head_nohair.alpha_composite(im)
    assert len(unchanged)==45
    hashes=read(GEN/'inputs/source-hashes.json')
    assert all(sha(ROOT/p)==h for p,h in hashes.items()),'Existing input changed'
    def render(shifts=None,only=None,hair=True,with_head=True):
        out=empty();shifts=shifts or {}
        for r in rows:
            n=r['name']
            if n not in cache or (only is not None and n not in only) or (not hair and n=='Hair_Back'):continue
            im=cache[n]
            if n in shifts:
                tmp=empty();tmp.alpha_composite(im,shifts[n]);im=tmp
            out.alpha_composite(im)
        if with_head:out.alpha_composite(head if hair else head_nohair)
        return out
    interior=ndi.distance_transform_edt(solid>0)>32
    sinterior=ndi.distance_transform_edt(struct>0)>32
    region=np.zeros(solid.shape,bool);region[1200:2860,350:1850]=True
    interior &= region;sinterior &= region
    cases=[]
    for label,ns in [(n,[n]) for n in BODY_LAYERS]+[('Body_group',[n for n in BODY_LAYERS if n!='Hair_Back'])]:
        sub=sum((alphas[n].astype(np.int16) for n in ns),np.zeros_like(solid))
        ssub=sum((alphas[n].astype(np.int16) for n in ns if n in structure_names),np.zeros_like(solid))
        for dx,dy in DIRECTIONS:
            gap=interior&((solid-sub+shifted(sub,dx,dy))==0)
            sgap=sinterior&((struct-ssub+shifted(ssub,dx,dy))==0)
            cases.append({'part':label,'dx':dx,'dy':dy,'gap_pixels':int(gap.sum()),'no_hair_gap_pixels':int(sgap.sum())})
            if gap.any() or sgap.any():Image.fromarray(np.uint8(gap|sgap)*255).save(GEN/f'proofs/gap-{label}-{dx}-{dy}.png')
    overlaps={}
    for n in ['Outer_R','Outer_L']:
        counts=[]
        for a in [(0,0)]+DIRECTIONS:
            for b in [(0,0)]+DIRECTIONS:
                counts.append(int((shifted(alphas['Fur_Back'],*a)&shifted(alphas[n],*b)).sum()))
        overlaps[n]={'neutral_overlap_pixels':int((alphas['Fur_Back']&alphas[n]).sum()),'minimum_in_81_relative_cases':min(counts)}
        assert min(counts)>0
    validation={'layer_count':55,'canvas':SIZE,'new_layer':'Fur_Back','existing_order_z_visibility_clip_preserved':True,
      'unchanged_layer_count':45,'protected_face_layer_count':43,'unchanged_sha256':unchanged,'changed_sha256':changed,
      'prior_files_hash_checked':len(hashes),'generation_count':4,'generation_limit':20,'motion_case_count':len(cases),
      'max_gap_pixels':max(c['gap_pixels'] for c in cases),'max_no_hair_gap_pixels':max(c['no_hair_gap_pixels'] for c in cases),
      'motion_cases':cases,'fur_outer_overlap':overlaps,
      'method':'Alpha >200, original interior farther than32px from outline, native +/-15px in8 directions; also without hair, ears and shadow-only support. Not a rig test.'}
    write(LAY/'validation.json',validation)
    print(json.dumps({k:v for k,v in validation.items() if k not in ['motion_cases','unchanged_sha256','changed_sha256']},ensure_ascii=True),flush=True)
    full=render()
    items=[]
    for dy in (-15,0,15):
        for dx in (-15,0,15):
            items.append((f'Body group {dx:+},{dy:+} px',render({n:(dx,dy) for n in BODY_LAYERS if n!='Hair_Back'}).crop((350,1220,1850,2896))))
    panel(items,GEN/'proofs/motion-body-grid.png',width=460);del items
    items=[]
    for name in ['Body','Outer_R','Outer_L']:
        for dx,dy in [(-15,-15),(0,0),(15,15)]:
            items.append((f'{name} {dx:+},{dy:+} / hair off',render({name:(dx,dy)},hair=False).crop((460,1400,1750,2896))))
    panel(items,GEN/'proofs/motion-joints-no-hair.png',width=470,bg='#9d476c');del items
    items=[]
    for name in ['Choker_Back','Choker_Inside','Choker_Pendant']:
        for dy in (-15,0,15):
            items.append((f'{name} Y {dy:+} px',render({name:(0,dy)}).crop((885,1300,1355,1740))))
    panel(items,GEN/'proofs/motion-choker.png',width=470);del items
    # Fur connection with all hair removed, plus a view without the body occluder.
    only=[n for n in BODY_LAYERS if n!='Hair_Back']
    fur_items=[('Fur_Back off',render(only=[n for n in only if n!='Fur_Back'],hair=False,with_head=False)),('Fur_Back on',render(only=only,hair=False,with_head=False)),('Connected fur / body off',render(only=['Fur_Back','Outer_R','Outer_L'],with_head=False))]
    panel(fur_items,GEN/'proofs/fur-connection.png',width=650,crop=(340,1280,1850,2090),bg='#606781')
    fitems=[]
    for dy in (-15,0,15):
        for dx in (-15,0,15):
            fitems.append((f'Fur_Back {dx:+},{dy:+} px',render({'Fur_Back':(dx,dy)},only=only,hair=False,with_head=False).crop((340,1280,1850,2090))))
    panel(fitems,GEN/'proofs/motion-fur-back.png',width=520,bg='#606781');del fitems
    large=[(n+' / 25%',cache[n].crop((0,1100,2172,2896))) for n in ['Hair_Back','Fur_Back','Body','Outer_R','Outer_L']]
    panel(large,GEN/'proofs/exploded-large.png',width=543,cols=3)
    small=[(n+' / 100%',cache[n].crop((820,1160,1420,1760))) for n in BODY_LAYERS if n not in ['Hair_Back','Fur_Back','Body','Outer_R','Outer_L']]
    panel(small,GEN/'proofs/exploded-neck-choker.png',width=600,cols=4)
    out=Image.new('RGB',(1629,768),'#e8ebf1');d=ImageDraw.Draw(out)
    for i,(label,bg) in enumerate([('White','#ffffff'),('Mid gray','#85858d'),('Dark','#171b29')]):
        d.text((i*543+12,10),label,font=FONT,fill='#202738');out.paste(flatten(full,bg).resize((543,724),Image.Resampling.LANCZOS),(i*543,44))
    out.save(GEN/'proofs/edges-light-gray-dark.png')
    print('Verification and all proofs complete.',flush=True)

if __name__=='__main__':main()
