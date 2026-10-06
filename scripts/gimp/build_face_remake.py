"""Source-resolution semantic eye remake. Run inside GIMP 3, not ordinary Python.

Normal partitions preserve the approved pixels. Hair holdouts, upper lash,
lower rim and iris move/occlude independently. This is not a Cubism model.
"""
import os
import json
import math
import hashlib
from pathlib import Path
from gi.repository import Gimp, Gio, Gegl

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
OUT = ROOT / 'assets/private/ciel/live2d/gimp/face-remake-v2'
OUT.mkdir(parents=True, exist_ok=True)
W, H = 280, 195
CROP = (330, 235, W, H)
FMT = "R'G'B'A u8"
RECT = Gegl.Rectangle.new(0, 0, W, H)
SOURCE = ROOT / 'docs/assets/ciel/ciel-approved-appearance-v1.png'

def run_proc(name, **values):
    proc = Gimp.get_pdb().lookup_procedure(name)
    config = proc.create_config()
    config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
    for key, value in values.items(): config.set_property(key.replace('_', '-'), value)
    result = proc.run(config)
    if result.index(0) != Gimp.PDBStatusType.SUCCESS: raise RuntimeError(name)

def pixels(layer):
    return bytes(layer.get_buffer().get(RECT, 1.0, FMT, Gegl.AbyssPolicy.NONE))

def layer(doc, name, rgba, x=0, y=0):
    item = Gimp.Layer.new(doc, name, W, H, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
    doc.insert_layer(item, None, 0)
    buf = item.get_buffer(); buf.set(RECT, FMT, bytes(rgba)); buf.flush()
    item.update(0, 0, W, H); item.set_offsets(x, y)
    return item

def composite(doc):
    item = Gimp.Layer.new_from_visible(doc, doc, 'Verification')
    doc.insert_layer(item, None, 0)
    result = pixels(item); doc.remove_layer(item)
    return result

def png(name, rgba):
    doc = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
    layer(doc, name, rgba)
    run_proc('file-png-export', image=doc, file=Gio.File.new_for_path(str(OUT / (name + '.png'))))
    doc.delete()

def inside(x,y,poly):
    result=False
    j=len(poly)-1
    for i,(xi,yi) in enumerate(poly):
        xj,yj=poly[j]
        if (yi>y)!=(yj>y) and x<(xj-xi)*(y-yi)/(yj-yi)+xi: result=not result
        j=i
    return result

def curve(points,x):
    if x<=points[0][0]: return points[0][1]
    for n,((a,b),(c,d)) in enumerate(zip(points,points[1:])):
        if x<=c:
            p=points[max(0,n-1)];q=points[min(len(points)-1,n+2)]
            m0=(d-p[1])/(c-p[0]);m1=(q[1]-b)/(q[0]-a)
            t=(x-a)/(c-a)
            return (2*t**3-3*t*t+1)*b+(t**3-2*t*t+t)*(c-a)*m0+(-2*t**3+3*t*t)*d+(t**3-t*t)*(c-a)*m1
    return points[-1][1]

original=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(SOURCE)))
original.crop(W,H,*CROP[:2]); reference=pixels(original.get_layers()[0]); original.delete()

# Manually traced anatomical boundaries, not brightness-based classification.
geometry={
 'R': dict(x=(39,111),
   outer=[(39,78),(48,65),(61,56),(73,52),(83,53),(95,58),(105,66),(111,75)],
   upper=[(39,78),(48,80),(55,71),(65,65),(76,61),(87,62),(99,66),(106,72),(111,75)],
   lower=[(39,78),(48,84),(56,94),(69,100),(82,103),(95,101),(103,94),(108,83),(111,75)],
   iris=[(76,60),(88,61),(99,66),(104,74),(106,84),(102,96),(96,102),(80,104),(71,97),(67,87),(66,76),(69,66)],
   hair=[[(67,40),(71,46),(74,53),(76,61),(75,62),(72,55),(69,49)],
         [(35,54),(40,60),(45,65),(49,68),(45,70),(40,74),(36,78)]],
   pupil=(87,79,3.5,6.5),highlights=[(87,68.5,3.6,3.6),(77,63.5,2.8,2.6)]),
 'L': dict(x=(168,240),
   outer=[(168,74),(172,63),(175,61),(181,56),(188,51),(198,49),(205,50),(213,51),(216,52),(220,54),(222,56),(230,63),(236,70),(240,74)],
   upper=[(168,74),(176,71),(184,64),(196,58),(203,58.7),(210,63),(218,69),(229,79),(240,74)],
   lower=[(168,74),(175,89),(183,100),(198,102),(212,100),(225,94),(233,84),(240,74)],
   iris=[(188,59),(200,58),(203,58),(209,64),(214,73),(215,85),(210,96),(203,101),(185,101),(178,94),(174,84),(175,72),(179,64)],
   hair=[[(202,36),(210,43),(219,49),(216,51),(210,49),(204,45)],
         [(233,49),(238,53),(245,57),(244,74),(240,78),(237,72),(235,64)]],
   pupil=(193,77,3.5,6.5),highlights=[(192.5,66.5,4,4),(203.5,60,2.1,2.1)]),
}

parts={'Context':bytearray(reference),'Hair_Foreground':bytearray(W*H*4)}
hair_indices=set()
eye_indices=set()
data={}
def ellipse(x,y,p):
    cx,cy,rx,ry=p
    return ((x-cx)/rx)**2+((y-cy)/ry)**2<=1

for side,g in geometry.items():
    buffers={n:bytearray(W*H*4) for n in ['Skin_Backfill','Sclera','Iris','Pupil','Highlight','UpperLash','LowerRim','UpperFold']}
    domain=set(); iris_domain=set(); opening=set()
    lash_top={}
    for x in range(g['x'][0],g['x'][1]+1):
        top,u=curve(g['outer'],x+.5),curve(g['upper'],x+.5)
        dark=[y for y in range(max(44,math.floor(top)-5),math.ceil(u))
              if max(reference[4*(y*W+x):4*(y*W+x)+3])<150]
        lash_top[x]=min(top-7,min(dark)-1.5) if dark else top-7
    for y in range(44,109):
      for x in range(g['x'][0],g['x'][1]+1):
        i=4*(y*W+x)
        top,u,d=curve(g['outer'],x+.5),curve(g['upper'],x+.5),curve(g['lower'],x+.5)
        # Only the traced ocular surface is editable; the rest stays in Context.
        if not lash_top[x]<=y+.5<=d+1: continue
        domain.add(i); eye_indices.add(i)
        # The inner left-eye bang overlaps a grey lash reflection. Preserve only
        # its pale hair core here, not that reflection as stationary foreground.
        is_hair=any(inside(x+.5,y+.5,p) and min(reference[i:i+3])>(200 if side=='L' and n==0 else 140)
                    for n,p in enumerate(g['hair']))
        if is_hair:
            parts['Hair_Foreground'][i:i+4]=reference[i:i+4];hair_indices.add(i)
            parts['Context'][i:i+4]=bytes(4)
            continue
        if y+.5<top-1: owner='UpperFold'
        elif y+.5<u: owner='UpperLash'
        elif y+.5>d-1 and reference[i+2]-reference[i]<32: owner='LowerRim'
        else:
            opening.add(i)
            near_iris = inside(x+.5,y+.5,g['iris']) or any(
                inside(x+.5+ox,y+.5+oy,g['iris']) for ox,oy in [(-2,0),(2,0),(0,-2),(0,2)])
            blue_edge = reference[i+2]-reference[i]>32
            if inside(x+.5,y+.5,g['iris']) or (near_iris and blue_edge):
                iris_domain.add(i)
                if any(ellipse(x+.5,y+.5,p) for p in g['highlights']): owner='Highlight'
                elif ellipse(x+.5,y+.5,g['pupil']): owner='Pupil'
                else: owner='Iris'
            else: owner='Sclera'
        buffers[owner][i:i+4]=reference[i:i+4]
        parts['Context'][i:i+4]=bytes(4)
    # The uncovered eye is a white plane. Visible source sclera stays verbatim.
    sclera=bytearray(buffers['Sclera'])
    white_samples=[i for i in domain if buffers['Sclera'][i+3]
                   and min(reference[i:i+3])>175 and max(reference[i:i+3])-min(reference[i:i+3])<40]
    assert white_samples
    clean_skin=[4*(yy*W+xx) for yy in range(111,132)
                for xx in range(g['x'][0],g['x'][1]+1)
                if min(reference[4*(yy*W+xx):4*(yy*W+xx)+3])>238
                and max(reference[4*(yy*W+xx):4*(yy*W+xx)+3])-min(reference[4*(yy*W+xx):4*(yy*W+xx)+3])<18]
    assert clean_skin
    for i in domain:
        x,y=(i//4)%W,(i//4)//W
        if not sclera[i+3]:
            nearest=sorted(white_samples,key=lambda j:.3*((j//4)%W-x)**2+4*((j//4)//W-y)**2)[:6]
            sclera[i:i+4]=bytes([round(sum(reference[j+c] for j in nearest)/len(nearest)) for c in range(3)]+[255])
        nearest=sorted(clean_skin,key=lambda j:((j//4)%W-x)**2+((j//4)//W-116)**2)[:8]
        buffers['Skin_Backfill'][i:i+4]=bytes([round(sum(reference[j+c] for j in nearest)/8) for c in range(3)]+[255])
    iris=bytearray(W*H*4)
    for n in ['Iris','Pupil','Highlight']:
        for i in iris_domain:
            if buffers[n][i+3]: iris[i:i+4]=buffers[n][i:i+4]
    # Continue the iris under the upper lash; keep reflections with the lash.
    known=[i for i in iris_domain]
    hidden=bytearray(W*H*4)
    for y in range(54,105):
      for x in range(g['x'][0],g['x'][1]+1):
        i=4*(y*W+x)
        if inside(x+.5,y+.5,g['iris']) and not iris[i+3]:
            j=min(known,key=lambda j:((j//4)%W-x)**2+4*((j//4)//W-y)**2)
            iris[i:i+4]=reference[j:j+4];hidden[i:i+4]=reference[j:j+4]
    # Fully separate edit layers; underpainting sits below original partitions.
    parts[f'{side}_Skin_Backfill']=buffers['Skin_Backfill']
    fill=bytearray(sclera)
    for i in range(0,len(reference),4):
        if buffers['Sclera'][i+3]:fill[i:i+4]=bytes(4)
    parts[f'{side}_Sclera_Hidden']=fill
    parts[f'{side}_Iris_Hidden']=hidden
    for name,rgba in buffers.items():
        if name!='Skin_Backfill':parts[f'{side}_{name}']=rgba
    lash_motion=bytearray(buffers['UpperLash'])
    # Removing foreground hair also removes the lash below it. Reconstruct that
    # covered lash before deformation, otherwise a slit travels away with the lid.
    for i in domain & hair_indices:
        x,y=(i//4)%W,(i//4)//W
        # Only reconstruct the actual lash band. Extending this dark fill into
        # skin above the lash creates a detached spike when the lid moves down.
        if not curve(g['outer'],x+.5)<=y+.5<curve(g['upper'],x+.5):continue
        candidates=[j for j in domain if buffers['UpperLash'][j+3] and min(reference[j:j+3])<110]
        j=min(candidates,key=lambda j:((j//4)%W-x)**2+4*((j//4)//W-y)**2)
        lash_motion[i:i+4]=reference[j:j+4]
    data[side]=dict(g=g,buffers=buffers,domain=domain,opening=opening,sclera=sclera,iris=iris,lash_motion=lash_motion)

# Preserve stationary periorbital contours instead of fading the whole strip.
# This is the same geometric ownership rule verified in Cubism material v4.
stationary_fold_indices=set()
stationary_fold_by_side={}
for side,item in data.items():
    fold=item['buffers']['UpperFold']; moved=[]
    for i in item['domain']:
        x,y=(i//4)%W,(i//4)//W
        if fold[i+3] and y+.5 < curve(item['g']['outer'],x+.5)-2.5:
            assert parts['Context'][i+3]==0
            parts['Context'][i:i+4]=fold[i:i+4]
            fold[i:i+4]=bytes(4)
            stationary_fold_indices.add(i);moved.append([x,y])
    stationary_fold_by_side[side]=sorted(moved)

# Hair is always the final overlay. Context contains no copy below moving parts.
parts['Context']=parts.pop('Context')
parts['Hair_Foreground']=parts.pop('Hair_Foreground')
hair_matte=None
translucent_hair_indices=[]
hair_underlay_samples={}

def sample(buf,x,y):
    x0,y0=math.floor(x),math.floor(y)
    fx,fy=x-x0,y-y0
    rgb=[0.0]*3;a=0.0
    for xx,yy,w in [(x0,y0,(1-fx)*(1-fy)),(x0+1,y0,fx*(1-fy)),(x0,y0+1,(1-fx)*fy),(x0+1,y0+1,fx*fy)]:
        if not 0<=xx<W or not 0<=yy<H or not w:continue
        j=4*(yy*W+xx);wa=w*buf[j+3]/255
        a+=wa
        for c in range(3):rgb[c]+=wa*buf[j+c]
    return rgb,a

def over(rgb,fg,a): return [fg[c]+rgb[c]*(1-a) for c in range(3)]

for item in data.values():
    opening_mask=bytearray(W*H*4)
    for i in item['opening']:opening_mask[i+3]=255
    item['opening_mask']=opening_mask

def render(dx,closure,include_foreground=True,refined_lid_side=None):
    result=bytearray(reference)
    for side,item in data.items():
      g,b=item['g'],item['buffers']
      for i in item['domain']:
        if i in stationary_fold_indices:continue
        x,y=(i//4)%W,(i//4)//W
        u,d=curve(g['upper'],x+.5),curve(g['lower'],x+.5)
        t=max(0,min(1,(x+.5-g['x'][0])/(g['x'][1]-g['x'][0])))
        # Closed key shape: corner positions stay anchored; a smooth arc avoids
        # carrying individual open-eye pixels into a serrated closed lash.
        close=(1-t)*g['upper'][0][1]+t*g['upper'][-1][1]+10*math.sin(math.pi*t)
        top=u+(close-u)*closure
        bottom=d+(close-d)*closure
        rgb=list(b['Skin_Backfill'][i:i+3])
        # Deform the source aperture continuously. Switching from the original
        # ownership mask to an analytical mask at any nonzero closure caused a
        # visible jump. Pixel centers map identically at the neutral endpoint.
        if closure==0:aperture=1.0 if i in item['opening'] else 0.0
        elif closure>=1 or d<=u:aperture=0.0
        else:
            ratio=(d-u)/max(.001,bottom-top)
            aperture=sum(sample(item['opening_mask'],x,
                u+(y+.5+offset*closure-top)*ratio-.5)[1]
                for offset in [-.375,-.125,.125,.375])/4
        if side==refined_lid_side and 0<closure<1:
            # Study candidate: trace an optical aperture rather than deforming
            # binary source pixels. Ease in to preserve the neutral endpoint.
            analytic=sum(top<=y+sy<=bottom for sy in
                         [.0625,.1875,.3125,.4375,.5625,.6875,.8125,.9375])/8
            blend=min(1,closure/.25)
            blend=blend*blend*(3-2*blend)
            aperture=aperture*(1-blend)+analytic*blend
        white=list(item['sclera'][i:i+3])
        fg,alpha=sample(item['iris'],x-dx,y)
        eye=over(white,fg,alpha)
        rgb=[eye[c]*aperture+rgb[c]*(1-aperture) for c in range(3)]
        # Upper lash carries its own reflection and moves with the lid, not gaze.
        thickness=1-.68*closure
        source_y=u+(y-top)/thickness
        if closure:
            samples=[sample(item['lash_motion'],x,source_y+offset*closure/thickness) for offset in [-.375,-.125,.125,.375]]
            fg=[sum(s[0][c] for s in samples)/4 for c in range(3)]
            alpha=sum(s[1] for s in samples)/4
        else:fg,alpha=sample(item['lash_motion'],x,source_y)
        textured=over(rgb,fg,alpha)
        taper=math.sin(math.pi*t)**.45
        stroke_width=(u-curve(g['outer'],x+.5))*(1-closure)+1.8*taper*closure
        coverage=max(0,min(1,y+1-(top-stroke_width),top+.5-y))
        drawn=over(rgb,[v*coverage for v in (48,53,67)],coverage)
        key_weight=closure**2
        rgb=[textured[c]*(1-key_weight)+drawn[c]*key_weight for c in range(3)]
        fg,alpha=sample(b['LowerRim'],x,y-(bottom-d))
        fg=[v*(1-closure) for v in fg];alpha*=1-closure
        rgb=over(rgb,fg,alpha)
        if side==refined_lid_side and 0<closure<1:
            # Independent lower-lid contour, strongest at half closure.
            # It must not travel with iris gaze or alter the approved neutral.
            width=.7*math.sin(math.pi*t)**.6
            coverage=sum(abs(y+sy-bottom)<width/2 for sy in
                         [.0625,.1875,.3125,.4375,.5625,.6875,.8125,.9375])/8
            alpha=coverage*.7*4*closure*(1-closure)
            rgb=over(rgb,[v*alpha for v in (105,119,145)],alpha)
        # This source partition includes the old lash rim, not just a skin fold.
        # Fade it out by 25% closure so a second line cannot stay above the lid.
        # Smoothstep keeps the neutral endpoint and the cutoff continuous.
        fold_progress=min(1,closure/.25)
        fold_visibility=1-fold_progress*fold_progress*(3-2*fold_progress)
        fold_alpha=b['UpperFold'][i+3]/255*fold_visibility
        rgb=over(rgb,[b['UpperFold'][i+c]*fold_alpha for c in range(3)],fold_alpha)
        result[i:i+4]=bytes([max(0,min(255,round(v))) for v in rgb]+[255])
    if include_foreground:
        if hair_matte is None:
            for i in hair_indices:result[i:i+4]=reference[i:i+4]
        else:
            hair_underlay_samples[(dx,closure)]=[list(result[i:i+3]) for i in translucent_hair_indices]
            for i in hair_indices:
                a=hair_matte[i+3]/255
                result[i:i+3]=bytes(round(hair_matte[i+c]*a+result[i+c]*(1-a)) for c in range(3))
    return bytes(result)

# Estimate only the existing traced hair pixels. The GIMP/PSD two-layer study
# separately verifies this encoded-RGB alpha equation and exact neutral rebuild.
hair_base=render(0,0,include_foreground=False)
hair_matte=bytearray(W*H*4)
for i in sorted(hair_indices):
    c,b=reference[i:i+3],hair_base[i:i+3]
    x,y=(i//4)%W,(i//4)//W
    neighbors=[j for j in hair_indices if abs((j//4)%W-x)<=4 and abs((j//4)//W-y)<=6 and min(reference[j:j+3])>225]
    f=[sum(reference[j+k] for j in neighbors)/len(neighbors) for k in range(3)] if neighbors else [245,247,253]
    delta=[f[k]-b[k] for k in range(3)]
    denominator=sum(v*v for v in delta)
    a=sum((c[k]-b[k])*delta[k] for k in range(3))/denominator if denominator>2500 else 1
    for aa in range(max(1,min(255,round(a*255))),256):
        alpha=aa/255
        ff=[round((c[k]-b[k]*(1-alpha))/alpha) for k in range(3)]
        if all(0<=v<=255 for v in ff) and all(round(ff[k]*alpha+b[k]*(1-alpha))==c[k] for k in range(3)):
            hair_matte[i:i+4]=bytes(ff+[aa]);break
    assert hair_matte[i+3]>0
translucent_hair_indices=sorted(i for i in hair_indices if hair_matte[i+3]<255)
opaque_hair_indices=hair_indices-set(translucent_hair_indices)

normal=render(0,0)
changed=sum(normal[i:i+4]!=reference[i:i+4] for i in range(0,len(reference),4))
print('REMAKE_NORMAL_DIFF',changed,flush=True)
assert changed==0
png('normal',normal)
png('hair-foreground',parts['Hair_Foreground'])
png('hair-foreground-estimated',hair_matte)
png('reference',reference)
png('closed',render(0,1))
for name,rgba in parts.items():png('part-'+name,rgba)

# Inspect semantic masks and extremes before accepting the new renderer.
doc=Gimp.Image.new(W*5,H*3,Gimp.ImageBaseType.RGB)
for row,dx in enumerate([-4,0,4]):
    for col,closure in enumerate([0,.25,.5,.75,1]):
        layer(doc,f'{dx}_{closure}',render(dx,closure),col*W,row*H)
run_proc('file-png-export',image=doc,file=Gio.File.new_for_path(str(OUT/'comparison.png')));doc.delete()
doc=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
for name,rgba in parts.items():layer(doc,name,rgba)
assert composite(doc)==reference, 'Semantic layer composite differs from approved face'
roundtrip={}
for suffix,proc in [('xcf','gimp-xcf-save'),('psd','file-psd-export')]:
    path=OUT/('semantic-parts.'+suffix)
    run_proc(proc,image=doc,file=Gio.File.new_for_path(str(path)))
    loaded=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(path)))
    actual={item.get_name():pixels(item) for item in loaded.get_layers()}
    roundtrip[suffix]=dict(composite_equal=composite(loaded)==reference,
        all_parts_equal=actual=={n:bytes(v) for n,v in parts.items()},layer_count=len(actual))
    assert roundtrip[suffix]['composite_equal'] and roundtrip[suffix]['all_parts_equal']
    loaded.delete()
doc.delete()
(OUT/'geometry.json').write_text(json.dumps(geometry,indent=2),encoding='utf-8')
checks=[]
closed=render(0,1)
for dx in [-4,0,4]:
    for closure in [0,.25,.5,.75,1]:
        rgba=render(dx,closure)
        hair_changed=sum(rgba[i:i+4]!=reference[i:i+4] for i in opaque_hair_indices)
        outside_changed=sum(rgba[i:i+4]!=reference[i:i+4] for i in range(0,len(reference),4) if i not in eye_indices)
        assert hair_changed==outside_changed==0
        fixed_changed=sum(rgba[i:i+4]!=reference[i:i+4] for i in stationary_fold_indices)
        assert fixed_changed==0, 'Stationary upper contours changed during blink'
        if closure==1:assert rgba==closed, 'Gaze remains visible after full closure'
        checks.append(dict(gaze_px=dx,closure=closure,hair_holdout_changes=hair_changed,
                           outside_eye_changes=outside_changed,stationary_fold_changes=fixed_changed))
report=dict(stage='In-progress semantic material study; not approved, not a Cubism rig',
    source=str(SOURCE.relative_to(ROOT)),crop=list(CROP),
    normal_sha256=hashlib.sha256(normal).hexdigest(),normal_changed_pixels=changed,
    foreground_holdout_pixels=len(opaque_hair_indices),foreground_source_pixels=len(hair_indices),
    estimated_translucent_hair_pixels=len(translucent_hair_indices),roundtrip=roundtrip,checks=checks,
    stationary_fold_pixels=stationary_fold_by_side,
    limitations=['280x195 source crop, not final-resolution illustration',
        'Hair alpha is estimated from a flattened image, not recovered original alpha',
        'Lid fold, lash edges and hidden sclera still require visual refinement',
        'Semantic PSD retains opaque hair partitions; estimated alpha is integrated in the preview and separate two-layer material only',
        'Cubism import, rig deformation and Unity verification are pending'])
(OUT/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('REMAKE_INSPECTION_READY',flush=True)
exec((ROOT/'scripts/gimp/build_face_remake_expressions.py').read_text(encoding='utf-8'))
