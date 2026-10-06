"""Prepare 22 moving parts with estimated hair alpha and anatomical sclera limits."""
from pathlib import Path
import os,json,hashlib
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
source=ROOT/'scripts/gimp/build_face_remake.py'
exec(source.read_text(encoding='utf-8').split('normal=render(0,0)')[0])
SOFT_MASK=os.environ.get('CIEL_CUBISM_SOFT_MASK')=='1'
OUT=ROOT/('assets/private/ciel/live2d/gimp/cubism-eye-material-v6' if SOFT_MASK else
          'assets/private/ciel/live2d/gimp/cubism-eye-material-v5')
OUT.mkdir(parents=True,exist_ok=True)
prepared={name:bytearray(rgba) for name,rgba in parts.items()}
changes={}
for side,item in data.items():
    g=item['g']; fill=prepared[f'{side}_Sclera_Hidden']
    cleared=0; mask_overlap=0; soft_boundary=0
    for i in item['domain']:
        x,y=(i//4)%W,(i//4)//W
        coverage=(sum(curve(g['upper'],x+sx)<=y+sy<=curve(g['lower'],x+sx)
            for sx in [.125,.375,.625,.875] for sy in [.125,.375,.625,.875])/16
            if SOFT_MASK else float(curve(g['upper'],x+.5)<=y+.5<=curve(g['lower'],x+.5)))
        in_aperture=coverage>0
        # A complementary cutout for the visible sclera creates internal mask
        # edges at the iris perimeter. Fill beneath the visible sclera too so
        # the hidden sclera provides one continuous clipping surface.
        if in_aperture and i not in hair_indices and item['buffers']['Sclera'][i+3]:
            fill[i:i+4]=item['sclera'][i:i+4];mask_overlap+=1
        if not in_aperture or i in hair_indices:
            if fill[i+3]:cleared+=1
            fill[i:i+4]=bytes(4)
        else:
            fill[i:i+4]=item['sclera'][i:i+4]
            fill[i+3]=round(255*coverage)
            if 0<fill[i+3]<255:soft_boundary+=1
    prepared[f'{side}_UpperLash']=bytearray(item['lash_motion'])
    for i in item['domain'] & hair_indices:
        prepared[f'{side}_Iris_Hidden'][i:i+4]=bytes(4)
    # A hole beneath the pupil/highlight exposes the sclera when adjacent
    # ArtMeshes are filtered independently. Paint iris color below those parts;
    # do not bake a second pupil or highlight into the iris.
    iris=prepared[f'{side}_Iris']
    pupil=prepared[f'{side}_Pupil']; highlight=prepared[f'{side}_Highlight']
    known=[i for i in item['domain'] if iris[i+3]]
    covered=[i for i in item['domain'] if pupil[i+3] or highlight[i+3]]
    assert known
    for i in covered:
        x,y=(i//4)%W,(i//4)//W
        neighbors=sorted(known,key=lambda j:((j//4)%W-x)**2+2*((j//4)//W-y)**2)[:8]
        iris[i:i+4]=bytes([round(sum(iris[j+c] for j in neighbors)/len(neighbors)) for c in range(3)]+[255])
    assert all(iris[i+3]==255 for i in covered)
    changes[side]=dict(hidden_sclera_pixels_cleared=cleared,
        continuous_sclera_overlap_pixels=mask_overlap,
        antialiased_sclera_boundary_pixels=soft_boundary,
        iris_underpaint_pixels=len(covered),pupil_and_highlight_have_opaque_underpaint=True)
prepared['Hair_Foreground']=bytearray(hair_matte)

# UpperFold was a catch-all strip above the lash, including stationary skin,
# crease and hair contours. Preserve its upper region in the fixed Context.
# The 1.5px strip nearest the traced lash remains in UpperFold pending a finer
# lash-edge trace. Use geometry, not brightness, to assign anatomical ownership.
for side,item in data.items():
    changes[side]['stationary_fold_pixels_moved_to_context']=stationary_fold_by_side[side]

# Estimate coverage only on visible iris perimeter pixels backed by clean
# sclera. Keep the original neutral composite exactly, including quantization.
for side in data:
    name=f'{side}_Iris'; iris=prepared[name]
    background_doc=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
    for part,rgba in prepared.items():
        if part==name:continue
        l=layer(background_doc,part,rgba)
        l.set_blend_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
        l.set_composite_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
    background=composite(background_doc);background_doc.delete()
    opaque={i for i in range(0,len(iris),4) if iris[i+3]==255}
    neighbors=lambda i:[i-4,i+4,i-W*4,i+W*4]
    interior=[i for i in opaque if all(j in opaque for j in neighbors(i))]
    modified=[]
    for i in sorted(opaque):
        if not parts[name][i+3] or all(j in opaque for j in neighbors(i)):continue
        b=list(background[i:i+3]);c=list(reference[i:i+3])
        if min(b)<175 or max(b)-min(b)>40:continue
        x,y=(i//4)%W,(i//4)//W
        nearby=sorted(interior,key=lambda j:((j//4)%W-x)**2+((j//4)//W-y)**2)[:4]
        if not nearby:continue
        f=[sum(iris[j+k] for j in nearby)/len(nearby) for k in range(3)]
        delta=[f[k]-b[k] for k in range(3)];den=sum(v*v for v in delta)
        a=sum((c[k]-b[k])*delta[k] for k in range(3))/den if den>2500 else 1
        for aa in range(max(64,min(255,round(a*255))),256):
            alpha=aa/255;ff=[round((c[k]-b[k]*(1-alpha))/alpha) for k in range(3)]
            if all(0<=v<=255 for v in ff) and all(round(ff[k]*alpha+b[k]*(1-alpha))==c[k] for k in range(3)):
                iris[i:i+4]=bytes(ff+[aa])
                if aa<255:modified.append(dict(pixel=[x,y],alpha=aa))
                break
    changes[side]['estimated_iris_perimeter']=modified
doc=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
for name,rgba in prepared.items():
    item=layer(doc,name,rgba)
    item.set_blend_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
    item.set_composite_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
actual=composite(doc)
diff=sum(actual[i:i+4]!=reference[i:i+4] for i in range(0,len(reference),4))
png('neutral',actual)
png('fold-half-fixed-context',render(0,.5))
print('CUBISM_HAIR_NEUTRAL_DIFF',diff,flush=True)
assert diff==0, 'New moving-part composite must preserve neutral exactly'
roundtrip={}
for suffix,proc in [('xcf','gimp-xcf-save'),('psd','file-psd-export')]:
    path=OUT/f'semantic-hair-parts.{suffix}'
    run_proc(proc,image=doc,file=Gio.File.new_for_path(str(path)))
    loaded=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(path)))
    same=composite(loaded)==reference
    layers={item.get_name():pixels(item) for item in loaded.get_layers()}
    assert same and layers=={n:bytes(v) for n,v in prepared.items()}
    roundtrip[suffix]=dict(neutral_equal=same,all_parts_equal=True,layer_count=len(layers))
    loaded.delete()
doc.delete()
for name in ['Hair_Foreground','L_UpperLash','L_Sclera_Hidden','R_UpperLash','R_Sclera_Hidden','L_Iris','R_Iris']:
    png(name,prepared[name])
report=dict(status='material_candidate_cubism_import_pending',neutral_changed_pixels=diff,
    neutral_rgba_sha256=hashlib.sha256(reference).hexdigest(),roundtrip=roundtrip,changes=changes,
    estimated_hair_pixels=len(translucent_hair_indices),
    psd_sha256=hashlib.sha256((OUT/'semantic-hair-parts.psd').read_bytes()).hexdigest(),
    limits=['Hair and iris alpha are estimates, not original source alpha','Neutral GIMP equality does not prove Cubism blend equality','Existing meshes may need regeneration after aperture changes','Movement and hair occlusion in Cubism not yet verified'])
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('CUBISM_HAIR_MATERIAL_READY',flush=True)
