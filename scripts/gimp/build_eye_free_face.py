"""Prepare an always-present eye-free face with separately toggled eye parts.

GIMP 3 batch script. This is a material candidate, not a Cubism rig.
"""
import os,json,hashlib
from pathlib import Path
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
exec((ROOT/'scripts/gimp/eye_material_core.py').read_text(encoding='utf-8'))
OUT=ROOT/'assets/private/ciel/live2d/gimp/eye-free-face'
OUT.mkdir(parents=True,exist_ok=True)
input_path=ROOT/'assets/private/ciel/live2d/gimp/forelock-materials/forelock-materials.psd'
assert input_path.exists(),'Generate forelock-materials first; do not substitute an unrelated PSD'
source=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(input_path)))
source_parts={l.get_name():pixels(l) for l in source.get_layers()}
assert composite(source)==reference
source.delete()
hair={k:v for k,v in source_parts.items() if k.startswith('Hair_')}
assert len(hair)==3
under=source_parts['Face_hidden_underpaint_ESTIMATED']
hair_pixels={i for i in range(0,W*H*4,4) if any(v[i+3] for v in hair.values())}
base=bytearray(under)
anchors=[]
for cx,cy in [(78,119),(107,123),(144,115),(173,124),(202,118)]:
    colors=[reference[4*(y*W+x):4*(y*W+x)+3] for y in range(cy-2,cy+3) for x in range(cx-2,cx+3)]
    anchors.append((cx,cy,[sum(c[k] for c in colors)/len(colors) for k in range(3)]))
def skin(x,y):
    weights=[1/(16+(x-cx)**2+.1*(y-cy)**2) for cx,cy,c in anchors]
    return bytes([round(sum(w*c[k] for w,(_,_,c) in zip(weights,anchors))/sum(weights)) for k in range(3)]+[255])
# The first fringe trace left fine central-tip contours in the face. Transfer
# those pixels out of the base into the central fringe, keeping encoded-RGB
# compositing exact. This anatomically bounded cleanup does not include eyes.
central_tip_region=[(112,60),(128,66),(146,71),(165,58),(165,84),(112,84)]
central=bytearray(hair['Hair_Center'])
transferred=[]
for y in range(58,84):
    for x in range(112,165):
        i=4*(y*W+x)
        if i in hair_pixels or not inside(x+.5,y+.5,central_tip_region):continue
        bg=skin(x,y)
        base[i:i+4]=bg
        if under[i:i+3]==bg[:3]:continue
        # Minimum representable alpha preserves subtle lines without turning
        # the whole cleanup polygon into an opaque skin-colored hair patch.
        for aa in range(1,256):
            a=aa/255
            color=[round((under[i+k]-bg[k]*(1-a))/a) for k in range(3)]
            if all(0<=v<=255 for v in color) and all(round(color[k]*a+bg[k]*(1-a))==under[i+k] for k in range(3)):break
        central[i:i+4]=bytes(color+[aa]);transferred.append([x,y,aa])
        hair_pixels.add(i)
hair['Hair_Center']=bytes(central)
eyes={};fixed=bytearray(W*H*4)
for side,item in data.items():
    names=['Sclera','Iris','Pupil','Highlight','UpperLash','LowerRim']
    for name in names:eyes[f'{side}_{name}']=bytearray(W*H*4)
    for i in item['domain']:
        x,y=(i//4)%W,(i//4)//W
        if i in hair_pixels:continue # The hair's estimated underpaint is already present.
        base[i:i+4]=skin(x,y)
        owners=[name for name in names if item['buffers'][name][i+3]]
        if owners:
            assert len(owners)==1
            eyes[f'{side}_{owners[0]}'][i:i+4]=under[i:i+4]
        else:
            # Preserve the fixed periorbital contour separately for diagnosis.
            # Never hide it in the eye-free base or label it a finished eyelid.
            fixed[i:i+4]=under[i:i+4]
# White and iris must remain surfaces when parts are moved or filtered, not
# complementary puzzle pieces. Extend them underneath their opaque children.
eye_underpaint_checks={}
for side,item in data.items():
    sclera=eyes[f'{side}_Sclera'];iris=eyes[f'{side}_Iris']
    pupil=eyes[f'{side}_Pupil'];highlight=eyes[f'{side}_Highlight']
    iris_known=[i for i in item['domain'] if iris[i+3]==255]
    assert iris_known
    covered=[i for i in item['domain'] if pupil[i+3] or highlight[i+3]]
    for i in covered:
        x,y=(i//4)%W,(i//4)//W
        nearby=sorted(iris_known,key=lambda j:((j//4)%W-x)**2+2*((j//4)//W-y)**2)[:8]
        iris[i:i+4]=bytes([round(sum(iris[j+k] for j in nearby)/len(nearby)) for k in range(3)]+[255])
    filled=0
    for i in item['domain']:
        if iris[i+3] and not sclera[i+3]:
            sclera[i:i+4]=item['sclera'][i:i+4];sclera[i+3]=255;filled+=1
    assert all(iris[i+3]==255 and sclera[i+3]==255 for i in covered)
    assert all(sclera[i+3]==255 for i in item['domain'] if iris[i+3])
    eye_underpaint_checks[side]=dict(iris_under_pupil_highlight_pixels=len(covered),
        sclera_under_iris_pixels=filled,opaque_underpaint_verified=True,
        limitation='Hidden surfaces outside the original eye aperture are not yet extended')
doc=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
layer(doc,'Face_Base_eye_free_ESTIMATED',base)
layer(doc,'Periorbital_contours_REVIEW',fixed)
for name,rgba in eyes.items():layer(doc,name,rgba)
for name,rgba in hair.items():layer(doc,name,rgba)
for l in doc.get_layers():
    l.set_blend_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
    l.set_composite_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
normal=composite(doc)
assert normal==reference,'Separating eyes must not alter the neutral composite'
expected={l.get_name():pixels(l) for l in doc.get_layers()}
checks={}
for suffix,proc in [('xcf','gimp-xcf-save'),('psd','file-psd-export')]:
    target=OUT/f'eye-free-face.{suffix}'
    run_proc(proc,image=doc,file=Gio.File.new_for_path(str(target)))
    loaded=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(target)))
    assert composite(loaded)==reference
    assert {l.get_name():pixels(l) for l in loaded.get_layers()}==expected
    checks[suffix]=dict(neutral_equal=True,all_parts_equal=True)
    loaded.delete()
for l in doc.get_layers():
    if l.get_name() in eyes or l.get_name()=='Periorbital_contours_REVIEW':l.set_visible(False)
without_eyes=composite(doc)
for l in doc.get_layers():
    if l.get_name() in hair:l.set_visible(False)
base_only=composite(doc)
assert base_only==base
assert all(base[i]==255 for i in range(3,len(base),4))
run_proc('gimp-xcf-save',image=doc,file=Gio.File.new_for_path(str(OUT/'face-base-review.xcf')))
doc.delete()
board=Gimp.Image.new(W*3,H,Gimp.ImageBaseType.RGB)
for col,(name,rgba) in enumerate([('Neutral',normal),('Eyes_hidden',without_eyes),('Eyes_and_forelock_hidden',base_only)]):
    layer(board,name,rgba,col*W,0)
run_proc('file-png-export',image=board,file=Gio.File.new_for_path(str(OUT/'comparison.png')))
board.delete()
report=dict(status='eye_free_base_candidate_requires_visual_refinement',
    architecture='One persistent face base; eyes and forelock are independent layers. No closed-skin cover layer.',
    source_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
    layer_count=len(expected),roundtrip=checks,face_base_opaque=True,
    neutral_equal=True,eyes_hidden_by_layer_visibility=True,
    central_tip_contours_transferred_to_hair=transferred,
    eye_underpaint=eye_underpaint_checks,
    limits=['280x195 crop; high-resolution repaint still needed',
            'Eye-part boundaries inherit the earlier tracing and require review',
            'Separate periorbital contour layer may contain hair or eyelid fragments',
            'Skin is estimated from cheek samples; base is not aesthetically approved',
            'Sclera under iris and iris under pupils are filled; outer hidden aperture still needs review',
            'No Cubism meshes or blink keys yet'])
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('EYE_FREE_FACE_READY',flush=True)
