"""Raise lower-lid center only for ParamRelaxed, retaining upper/blink rest keys."""
from pathlib import Path
import sys,importlib.util,shutil,json
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cmo3_tool as t
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py')
lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib)
named=lib.named
doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc);amount=float(sys.argv[3]) if len(sys.argv)>3 else 18
for side in 'LR':
    for part in ('Sclera','LidSkin_Lower','LashLower'):
        mesh=e.meshes[f'Eye_{side}_{part}'];info=lib.parent_info(e,doc,mesh)
        opens=lib.form_parameter(e,mesh,f'ParamEye{side}Open');relaxed=lib.form_parameter(e,mesh,'ParamRelaxed')
        W=info['x1']-info['x0'];H=info['y1']-info['y0']
        for f in named(mesh,'carray_list','keyforms'):
            guid=named(f,'CFormGuid','guid').get('xs.ref')
            if not relaxed[guid] or not opens[guid]:continue
            pos=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2)
            absolute=pos*[W,H]+[info['x0'],info['y0']]
            cx=1285 if side=='L' else 920
            u=np.clip((absolute[:,0]-cx)/145,-1,1)
            weight=np.maximum(0,1-u*u)**1.5
            if part=='Sclera':
                # Do not move the upper rim. Concentrate the displacement below the center.
                ty=np.clip((absolute[:,1]-1000)/110,0,1)
                weight*=ty**2
            pos[:,1]-=amount*weight*opens[guid]/H
            named(f,'float-array','positions').text=lib.lib.array(pos)
e.flush();doc.save(sys.argv[2]);print('LOWER_LID_ADJUSTED',amount)
