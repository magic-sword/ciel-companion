"""Translate the angry brow mesh without changing its shape or materials."""
from pathlib import Path
import sys,importlib.util
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import cmo3_tool as t
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py')
lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib)
doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc);mesh=e.meshes['Brow_Angry']
info=lib.parent_info(e,doc,mesh);dy=float(sys.argv[3]) if len(sys.argv)>3 else -32
for f in lib.named(mesh,'carray_list','keyforms'):
    pos=np.array(lib.named(f,'float-array','positions').text.split(),float).reshape(-1,2)
    pos[:,1]+=dy/(info['y1']-info['y0'])
    lib.named(f,'float-array','positions').text=lib.lib.array(pos)
e.flush();doc.save(sys.argv[2]);print('BROW_POSITION_UPDATED',dy)
