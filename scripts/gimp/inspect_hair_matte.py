"""GIMP-only comparison of estimated hair alpha; does not replace production PSD.

The flattened reference cannot identify true foreground alpha. This candidate
uses the reconstructed neutral underpainting and a pale-hair prior, and retains
opaque pixels where the two colors are too similar to constrain an estimate.
"""
from pathlib import Path
import os

source = Path(os.environ['CIEL_PROJECT_ROOT']) / 'scripts/gimp/build_face_remake.py'
exec(source.read_text(encoding='utf-8').split('\nnormal=render(0,0)')[0])
OUT = ROOT / 'assets/private/ciel/live2d/gimp/hair-matte-study'
OUT.mkdir(parents=True, exist_ok=True)
base = render(0, 0, include_foreground=False)
matte = bytearray(W*H*4)
estimated = []
for i in sorted(hair_indices):
    c = reference[i:i+3]
    b = base[i:i+3]
    # A local bright strand sample is a color prior, not an alpha measurement.
    x,y = (i//4)%W,(i//4)//W
    neighbors = [j for j in hair_indices
                 if abs((j//4)%W-x)<=4 and abs((j//4)//W-y)<=6
                 and min(reference[j:j+3])>225]
    f = [sum(reference[j+k] for j in neighbors)/len(neighbors)
         for k in range(3)] if neighbors else [245,247,253]
    delta = [f[k]-b[k] for k in range(3)]
    denominator = sum(v*v for v in delta)
    a = sum((c[k]-b[k])*delta[k] for k in range(3))/denominator if denominator>2500 else 1
    # Search upward for an 8-bit matte that reconstructs all neutral channels
    # exactly under the same straight-alpha, encoded-RGB compositing equation.
    found = None
    for aa in range(max(1,min(255,round(a*255))),256):
        alpha = aa/255
        ff = [round((c[k]-b[k]*(1-alpha))/alpha) for k in range(3)]
        if all(0<=v<=255 for v in ff) and all(
                round(ff[k]*alpha+b[k]*(1-alpha))==c[k] for k in range(3)):
            found = bytes(ff+[aa]);break
    assert found is not None
    matte[i:i+4] = found
    if found[3]<255:estimated.append(i)

def candidate(dx,closure):
    result=bytearray(render(dx,closure,include_foreground=False))
    for i in hair_indices:
        a=matte[i+3]/255
        result[i:i+3]=bytes(round(matte[i+k]*a+result[i+k]*(1-a)) for k in range(3))
    return bytes(result)

def opaque_cutout(dx,closure):
    result=bytearray(render(dx,closure,include_foreground=False))
    for i in hair_indices:result[i:i+4]=reference[i:i+4]
    return bytes(result)

assert candidate(0,0)==reference
# Compare against the published version before promoting any renderer change.
baseline=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(
    ROOT/'docs/assets/ciel/production/ciel-face-remake-v2-comparison.png')))
baseline_pixels=bytes(baseline.get_layers()[0].get_buffer().get(
    Gegl.Rectangle.new(0,0,W*5,H*3),1.0,FMT,Gegl.AbyssPolicy.NONE))
baseline.delete()
baseline_checks=0
baseline_changes=[]
for row,dx in enumerate([-4,0,4]):
    for col,closure in enumerate([0,.25,.5,.75,1]):
        frame=render(dx,closure)
        changed_pixels=0
        for y in range(H):
            offset=4*((row*H+y)*W*5+col*W)
            old=baseline_pixels[offset:offset+W*4]
            new=frame[y*W*4:(y+1)*W*4]
            changed_pixels+=sum(old[j:j+4]!=new[j:j+4] for j in range(0,W*4,4))
        baseline_changes.append(dict(gaze=dx,closure=closure,changed_pixels=changed_pixels))
        baseline_checks+=1
png('estimated-hair',matte)
# Keep the candidate editable and verify GIMP/PSD compositing, not only the
# Python compositing equation. This two-layer diagnostic is not a rigging PSD.
material=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
layer(material,'Neutral_Underpainting',base)
foreground=layer(material,'Hair_EstimatedAlpha',matte)
foreground.set_blend_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
foreground.set_composite_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
def comparison_metrics(actual,expected):
    return dict(changed_pixels=sum(actual[i:i+4]!=expected[i:i+4] for i in range(0,len(expected),4)),
                max_channel_delta=max(abs(a-b) for a,b in zip(actual,expected)))
material_composite=composite(material)
assert material_composite==reference, 'GIMP hair composite changed the neutral face'
material_roundtrip={}
for suffix,procedure in [('xcf','gimp-xcf-save'),('psd','file-psd-export')]:
    path=OUT/('hair-matte-material.'+suffix)
    run_proc(procedure,image=material,file=Gio.File.new_for_path(str(path)))
    loaded=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(path)))
    loaded_parts={item.get_name():pixels(item) for item in loaded.get_layers()}
    actual=composite(loaded)
    material_roundtrip[suffix]=dict(
        layers_equal=loaded_parts=={'Neutral_Underpainting':bytes(base),'Hair_EstimatedAlpha':bytes(matte)},
        composite_equal_to_gimp=actual==material_composite,
        reference_difference=comparison_metrics(actual,reference))
    assert material_roundtrip[suffix]['layers_equal'] and actual==reference, suffix+' hair material roundtrip changed'
    loaded.delete()
material.delete()
doc=Gimp.Image.new(W*5,H*2,Gimp.ImageBaseType.RGB)
for row,fn in enumerate([opaque_cutout,candidate]):
    for col,closure in enumerate([0,.25,.5,.75,1]):
        layer(doc,f'{row}-{closure}',fn(0,closure),col*W,row*H)
run_proc('file-png-export',image=doc,file=Gio.File.new_for_path(str(OUT/'comparison.png')))
# Enlarge the same half-closed crop in each row for an honest boundary review.
detail=doc.duplicate()
detail.crop(W,H*2,W*2,0)
detail.scale(W*3,H*6)
run_proc('file-png-export',image=detail,file=Gio.File.new_for_path(str(OUT/'half-close-detail.png')))
detail.delete()
doc.delete()
doc=Gimp.Image.new(W*3,H,Gimp.ImageBaseType.RGB)
for col,color in enumerate([(25,25,35),(128,128,128),(245,245,250)]):
    backdrop=bytes(list(color)+[255])*(W*H)
    layer(doc,f'background-{col}',backdrop,col*W,0)
    layer(doc,f'hair-{col}',matte,col*W,0)
run_proc('file-png-export',image=doc,file=Gio.File.new_for_path(str(OUT/'backgrounds.png')))
doc.delete()
report=dict(status='candidate_not_approved',neutral_equal=True,
    editable_material=dict(layer_count=2,composite_space='RGB_NON_LINEAR',
        reference_difference=comparison_metrics(material_composite,reference),roundtrip=material_roundtrip),
    baseline_frames_checked=baseline_checks,baseline_changes=baseline_changes,
    foreground_pixels=len(hair_indices),estimated_translucent_pixels=len(estimated),
    alpha_range=[min(matte[i+3] for i in estimated),max(matte[i+3] for i in estimated)] if estimated else None,
    limits=['Estimated alpha, not recovered original alpha',
            'Only existing traced foreground pixels are covered',
            'Encoded RGB compositing; Cubism pixel equivalence is not checked by this script',
            'Estimated hair alpha is integrated into the preview, but not the existing Cubism expression rig'])
(OUT/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('HAIR_MATTE_STUDY_READY',json.dumps(report),flush=True)
