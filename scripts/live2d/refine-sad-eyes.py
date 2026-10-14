"""Replace the first sad eye deformation and add matched iris/highlight keys."""
from pathlib import Path
import sys,importlib.util
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import cmo3_tool as t
from sad_eye_shapes import eye_delta
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib);named=lib.named
doc=t.Cmo3(sys.argv[1])
for side in 'LR':
    for part in ('Sclera','LidSkin_Upper','LidSkin_Lower','LashUpper','LashLower','Crease','Iris','Highlight'):
        e=lib.lib.Editor(doc);mesh=e.meshes[f'Eye_{side}_{part}'];fresh=part in ('Iris','Highlight')
        if fresh:
            old=[float(named(f,'f','opacity').text) for f in named(mesh,'carray_list','keyforms')]
            e.opacity_binding(f'Eye_{side}_{part}','ParamSad',True);mesh=e.meshes[f'Eye_{side}_{part}']
        sad=lib.form_parameter(e,mesh,'ParamSad');opening=lib.form_parameter(e,mesh,f'ParamEye{side}Open');smile=lib.form_parameter(e,mesh,f'ParamEye{side}Smile')
        info=lib.parent_info(e,doc,mesh);W=info['x1']-info['x0'];H=info['y1']-info['y0']
        for i,f in enumerate(named(mesh,'carray_list','keyforms')):
            if fresh:named(f,'f','opacity').text=str(old[i%len(old)])
            guid=named(f,'CFormGuid','guid').get('xs.ref');op=opening.get(guid,1)
            if sad.get(guid,0)<.99 or not op or smile.get(guid,0):continue
            pos=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2)
            absolute=pos*[W,H]+[info['x0'],info['y0']]
            if not fresh:
                cx=1285 if side=='L' else 920;u=np.clip((absolute[:,0]-cx)/145,-1,1)
                upper=40*(1-u*u);lower=-10*(1-.5*u*u)
                if part in ('LashUpper','LidSkin_Upper','Crease'):previous=upper
                elif part in ('LashLower','LidSkin_Lower'):previous=lower
                else:
                    # Undo y interpolation exactly, before applying the new curve.
                    original_y=(absolute[:,1]-op*upper+op*(lower-upper)*985/145)/(1+op*(lower-upper)/145)
                    original_y=np.where(absolute[:,1]<985+op*upper,absolute[:,1]-op*upper,original_y)
                    original_y=np.where(absolute[:,1]>1130+op*lower,absolute[:,1]-op*lower,original_y)
                    previous=(absolute[:,1]-original_y)/op
                pos[:,1]-=previous*op/H;absolute=pos*[W,H]+[info['x0'],info['y0']]
            pos[:,1]+=eye_delta(side,part,absolute)*op/H;named(f,'float-array','positions').text=lib.lib.array(pos)
        e.flush()
doc.save(sys.argv[2]);print('SAD_EYES_REFINED')
