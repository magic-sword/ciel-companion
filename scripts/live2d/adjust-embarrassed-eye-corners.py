"""Shorten downward outer lash tails only in the embarrassed, open-eye forms."""
from pathlib import Path
import sys,importlib.util
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cmo3_tool as t;import cubism_core as cc
sp=importlib.util.spec_from_file_location('embarrassed',HERE/'integrate-relaxed.py')
lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib);named=lib.named
doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc)
strength=float(sys.argv[3]) if len(sys.argv)>3 else .45
for side in 'LR':
    name=f'Eye_{side}_LashUpper';mesh=e.meshes[name]
    values={p:lib.form_parameter(e,mesh,p) for p in ('ParamEmbarrassed',f'ParamEye{side}Open',f'ParamEye{side}Smile')}
    for f in named(mesh,'carray_list','keyforms'):
        guid=named(f,'CFormGuid','guid').get('xs.ref')
        opening=values[f'ParamEye{side}Open'][guid]
        if values['ParamEmbarrassed'][guid]!=1 or not opening or values[f'ParamEye{side}Smile'][guid]:continue
        info=lib.parent_info(e,doc,mesh);scales=np.array([info['x1']-info['x0'],info['y1']-info['y0']]);offsets=np.array([info['x0'],info['y0']])
        pos=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2)
        world=pos*scales+offsets;x,y=world.T
        outer=(860-x)/65 if side=='R' else (x-1350)/65
        weight=np.clip(outer,0,1);weight=weight*weight*(3-2*weight)
        # Keep the lash arch and central eye opening intact. At half blink,
        # scale the edit with opening so the tail moves continuously to rest.
        world[:,1]-=strength*opening*weight*np.maximum(0,y-1040)
        named(f,'float-array','positions').text=lib.lib.array((world-offsets)/scales)
e.flush();doc.save(sys.argv[2]);print('EMBARRASSED_EYE_CORNERS_ADJUSTED',strength)
