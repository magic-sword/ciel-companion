"""Lower the already reduced iris/highlight to match the reference's white margin."""
from pathlib import Path
import sys,importlib.util
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import cmo3_tool as t
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib)
named=lib.named;doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc)
for side in 'LR':
    for part in ('Iris','Highlight'):
        mesh=e.meshes[f'Eye_{side}_{part}'];levels=lib.form_parameter(e,mesh,'ParamSurprised')
        opens=lib.form_parameter(e,mesh,f'ParamEye{side}Open');smiles=lib.form_parameter(e,mesh,f'ParamEye{side}Smile')
        info=lib.parent_info(e,doc,mesh);H=info['y1']-info['y0']
        for f in named(mesh,'carray_list','keyforms'):
            guid=named(f,'CFormGuid','guid').get('xs.ref');opening=opens.get(guid,1)
            if levels[guid]!=1 or smiles.get(guid,0) or not opening:continue
            pos=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2);pos[:,1]+=20*opening/H
            named(f,'float-array','positions').text=lib.lib.array(pos)
e.flush();doc.save(sys.argv[2]);print('SURPRISED_IRIS_POSITION_ADJUSTED')
