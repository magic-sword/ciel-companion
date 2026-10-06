"""Build editable cropped fringe and hidden-face underpaint in GIMP 3.

Preserves source compositing; alpha and hidden colors are estimates. This is
material preparation, not approved anatomy or a moving Cubism model.
"""
import os,json,hashlib
from pathlib import Path
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
exec((ROOT/'scripts/gimp/eye_material_core.py').read_text(encoding='utf-8'))
OUT=ROOT/'assets/private/ciel/live2d/gimp/forelock-materials'
OUT.mkdir(parents=True,exist_ok=True)
# A polygon can represent overhanging tips; y=f(x) cannot. Keep this contour
# explicit so the artist can refine ownership without brightness thresholds.
edge=[(0,83),(18,74),(30,63),(39,76),(48,63),(61,54),(73,50),
    (83,51),(95,56),(105,64),(111,70),(120,77),(117,67),
    (128,76),(135,79),(129,68),(141,76),(150,78),(150,61),
    (155,77),(157,65),(160,75),(164,59),(168,72),
    (172,61),(181,54),(188,49),(198,47),(205,48),(216,50),(222,54),
    (230,61),(236,68),(240,72),(250,57),(265,67),(280,79)]
polygon=[(0,0),(280,0)]+list(reversed(edge))
coverage={}
for y in range(84):
    for x in range(W):
        n=sum(inside(x+sx,y+sy,polygon) for sx in (.125,.375,.625,.875) for sy in (.125,.375,.625,.875))
        i=4*(y*W+x)
        if n:coverage[i]=n/16
# Keep existing traced crossing strands too, pending a full contour review.
for i in hair_indices:coverage[i]=max(coverage.get(i,0),hair_matte[i+3]/255)

# Explicit clean-cheek samples, outside eyes/hair/mouth. Interpolate rather
# than filling the entire hidden forehead with one flat sampled color.
anchors=[]
for cx,cy in [(78,119),(107,123),(144,115),(173,124),(202,118)]:
    colors=[reference[4*(y*W+x):4*(y*W+x)+3]
            for y in range(cy-2,cy+3) for x in range(cx-2,cx+3)]
    anchors.append((cx,cy,[sum(c[k] for c in colors)/len(colors) for k in range(3)]))
underpaint=bytearray(reference)
hair={name:bytearray(W*H*4) for name in ('Hair_R','Hair_Center','Hair_L')}
refined=[];promoted=[]
for i,a in coverage.items():
    x,y=(i//4)%W,(i//4)//W
    weights=[1/(16+(x-cx)**2+.1*(y-cy)**2) for cx,cy,c in anchors]
    bg=[round(sum(w*c[k] for w,(_,_,c) in zip(weights,anchors))/sum(weights)) for k in range(3)]
    underpaint[i:i+4]=bytes(bg+[255])
    # Unmatte the source against the estimated underpaint in encoded RGB.
    # Increase alpha only as far as needed to represent valid 8-bit colors and
    # recover exactly the approved source when these parts are composited.
    start=max(1,round(a*255))
    for aa in range(start,256):
        alpha=aa/255
        color=[round((reference[i+k]-bg[k]*(1-alpha))/alpha) for k in range(3)]
        if all(0<=v<=255 for v in color) and all(round(color[k]*alpha+bg[k]*(1-alpha))==reference[i+k] for k in range(3)):
            break
    name='Hair_R' if x<111 else 'Hair_Center' if x<168 else 'Hair_L'
    hair[name][i:i+4]=bytes(color+[aa])
    if aa<255:refined.append([x,y,aa])
    if aa>start:promoted.append([x,y,start,aa])
doc=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
layer(doc,'Face_hidden_underpaint_ESTIMATED',underpaint)
for name,rgba in hair.items():layer(doc,name,rgba)
for item in doc.get_layers():
    item.set_blend_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
    item.set_composite_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
assert composite(doc)==reference
expected={'Face_hidden_underpaint_ESTIMATED':bytes(underpaint),**{k:bytes(v) for k,v in hair.items()}}
checks={}
for suffix,proc in [('xcf','gimp-xcf-save'),('psd','file-psd-export')]:
    path=OUT/f'forelock-materials.{suffix}'
    run_proc(proc,image=doc,file=Gio.File.new_for_path(str(path)))
    loaded=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(path)))
    assert composite(loaded)==reference
    assert {l.get_name():pixels(l) for l in loaded.get_layers()}==expected
    checks[suffix]=dict(normal_equal=True,all_parts_equal=True)
    loaded.delete()
doc.delete()
assert all(underpaint[i]==255 for i in range(3,len(underpaint),4))

# Four columns: original, hidden face, isolated forelock on white and grey.
board=Gimp.Image.new(W*4,H,Gimp.ImageBaseType.RGB)
layer(board,'Original',reference)
layer(board,'Underpaint',underpaint,W,0)
for col,background in [(2,255),(3,65)]:
    rendered=bytearray([background,background,background,255]*(W*H))
    for rgba in hair.values():
        for i in coverage:
            a=rgba[i+3]/255
            rendered[i:i+3]=bytes(round(rgba[i+k]*a+rendered[i+k]*(1-a)) for k in range(3))
    layer(board,f'Forelock_background_{background}',rendered,col*W,0)
run_proc('file-png-export',image=board,file=Gio.File.new_for_path(str(OUT/'comparison.png')))
board.delete()
report=dict(status='editable_material_candidate_not_accepted_for_motion',
    source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    generator_sha256=hashlib.sha256((ROOT/'scripts/gimp/build_forelock_materials.py').read_bytes()).hexdigest(),
    dimensions=[W,H],layer_count=4,roundtrip=checks,
    hidden_face_opaque=True,covered_pixels=len(coverage),
    semitransparent_pixels=refined,alpha_increased_for_color_reconstruction=promoted,
    underpaint_sample_centers=[[x,y] for x,y,c in anchors],
    next_work=['Review every tip and internal seam against source',
               'Refine skin appearance and closed-eye transition with hair hidden',
               'Extend cropped parts to roots before rigging'],
    limitations=['Hidden face color is inferred, not recovered original artwork',
                 'Alpha is geometrically estimated, not ground-truth hair coverage',
                 'Exact neutral composite does not prove anatomical separation',
                 'No blink integration or hair movement yet'])
# Evaluate the closed endpoint with the same hidden-face color field. The
# approved closed lashes remain separate and keep their existing pixels.
closed_source=ROOT/'assets/private/ciel/live2d/gimp/approved-eye-motion-v1/closed-materials.psd'
if closed_source.exists():
    closed_doc=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(closed_source)))
    lashes={l.get_name():pixels(l) for l in closed_doc.get_layers() if '_Closed_lash' in l.get_name()}
    assert len(lashes)==2
    closed_doc.delete()
    skin_layers={}
    for side,item in data.items():
        rgba=bytearray(W*H*4)
        for i in item['domain']:
            x,y=(i//4)%W,(i//4)//W
            weights=[1/(16+(x-cx)**2+.1*(y-cy)**2) for cx,cy,c in anchors]
            bg=[round(sum(w*c[k] for w,(_,_,c) in zip(weights,anchors))/sum(weights)) for k in range(3)]
            rgba[i:i+4]=bytes(bg+[255])
        skin_layers[f'{side}_Closed_skin_ESTIMATED']=rgba
    endpoint=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
    layer(endpoint,'Face_hidden_underpaint_ESTIMATED',underpaint)
    for name,rgba in {**skin_layers,**lashes,**hair}.items():layer(endpoint,name,rgba)
    for item in endpoint.get_layers():
        item.set_blend_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
        item.set_composite_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
    endpoint_rgba=composite(endpoint)
    endpoint_parts={l.get_name():pixels(l) for l in endpoint.get_layers()}
    for suffix,proc in [('xcf','gimp-xcf-save'),('psd','file-psd-export')]:
        target=OUT/f'closed-endpoint.{suffix}'
        run_proc(proc,image=endpoint,file=Gio.File.new_for_path(str(target)))
        reloaded=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(target)))
        assert composite(reloaded)==endpoint_rgba
        assert {l.get_name():pixels(l) for l in reloaded.get_layers()}==endpoint_parts
        reloaded.delete()
    endpoint.delete()
    atlas=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(ROOT/'docs/assets/ciel/production/ciel-approved-eye-motion-v1-blink-atlas.png')))
    previous=bytes(atlas.get_layers()[0].get_buffer().get(Gegl.Rectangle.new(W*8,H*32,W,H),1,FMT,Gegl.AbyssPolicy.NONE))
    atlas.delete()
    comparison=Gimp.Image.new(W*3,H,Gimp.ImageBaseType.RGB)
    for col,(name,rgba) in enumerate([('Original',reference),('Current_closed',previous),('Underpaint_candidate',endpoint_rgba)]):
        layer(comparison,name,rgba,col*W,0)
    run_proc('file-png-export',image=comparison,file=Gio.File.new_for_path(str(OUT/'closed-comparison.png')))
    comparison.delete()
    report['closed_endpoint']=dict(status='visual_candidate_not_integrated',layer_count=len(endpoint_parts),
        psd_xcf_composite_and_parts_equal=True,
        source_lashes_sha256=hashlib.sha256(closed_source.read_bytes()).hexdigest(),
        blink_intermediates_verified=False)
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('FORELOCK_MATERIALS_READY',flush=True)
