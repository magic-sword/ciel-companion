"""Replace existing folded-ear sources without duplicating layers or changing controls."""
from pathlib import Path
import sys, importlib.util
from PIL import Image
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1];sys.path.insert(0,str(HERE))
import cmo3_tool as t,mesh_ops
sp=importlib.util.spec_from_file_location('expression_lib',HERE/'integrate-expressions.py')
lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib)
doc=t.Cmo3(sys.argv[1]); editor=lib.Editor(doc)
for side in 'RL':
    name=f'Ear_{side}_Folded'; path=ROOT/'assets/ciel/generated/v42/layers'/(name+'.png')
    editor.replace_image(name,path)
editor.flush()
for side in 'RL':
    name=f'Ear_{side}_Folded';box=Image.open(ROOT/'assets/ciel/generated/v42/layers'/(name+'.png')).getbbox()
    mesh_ops.remesh_rect(doc,name,(box[0]-4,box[1]-4,box[2]+4,box[3]+4),20,16)
doc.save(sys.argv[2]);print('SAMOYED_EARS_INTEGRATED')
