"""Material proofs and regression checks; not a Cubism rig simulation."""
import sys
sys.dont_write_bytecode=True
from build import *

DIRECTIONS=[(x,y) for y in (-15,0,15) for x in (-15,0,15) if (x,y)!=(0,0)]

def shift_array(a,dx,dy):
    b=np.zeros_like(a);h,w=a.shape
    x0=max(0,dx);x1=min(w,w+dx);y0=max(0,dy);y1=min(h,h+dy)
    b[y0:y1,x0:x1]=a[y0-dy:y1-dy,x0-dx:x1-dx]
    return b

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    state=read(LAY/'layer-state.json');prior=read(OLD/'layer-state.json');manifest=read(LAY/'psd-manifest.json')
    assert len(state['layers'])==54
    assert [r['name'] for r in state['layers']]==[r['name'] for r in prior['layers']]
    assert manifest['layers']==[{k:r[k] for k in ('name','path')} for r in state['layers']]
    assert manifest['out']=='assets/ciel/psd/ciel-v15'
    unchanged={};changed={};alphas={};solid=np.zeros((SIZE[1],SIZE[0]),np.int16);structure=solid.copy()
    structure_names=[]
    for r,oldrow in zip(state['layers'],prior['layers']):
        n=r['name'];p=LAY/(n+'.png');im=Image.open(p)
        assert im.mode=='RGBA' and im.size==SIZE
        assert (r['z'],r['visible'],r['group'],r['clip'])==(oldrow['z'],oldrow['visible'],oldrow['group'],oldrow['clip'])
        equal=sha(p)==sha(OLD/(n+'.png'))
        if n not in ALLOWED:assert equal,n;unchanged[n]=sha(p)
        else:changed[n]={'changed':not equal,'sha256':sha(p),'bbox':im.getbbox()}
        if r['visible']:
            a=np.array(im.getchannel('A'))>200
            solid+=a
            if not n.startswith(('Hair_','Ear_')) and n not in ['Neck_Shadow_Chin','Face_Shadow_Hair']:
                structure+=a;structure_names.append(n)
            if n in ALLOWED:alphas[n]=a
    assert len(unchanged)==43 and all(x['changed'] for x in changed.values())
    source_hashes=read(GEN/'inputs/source-hashes.json')
    assert all(sha(ROOT/p)==v for p,v in source_hashes.items()),'Prior sources changed'
    # Interior-only masks exclude exterior silhouette displacement and the canvas crop edge.
    interior=ndi.distance_transform_edt(solid>0)>32
    structural_interior=ndi.distance_transform_edt(structure>0)>32
    yy,xx=np.indices(solid.shape)
    region=(yy>=1200)&(yy<2860)&(xx>=350)&(xx<1850)
    interior &= region;structural_interior &= region
    records=[]
    groups=[(n,[n]) for n in ALLOWED]+[('body_group',[n for n in ALLOWED if n!='Hair_Back'])]
    for label,names in groups:
        sub=sum((alphas[n].astype(np.int16) for n in names),np.zeros_like(solid))
        strsub=sum((alphas[n].astype(np.int16) for n in names if n in structure_names),np.zeros_like(solid))
        for dx,dy in DIRECTIONS:
            moved=solid-sub+shift_array(sub,dx,dy)
            movedstructure=structure-strsub+shift_array(strsub,dx,dy)
            gap=interior&(moved==0);sgap=structural_interior&(movedstructure==0)
            count=int(gap.sum());scount=int(sgap.sum())
            records.append({'group':label,'dx':dx,'dy':dy,'new_interior_gap_pixels':count,'without_hair_gap_pixels':scount})
            if count or scount:
                mask=Image.fromarray(np.uint8(gap|sgap)*255)
                mask.save(GEN/f'proofs/gap-{label}-{dx}-{dy}.png')
    validation={'canvas':SIZE,'layer_count':54,'protected_layers_byte_identical':43,'order_z_visibility_clip_preserved':True,
      'prior_files_hash_checked':len(source_hashes),'changed_layers':changed,'protected_sha256':unchanged,
      'generation_count':4,'generation_limit':30,
      'motion_method':'11 layers independently and 10-layer body group, 8 translations each, +/-15 native canvas pixels. Alpha>200 union; exterior margin 32px and canvas edges excluded. Also evaluated without Hair/Ear and translucent shadow support.',
      'motion_case_count':len(records),'motion_cases':records,'max_new_interior_gap_pixels':max(r['new_interior_gap_pixels'] for r in records),
      'max_without_hair_gap_pixels':max(r['without_hair_gap_pixels'] for r in records),
      'limitations':['Translation checks only, not deformation, rotation, breathing, Cubism import, or Unity playback.','Interior alpha coverage does not prove color/shadow continuity or every possible combined relative displacement.']}
    write(LAY/'validation.json',validation)
    print(json.dumps({k:v for k,v in validation.items() if k not in ['changed_layers','protected_sha256','motion_cases']},ensure_ascii=True),flush=True)
    # Load images for only the small number of visual proofs, composing one at a time.
    baseline=composite(state)
    groupshift=[n for n in ALLOWED if n!='Hair_Back']
    grid=[]
    for dy in (-15,0,15):
        for dx in (-15,0,15):
            im=composite(state,{n:(dx,dy) for n in groupshift})
            grid.append((f'Body group X {dx:+} / Y {dy:+} px',im.crop((350,1220,1850,2896))))
    panel(grid,GEN/'proofs/motion-body-grid.png',cols=3,width=500)
    del grid
    joints=[]
    for n in ['Body','Outer_R','Outer_L']:
        for dx,dy in [(-15,-15),(0,0),(15,15)]:
            im=composite(state,{n:(dx,dy)},only=structure_names)
            joints.append((f'{n} {dx:+},{dy:+} px / hair off',im.crop((470,1290,1740,2720))))
    panel(joints,GEN/'proofs/motion-joints-no-hair.png',cols=3,width=500,bg='#a74971')
    del joints
    neck=[]
    for label,names in [('Neck + shadow',['Neck','Neck_Shadow_Chin']),('Choker assembly',[n for n in ALLOWED if n.startswith('Choker_')]),('Pendant',['Choker_Pendant'])]:
        for dy in (-15,0,15):
            im=composite(state,{n:(0,dy) for n in names})
            neck.append((f'{label} Y {dy:+} px',im.crop((880,1270,1360,1750))))
    panel(neck,GEN/'proofs/motion-neck-choker.png',cols=3,width=480)
    del neck
    # Large components shown at common 25% scale, neck/accessories at common 100% scale.
    large=[(n+' / 25%',Image.open(LAY/(n+'.png')).convert('RGBA').crop((0,1100,2172,2896))) for n in ['Hair_Back','Body','Outer_R','Outer_L']]
    panel(large,GEN/'proofs/exploded-large.png',cols=4,width=543)
    small=[(n+' / 100%',Image.open(LAY/(n+'.png')).convert('RGBA').crop((820,1160,1420,1760))) for n in ALLOWED if n not in ['Hair_Back','Body','Outer_R','Outer_L']]
    panel(small,GEN/'proofs/exploded-neck-choker.png',cols=4,width=600)
    # Complete back hair, including preserved upper head, and underpainting in context.
    panel([('Hair_Back full / 25%',Image.open(LAY/'Hair_Back.png').convert('RGBA')),('Body underpainting / 25%',Image.open(LAY/'Body.png').convert('RGBA')),('Body + jacket / 25%',composite(state,only=ALLOWED))],GEN/'proofs/underpainting.png',width=543)
    panel([('White background',baseline),('Mid gray background',baseline),('Dark background',baseline)],GEN/'proofs/edges-light-gray-dark.png',width=543)
    # Actual distinct backgrounds rather than a shared panel background.
    backgrounds=[('#ffffff','White'),('#85858d','Mid gray'),('#171b29','Dark')]
    proof=Image.new('RGB',(543*3,724+44),'#e8ebf1');d=ImageDraw.Draw(proof)
    for i,(bg,label) in enumerate(backgrounds):
        d.text((i*543+12,10),label,font=FONT,fill='#202738')
        proof.paste(flatten(baseline,bg).resize((543,724),Image.Resampling.LANCZOS),(i*543,44))
    proof.save(GEN/'proofs/edges-light-gray-dark.png')
    print('All proofs written.',flush=True)

if __name__=='__main__':main()
