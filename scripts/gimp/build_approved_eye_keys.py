"""Register approved eye artwork with GIMP; endpoint study, not a finished rig."""
import os
from pathlib import Path
ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
exec((ROOT/'scripts/gimp/build_face_remake.py').read_text(encoding='utf-8').split('normal=render(0,0)')[0])
OUT = ROOT/'assets/private/ciel/live2d/gimp/approved-eye-keys-v1'
OUT.mkdir(parents=True, exist_ok=True)
approved = ROOT/'docs/assets/ciel/production/ciel-eye-appearance-study-v1.png'
src = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(approved)))
sw, sh = src.get_width(), src.get_height()
assert (sw, sh) == (2172,724)
buf = bytes(src.get_layers()[0].get_buffer().get(Gegl.Rectangle.new(0,0,sw,sh),1.0,FMT,Gegl.AbyssPolicy.NONE))
def read(x,y):
    x=max(0,min(sw-2,x)); y=max(0,min(sh-2,y))
    ix,iy=int(x),int(y); fx,fy=x-ix,y-iy
    return [sum(buf[4*((iy+dy)*sw+ix+dx)+c]*wx*wy
                for dx,wx in ((0,1-fx),(1,fx)) for dy,wy in ((0,1-fy),(1,fy))) for c in range(3)]
board = Gimp.Image.new(W*3,H,Gimp.ImageBaseType.RGB)
study = Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
layer(study,'Approved_original_normal',reference)
layer(board,'Normal',reference)
checks=[]
domain=set().union(*(v['domain'] for v in data.values()))
for col,name in ((1,'Near_closed'),(2,'Closed')):
    rgba=bytearray(reference)
    endpoint=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
    layer(endpoint,'Original_context',reference)
    for side,item in data.items():
        patch=bytearray(W*H*4)
        a,b=item['g']['x']; sx=164 if side=='R' else 402
        for i in item['domain']:
            x,y=(i//4)%W,(i//4)//W
            rgb=read(col*724+sx+(x-a)*1.9,320+(y-52)*1.9)
            # The reference sheet's fringe is not pixel-registered. Do not
            # transfer its hair fragments with the eyelid appearance patch.
            blend=max(0,min(1,(y-70)/7))
            blend=blend*blend*(3-2*blend)
            rgb=[rgb[c]*blend+item['buffers']['Skin_Backfill'][i+c]*(1-blend) for c in range(3)]
            if i in hair_indices:
                if hair_matte is None: rgb=list(reference[i:i+3])
                else:
                    alpha=hair_matte[i+3]/255
                    rgb=[hair_matte[i+c]*alpha+rgb[c]*(1-alpha) for c in range(3)]
            rgba[i:i+4]=bytes([round(v) for v in rgb]+[255])
            patch[i:i+4]=rgba[i:i+4]
        layer(endpoint,f'{side}_{name}_appearance_patch_NOT_rig_part',patch)
    run_proc('gimp-xcf-save',image=endpoint,file=Gio.File.new_for_path(str(OUT/f'{name.lower()}-registration.xcf')))
    run_proc('file-psd-export',image=endpoint,file=Gio.File.new_for_path(str(OUT/f'{name.lower()}-registration.psd')))
    endpoint.delete()
    png(name.lower(),rgba)
    layer(board,name,rgba,col*W,0)
    layer(study,name,rgba).set_visible(False)
    outside=sum(rgba[i:i+4]!=reference[i:i+4] for i in range(0,len(rgba),4) if i not in domain)
    hair=sum(rgba[i:i+4]!=reference[i:i+4] for i in opaque_hair_indices)
    assert outside==hair==0
    checks.append(dict(pose=name,outside_eye_changed_pixels=outside,opaque_hair_changed_pixels=hair))
run_proc('file-png-export',image=board,file=Gio.File.new_for_path(str(OUT/'comparison.png')))
run_proc('gimp-xcf-save',image=study,file=Gio.File.new_for_path(str(OUT/'registered-poses.xcf')))
board.delete();study.delete();src.delete()
(OUT/'report.json').write_text(json.dumps(dict(status='registration_candidate_not_rig_ready',
    approved_reference=approved.relative_to(ROOT).as_posix(),
    approved_sha256=hashlib.sha256(approved.read_bytes()).hexdigest(),
    normal_source=SOURCE.relative_to(ROOT).as_posix(),
    columns=['original normal','near closed reference (not calibrated 0.5)','closed'],
    checks=checks,limitations=['Manual landmark registration requires visual review',
    'Appearance patches include skin and lashes; not independently deformable parts',
    '280x195 output is a registration study; retain approved full resolution master',
    'No intermediate motion, Cubism import or Unity validation']),indent=2)+'\n',encoding='utf-8')
print('APPROVED_EYE_KEYS_READY',flush=True)
