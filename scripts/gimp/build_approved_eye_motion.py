"""Separate approved closed lashes/skin and build a textured blink in GIMP 3.

This is an appearance/motion prototype. PSD parts are not a Cubism rig.
"""
import os
from pathlib import Path
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
exec((ROOT/'scripts/gimp/build_approved_eye_keys.py').read_text(encoding='utf-8').split('board = Gimp.Image.new')[0])
OUT=ROOT/'assets/private/ciel/live2d/gimp/approved-eye-motion-v1'
OUT.mkdir(parents=True,exist_ok=True)
old_render=render
def ease(v):
    v=max(0,min(1,v)); return v*v*(3-2*v)

materials={}
separation=[]
for side,item in data.items():
    g=item['g']; a,b=g['x']; sx=164 if side=='R' else 402
    raw=bytearray(W*H*4)
    for y in range(H):
        for x in range(a,b+1):
            i=4*(y*W+x)
            rgb=read(2*724+sx+(x-a)*1.9,320+(y-52)*1.9)
            blend=ease((y-70)/7)
            base=item['buffers']['Skin_Backfill'][i:i+3]
            # Off-domain rows are used only to estimate the material background.
            if i not in item['domain']: base=(246,247,251)
            raw[i:i+4]=bytes([round(rgb[c]*blend+base[c]*(1-blend)) for c in range(3)]+[255])
    lash=bytearray(W*H*4); skin=bytearray(raw); anchors={}; widths={}
    error=0
    for x in range(a,b+1):
        ys=[y for y in range(76,103) if min(raw[4*(y*W+x):4*(y*W+x)+3])<175]
        if not ys:
            anchors[x]=85.0;widths[x]=2.0;continue
        lo,hi=max(73,min(ys)-2),min(105,max(ys)+2)
        anchors[x]=max(ys)-.5
        widths[x]=max(1.5,max(ys)-min(ys)+1)
        above=raw[4*((lo-1)*W+x):4*((lo-1)*W+x)+3]
        below=raw[4*((hi+1)*W+x):4*((hi+1)*W+x)+3]
        for y in range(lo,hi+1):
            i=4*(y*W+x); t=(y-lo+1)/(hi-lo+2)
            background=[round(above[c]*(1-t)+below[c]*t) for c in range(3)]
            pixel=raw[i:i+3]
            alpha=max(0,min(1,max((background[c]-pixel[c])/max(1,background[c]-20)
                    if pixel[c]<=background[c] else (pixel[c]-background[c])/max(1,255-background[c])
                    for c in range(3))))
            alpha=math.ceil(alpha*255)/255
            if alpha:
                color=[max(0,min(255,round(background[c]+(pixel[c]-background[c])/alpha))) for c in range(3)]
                lash[i:i+4]=bytes(color+[round(alpha*255)])
                skin[i:i+4]=bytes(background+[255])
                error=max(error,max(abs(round(color[c]*alpha+background[c]*(1-alpha))-pixel[c]) for c in range(3)))
    assert error<=1
    # A deformation guide follows the lid as a whole, not each individual
    # lash tip. Per-column tip heights caused vertical seams during scaling.
    for _ in range(2):
        anchors={x:sum(anchors[j] for j in range(max(a,x-6),min(b,x+6)+1))/len(range(max(a,x-6),min(b,x+6)+1)) for x in anchors}
    mean_width=sum(widths.values())/len(widths)
    widths={x:mean_width for x in widths}
    materials[side]=dict(lash=lash,skin=skin,raw=raw,anchors=anchors,widths=widths)
    separation.append(dict(side=side,roundtrip_max_rgb_error=error,
        lash_nontransparent_pixels=sum(lash[i]>0 for i in range(3,len(lash),4))))
src.delete()

def render(dx,closure,include_foreground=True):
    if closure==0:return old_render(dx,0,include_foreground)
    result=bytearray(reference)
    for side,item in data.items():
        g,b=item['g'],item['buffers']; mat=materials[side]
        for i in item['domain']:
            if i in stationary_fold_indices:continue
            x,y=(i//4)%W,(i//4)//W
            u,d=curve(g['upper'],x+.5),curve(g['lower'],x+.5)
            t=max(0,min(1,(x+.5-g['x'][0])/(g['x'][1]-g['x'][0])))
            guide=(1-t)*g['upper'][0][1]+t*g['upper'][-1][1]+10*math.sin(math.pi*t)
            texture_anchor=mat['anchors'].get(x,85)
            close=guide*(1-ease(closure))+texture_anchor*ease(closure)
            top=u+(close-u)*closure; bottom=d+(close-d)*closure
            rgb=[b['Skin_Backfill'][i+c]*(1-ease(closure))+mat['skin'][i+c]*ease(closure) for c in range(3)]
            if closure>=1 or d<=u:aperture=0
            else:
                ratio=(d-u)/max(.001,bottom-top)
                aperture=sum(sample(item['opening_mask'],x,u+(y+.5+offset*closure-top)*ratio-.5)[1]
                             for offset in (-.375,-.125,.125,.375))/4
            fg,alpha=sample(item['iris'],x-dx,y)
            eye=over(item['sclera'][i:i+3],fg,alpha)
            rgb=[eye[c]*aperture+rgb[c]*(1-aperture) for c in range(3)]
            open_width=max(2,u-curve(g['outer'],x+.5))
            closed_width=mat['widths'].get(x,2)
            target_width=open_width*(1-.68*closure)*(1-ease(closure))+closed_width*ease(closure)
            thickness=target_width/open_width
            sy=u+(y-top)/thickness
            samples=[sample(item['lash_motion'],x,sy+offset*closure/thickness) for offset in (-.375,-.125,.125,.375)]
            open_fg=[sum(s[0][c] for s in samples)/4 for c in range(3)]
            open_a=sum(s[1] for s in samples)/4
            closed_fg,closed_a=sample(mat['lash'],x,texture_anchor+(y-top)*closed_width/target_width)
            weight=ease((closure-.2)/.55)
            fg=[open_fg[c]*(1-weight)+closed_fg[c]*weight for c in range(3)]
            alpha=open_a*(1-weight)+closed_a*weight
            rgb=over(rgb,fg,alpha)
            fg,alpha=sample(b['LowerRim'],x,y-(bottom-d))
            rgb=over(rgb,[v*(1-closure) for v in fg],alpha*(1-closure))
            fold_alpha=b['UpperFold'][i+3]/255*(1-ease(closure/.25))
            rgb=over(rgb,[b['UpperFold'][i+c]*fold_alpha for c in range(3)],fold_alpha)
            result[i:i+4]=bytes([max(0,min(255,round(v))) for v in rgb]+[255])
    if include_foreground:
        hair_underlay_samples[(dx,closure)]=[list(result[i:i+3]) for i in translucent_hair_indices]
        for i in hair_indices:
            alpha=hair_matte[i+3]/255
            result[i:i+3]=bytes(round(hair_matte[i+c]*alpha+result[i+c]*(1-alpha)) for c in range(3))
    return bytes(result)

doc=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
context=bytearray(reference)
for item in data.values():
    for i in item['domain']:
        if i not in stationary_fold_indices:context[i:i+4]=bytes(4)
layer(doc,'Context',context)
for side,item in data.items():
    for name in ('skin','lash'):
        material=bytearray(W*H*4)
        for i in item['domain']:
            if i not in stationary_fold_indices:material[i:i+4]=materials[side][name][i:i+4]
        layer(doc,f'{side}_Closed_{name}',material)
layer(doc,'Hair_Foreground',hair_matte)
for material_layer in doc.get_layers():
    material_layer.set_blend_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
    material_layer.set_composite_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
expected=composite(doc)
expected_parts={item.get_name():pixels(item) for item in doc.get_layers()}
closed=render(0,1)
assert max(abs(a-b) for a,b in zip(expected,closed))<=1, max(abs(a-b) for a,b in zip(expected,closed))
for suffix,proc in (('xcf','gimp-xcf-save'),('psd','file-psd-export')):
    path=OUT/f'closed-materials.{suffix}'
    run_proc(proc,image=doc,file=Gio.File.new_for_path(str(path)))
    check=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(path)))
    assert composite(check)==expected
    assert {item.get_name():pixels(item) for item in check.get_layers()}==expected_parts
    check.delete()
doc.delete()
board=Gimp.Image.new(W*5,H,Gimp.ImageBaseType.RGB)
for col,amount in enumerate((0,.25,.5,.75,1)):
    rgba=render(0,amount)
    layer(board,f'Closed_{amount}',rgba,col*W,0)
run_proc('file-png-export',image=board,file=Gio.File.new_for_path(str(OUT/'comparison.png')))
board.delete()
png('closed',closed)
assert render(0,0)==reference
assert render(-4,1)==render(4,1)==closed
if os.environ.get('CIEL_APPROVED_EYE_CENTRE_CHECK')=='1':
    indices=[4*(y*W+x)+c for y in range(40,111) for x in range(35,246) for c in range(3)]
    continuity=[]
    for label,draw in (('previous',old_render),('candidate',render)):
        frames=[draw(0,n/32) for n in range(33)]
        changes=[sum(abs(a[i]-b[i]) for i in indices)/len(indices) for a,b in zip(frames,frames[1:])]
        continuity.append(dict(renderer=label,onset=changes[0],worst=max(changes),steps=changes))
    (OUT/'centre-check.json').write_text(json.dumps(continuity,indent=2)+'\n',encoding='utf-8')
    print('CENTRE_CHECK',[(r['renderer'],r['onset'],r['worst']) for r in continuity],flush=True)
(OUT/'materials-report.json').write_text(json.dumps(dict(
    status='textured_motion_candidate',separation=separation,
    closed_psd_xcf_compositing_verified=True,
    closed_psd_xcf_all_parts_equal=True,layer_count=len(expected_parts),
    approved_reference_sha256=hashlib.sha256(approved.read_bytes()).hexdigest(),
    limitations=['Source-resolution registered material, not new high-resolution detail',
                 'Blink interpolation is software deformation, not a Cubism rig',
                 'Skin/lash separation estimates hidden background from nearby samples']),indent=2)+'\n',encoding='utf-8')
if os.environ.get('CIEL_APPROVED_EYE_ATLAS')=='1':
    report=dict(stage='Approved closed design, software motion candidate; not Cubism',
        source=SOURCE.relative_to(ROOT).as_posix(),crop=list(CROP),
        normal_sha256=hashlib.sha256(reference).hexdigest(),normal_changed_pixels=0,
        foreground_holdout_pixels=len(opaque_hair_indices),foreground_source_pixels=len(hair_indices),
        stationary_fold_pixels=stationary_fold_by_side,separation=separation,
        generator_sha256=hashlib.sha256((ROOT/'scripts/gimp/build_approved_eye_motion.py').read_bytes()).hexdigest(),
        limitations=['280x195 source-resolution prototype',
                    'Cubism keyforms and Unity rendering not implemented for this new material'])
    exec((ROOT/'scripts/gimp/build_face_remake_expressions.py').read_text(encoding='utf-8'))
print('APPROVED_EYE_MOTION_READY',flush=True)
