"""Three-pose left-eye material study; not an exported Cubism rig."""
import os
from pathlib import Path
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
exec((ROOT/'scripts/gimp/build_face_remake.py').read_text(encoding='utf-8').split('normal=render(0,0)')[0])
OUT=ROOT/'assets/private/ciel/live2d/gimp/single-eye-redesign-v1'
OUT.mkdir(parents=True,exist_ok=True)
poses={}
checks=[]
board=Gimp.Image.new(W*3,H*2,Gimp.ImageBaseType.RGB)
keys=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
for col,closure in enumerate((0,.5,1)):
    for row,method in enumerate(('previous','candidate')):
        rendered=render(0,closure,refined_lid_side='L' if row else None)
        one=bytearray(reference)
        for i in data['L']['domain']:
            one[i:i+4]=rendered[i:i+4]
        one=bytes(one)
        layer(board,f'{method}_{closure}',one,col*W,row*H)
        if row:
            poses[closure]=one
            layer(keys,f'Left_eye_closure_{closure}',one).set_visible(closure==0)
            png(f'left-eye-{col}',one)
            outside=sum(one[i:i+4]!=reference[i:i+4] for i in range(0,len(reference),4)
                        if i not in data['L']['domain'])
            hair=sum(one[i:i+4]!=reference[i:i+4] for i in opaque_hair_indices)
            assert outside==hair==0
            checks.append(dict(closure=closure,outside_left_eye_changes=outside,opaque_hair_changes=hair))
assert poses[0]==reference
for dx in (-4,4):
    assert render(dx,1,refined_lid_side='L')==render(0,1,refined_lid_side='L')
run_proc('file-png-export',image=board,file=Gio.File.new_for_path(str(OUT/'comparison.png')))
run_proc('gimp-xcf-save',image=keys,file=Gio.File.new_for_path(str(OUT/'pose-study.xcf')))
board.delete();keys.delete()
# A separate source contour for a Cubism trial. Keep it visible in this import
# PSD; the rig must set opacity to zero at the approved neutral/closed keys.
g=data['L']['g']
contour=bytearray(W*H*4)
for y in range(H):
    for x in range(g['x'][0],g['x'][1]+1):
        coverage=0
        for sx in (.125,.375,.625,.875):
            xx=x+sx
            t=max(0,min(1,(xx-g['x'][0])/(g['x'][1]-g['x'][0])))
            width=.7*math.sin(math.pi*t)**.6
            lower=curve(g['lower'],xx)
            coverage+=sum(abs(y+sy-lower)<width/2 for sy in (.125,.375,.625,.875))/16
        if coverage:
            i=4*(y*W+x)
            contour[i:i+4]=bytes((105,119,145,round(coverage*255)))
material=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
layer(material,'L_LowerContour',contour)
run_proc('file-psd-export',image=material,file=Gio.File.new_for_path(str(OUT/'lower-contour-import.psd')))
material.delete()
png('lower-contour',contour)
(OUT/'report.json').write_text(json.dumps(dict(
    status='candidate_visual_review_pending_not_cubism_material',
    rows=['previous software rendering','redesigned aperture and independent lower contour'],
    columns=['normal','half closed','closed'],side='L (screen right)',
    source=str(SOURCE.relative_to(ROOT)),neutral_equal=True,checks=checks,
    source_contour=dict(file='lower-contour-import.psd',name='L_LowerContour',
        nontransparent_pixels=sum(contour[i]>0 for i in range(3,len(contour),4)),
        parent_plan='L_EyeOpening',opacity_plan={'open':0,'half':70,'closed':0},
        note='Import candidate only; match actual deformed edge before adoption'),
    limitations=['Same 280x195 source crop; no new illustration detail',
                 'Closed pose retains the existing procedural upper lash',
                 'XCF contains comparison poses, not rig-ready separated parts',
                 'Cubism and Unity appearance not validated']),indent=2)+'\n',encoding='utf-8')
print('SINGLE_EYE_REDESIGN_READY',flush=True)
