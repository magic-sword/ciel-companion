"""Expose current hair ownership and blink boundaries in editable GIMP layers.

This is a diagnosis of the current material, not an accepted hair mask.
Run in GIMP 3 with CIEL_PROJECT_ROOT set. Does not change the motion assets.
"""
import os,json,hashlib
from pathlib import Path
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
exec((ROOT/'scripts/gimp/eye_material_core.py').read_text(encoding='utf-8'))
OUT=ROOT/'assets/private/ciel/live2d/gimp/hair-separation'
OUT.mkdir(parents=True,exist_ok=True)
atlas=ROOT/'docs/assets/ciel/production/ciel-approved-eye-motion-v1-blink-atlas.png'
source=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(atlas)))
buffer=source.get_layers()[0].get_buffer()
neutral=bytes(buffer.get(Gegl.Rectangle.new(W*8,0,W,H),1,FMT,Gegl.AbyssPolicy.NONE))
closed=bytes(buffer.get(Gegl.Rectangle.new(W*8,H*32,W,H),1,FMT,Gegl.AbyssPolicy.NONE))
source.delete()
assert neutral==reference
# A conservative tracing scaffold for the visible front fringe. The top of the
# face crop cuts through the hair: these are editable crop studies, not rooted
# production meshes. Keep opaque source pixels for an exact partition first;
# alpha refinement and the hidden face belong to the next material pass.
fringe_profile=[(0,83),(18,74),(30,63),(39,76),(48,63),(61,54),(73,50),
    (83,51),(95,56),(105,64),(111,73),(118,65),(128,72),(125,61),
    (140,75),(138,65),(148,77),(148,59),(155,69),(162,54),(168,72),
    (172,61),(181,54),(188,49),(198,47),(205,48),(216,50),(222,54),
    (230,61),(236,68),(240,72),(250,57),(265,67),(279,79)]
def fringe_bottom(x):
    for (a,b),(c,d) in zip(fringe_profile,fringe_profile[1:]):
        if a<=x<=c:return b+(d-b)*(x-a)/(c-a)
    return 0
fringe_parts={name:bytearray(W*H*4) for name in ('Hair_R_trace','Hair_Center_trace','Hair_L_trace')}
face=bytearray(reference);fringe_pixels=set()
for y in range(H):
    for x in range(W):
        i=4*(y*W+x)
        if y+.5>=fringe_bottom(x+.5) and i not in hair_indices:continue
        name='Hair_R_trace' if x<111 else 'Hair_Center_trace' if x<168 else 'Hair_L_trace'
        fringe_parts[name][i:i+4]=reference[i:i+4]
        face[i:i+4]=bytes(4);fringe_pixels.add(i)
tracing=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
layer(tracing,'Face_visible_only_UNDERPAINT_REQUIRED',face)
for name,rgba in fringe_parts.items():layer(tracing,name,rgba)
assert composite(tracing)==reference
trace_checks={}
for suffix,proc in [('xcf','gimp-xcf-save'),('psd','file-psd-export')]:
    target=OUT/f'forelock-tracing.{suffix}'
    run_proc(proc,image=tracing,file=Gio.File.new_for_path(str(target)))
    loaded=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(target)))
    assert composite(loaded)==reference
    expected={'Face_visible_only_UNDERPAINT_REQUIRED':bytes(face),**{k:bytes(v) for k,v in fringe_parts.items()}}
    assert {l.get_name():pixels(l) for l in loaded.get_layers()}==expected
    trace_checks[suffix]=dict(neutral_equal=True,all_parts_equal=True)
    loaded.delete()
tracing.delete()
trace_board=Gimp.Image.new(W*4,H,Gimp.ImageBaseType.RGB)
layer(trace_board,'Source',reference)
for col,(name,rgba) in enumerate(fringe_parts.items(),1):
    visible=bytearray([65,65,65,255]*(W*H))
    for i in range(0,len(visible),4):
        if rgba[i+3]:visible[i:i+4]=rgba[i:i+4]
    layer(trace_board,name,visible,col*W,0)
run_proc('file-png-export',image=trace_board,file=Gio.File.new_for_path(str(OUT/'forelock-tracing.png')))
trace_board.delete()
editable=set().union(*(item['domain'] for item in data.values()))-stationary_fold_indices
hair_layer=bytearray(W*H*4);edit_layer=bytearray(W*H*4);fixed_layer=bytearray(W*H*4)
for i in hair_indices:hair_layer[i:i+4]=bytes((0,230,100,210))
for i in editable-hair_indices:edit_layer[i:i+4]=bytes((235,35,165,90))
for i in stationary_fold_indices:fixed_layer[i:i+4]=bytes((255,190,0,170))
doc=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
layer(doc,'Reference_open',reference)
layer(doc,'Reference_closed',closed).set_visible(False)
layer(doc,'Editable_region_magenta',edit_layer)
layer(doc,'Stationary_contours_yellow',fixed_layer)
layer(doc,'Registered_hair_green',hair_layer)
for item in doc.get_layers():
    item.set_blend_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
    item.set_composite_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
overlay=composite(doc)
run_proc('gimp-xcf-save',image=doc,file=Gio.File.new_for_path(str(OUT/'hair-ownership.xcf')))
doc.delete()
board=Gimp.Image.new(W*4,H,Gimp.ImageBaseType.RGB)
layer(board,'Open',reference,0,0)
layer(board,'Closed',closed,W,0)
layer(board,'Ownership_overlay',overlay,W*2,0)
# Show the actual source-alpha material over dark grey, exposing fragmented tips.
matte=bytearray([65,65,65,255]*(W*H))
for i in hair_indices:
    a=hair_matte[i+3]/255
    matte[i:i+3]=bytes(round(hair_matte[i+c]*a+65*(1-a)) for c in range(3))
layer(board,'Existing_hair_on_grey',matte,W*3,0)
run_proc('file-png-export',image=board,file=Gio.File.new_for_path(str(OUT/'inspection.png')))
board.delete()
report=dict(status='diagnostic_only_not_accepted_hair_separation',
    columns=['source open','current closed','magenta editable / yellow stationary / green registered hair','existing hair alpha on grey'],
    source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    atlas_sha256=hashlib.sha256(atlas.read_bytes()).hexdigest(),
    registered_hair_pixels=len(hair_indices),editable_nonhair_pixels=len(editable-hair_indices),
    stationary_pixels=len(stationary_fold_indices),neutral_equal=True,
    forelock_tracing=dict(status='manual_contour_scaffold_requires_review',
        roundtrip=trace_checks,layer_count=4,foreground_pixels=len(fringe_pixels),
        hidden_face_filled=False,alpha_refined=False,movement_ready=False,
        note='Exact partition is a file check, not proof of correct hair anatomy. Crop excludes roots.'),
    limitations=['Masks describe implementation ownership, not ground-truth anatomy',
                'Existing foreground is a fragmentary holdout, not a complete movable forelock',
                'Hair-tip completeness and skin-boundary appearance require visual review'])
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('HAIR_SEPARATION_INSPECTION_READY',flush=True)
