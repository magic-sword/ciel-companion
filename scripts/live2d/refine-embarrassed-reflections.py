"""Keep primary eye reflections below the embarrassed upper lids."""
from pathlib import Path
import sys,importlib.util
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import cmo3_tool as t
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib);named=lib.named
from embarrassed_eye_shapes import eye_delta
doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc)
for side in 'LR':
 for part in ('Iris','Highlight'):
  mesh=e.meshes[f'Eye_{side}_{part}'];levels=lib.form_parameter(e,mesh,'ParamEmbarrassed');opens=lib.form_parameter(e,mesh,f'ParamEye{side}Open');smiles=lib.form_parameter(e,mesh,f'ParamEye{side}Smile');info=lib.parent_info(e,doc,mesh);H=info['y1']-info['y0'];W=info['x1']-info['x0'];forms=list(named(mesh,'carray_list','keyforms'));count=len(forms)//2
  for i,f in enumerate(forms):
   guid=named(f,'CFormGuid','guid').get('xs.ref');opening=opens.get(guid,1)
   if levels[guid]!=1 or not opening or smiles.get(guid,0):continue
   base=np.array(named(forms[i%count],'float-array','positions').text.split(),float).reshape(-1,2);pos=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2);absolute=base*[W,H]+[info['x0'],info['y0']];pos[:,1]=base[:,1]+eye_delta(side,part,absolute)*opening/H;named(f,'float-array','positions').text=lib.lib.array(pos)
e.flush();doc.save(sys.argv[2]);print('EMBARRASSED_REFLECTIONS_FITTED')
