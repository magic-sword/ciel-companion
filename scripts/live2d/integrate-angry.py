"""Independent pouting face and reusable folded-ear controls."""
from pathlib import Path
import sys, importlib.util
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]; sys.path.insert(0,str(HERE))
import cmo3_tool as t, mesh_ops
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py')
lib=importlib.util.module_from_spec(sp); sp.loader.exec_module(lib); named=lib.named
doc=t.Cmo3(sys.argv[1]); e=lib.lib.Editor(doc)
e.add_param('ParamAngry','ぷんすか'); e.add_param('ParamEarFold','折れ耳'); e.flush()
for name,reference,order,nx,ny in [('Ear_R_Folded','Ear_R_Outer',215,16,12),('Ear_L_Folded','Ear_L_Outer',235,16,12),('Mouth_Angry','Mouth_Large',352,8,4),('Brow_Angry','Face_Skin',635,24,4)]:
    im=Image.open(ROOT/'.local/angry-integration/layers'/(name+'.png'))
    x0,y0,x1,y1=im.getbbox(); mesh_ops.remesh_quad(doc,name,(x0-4,y0-4,x1+4,y1+4),nx,ny)
    e=lib.lib.Editor(doc); mesh=e.meshes[name]; ref=e.meshes[reference]
    target=named(mesh,'CDeformerGuid','targetDeformerGuid'); target.attrib.clear(); target.attrib.update(named(ref,'CDeformerGuid','targetDeformerGuid').attrib)
    info=lib.parent_info(e,doc,mesh); points=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2)
    pos=(points-[info['x0'],info['y0']])/[info['x1']-info['x0'],info['y1']-info['y0']]
    if name=='Brow_Angry': pos[:,1]-=32/(info['y1']-info['y0'])
    coord=named(named(ref,'carray_list','keyforms')[0],'CoordType','coordType').attrib
    named(mesh,'b','isVisible').text='true'
    for f in named(mesh,'carray_list','keyforms'):
        named(f,'float-array','positions').text=lib.lib.array(pos)
        c=named(f,'CoordType','coordType'); c.attrib.clear(); c.attrib.update(coord)
        named(f,'i','drawOrder').text=str(order)
    ear=name.startswith('Ear_'); e.opacity_binding(name,'ParamEarFold' if ear else 'ParamAngry',True)
    if not ear:
        for param in ('ParamHappy','ParamRelaxed','ParamSurprised'): e.opacity_binding(name,param,False)
    if name=='Mouth_Angry': e.opacity_binding(name,'ParamMouthOpenY',False)
    e.flush()
e=lib.lib.Editor(doc)
for side in ('R','L'):
    for part in ('Outer','Inner','Base'): e.opacity_binding(f'Ear_{side}_{part}','ParamEarFold',False)
for name in ('Brow_R','Brow_L','Mouth_Line_Upper','Mouth_Line_Lower','Mouth_Small','Mouth_Skin_Upper','Mouth_Skin_Lower','Mouth_Happy','Mouth_Relaxed','Mouth_Surprised'):
    e.opacity_binding(name,'ParamAngry',False)
e.flush(); doc.save(sys.argv[2]); print('ANGRY_INTEGRATED')
