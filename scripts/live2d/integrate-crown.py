"""Bind the imported common crown to the head-following front-hair warp."""
from pathlib import Path
import importlib.util,sys,re
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cmo3_tool as t,mesh_ops
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py')
lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib);named=lib.named
doc=t.Cmo3(sys.argv[1]);box=Image.open(ROOT/'assets/ciel/generated/v45/layers/Hair_Crown.png').getbbox()
start,end=doc.mesh_block('Hair_Crown')
if re.search(r'<float-array xs.n="point" count="8">',doc.xml[start:end]):
    mesh_ops.remesh_quad(doc,'Hair_Crown',(box[0]-4,box[1]-4,box[2]+4,box[3]+4),20,10)
e=lib.lib.Editor(doc);mesh=e.meshes['Hair_Crown'];ref=e.meshes['Hair_Front_2']
target=named(mesh,'CDeformerGuid','targetDeformerGuid');target.attrib.clear();target.attrib.update(named(ref,'CDeformerGuid','targetDeformerGuid').attrib)
info=lib.parent_info(e,doc,mesh)
points=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2)
mapped=(points-[info['x0'],info['y0']])/[info['x1']-info['x0'],info['y1']-info['y0']]
ref_form=named(ref,'carray_list','keyforms')[0]
order=int(named(named(e.meshes['Hair_Back'],'carray_list','keyforms')[0],'i','drawOrder').text)+1
for form in named(mesh,'carray_list','keyforms'):
    named(form,'float-array','positions').text=lib.lib.array(mapped)
    coord=named(form,'CoordType','coordType');coord.attrib.clear();coord.attrib.update(named(ref_form,'CoordType','coordType').attrib)
    named(form,'f','opacity').text='1.0';named(form,'i','drawOrder').text=str(order)
named(mesh,'b','isVisible').text='true'
e.flush();doc.save(sys.argv[2]);print('COMMON_CROWN_INTEGRATED',len(e.meshes),info['x0'],info['y0'],order)
