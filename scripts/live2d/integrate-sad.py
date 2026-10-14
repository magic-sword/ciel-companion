"""A sad face control preserving all previous expressions and blink/gaze keys."""
from pathlib import Path
import sys,importlib.util
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE))
import cmo3_tool as t,mesh_ops
from sad_eye_shapes import eye_delta
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib);named=lib.named
doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc);e.add_param('ParamSad','しょんぼり');e.flush()
for name,reference,order,nx,ny in [('Mouth_Sad','Mouth_Large',353,8,4),('Brow_Sad','Face_Skin',636,24,4)]:
    x0,y0,x1,y1=Image.open(ROOT/'.local/sad-integration/layers'/(name+'.png')).getbbox()
    mesh_ops.remesh_quad(doc,name,(x0-4,y0-4,x1+4,y1+4),nx,ny)
    e=lib.lib.Editor(doc);mesh=e.meshes[name];ref=e.meshes[reference]
    target=named(mesh,'CDeformerGuid','targetDeformerGuid');target.attrib.clear();target.attrib.update(named(ref,'CDeformerGuid','targetDeformerGuid').attrib)
    info=lib.parent_info(e,doc,mesh);points=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2)
    pos=(points-[info['x0'],info['y0']])/[info['x1']-info['x0'],info['y1']-info['y0']]
    coord=named(named(ref,'carray_list','keyforms')[0],'CoordType','coordType').attrib
    named(mesh,'b','isVisible').text='true'
    for f in named(mesh,'carray_list','keyforms'):
        named(f,'float-array','positions').text=lib.lib.array(pos)
        c=named(f,'CoordType','coordType');c.attrib.clear();c.attrib.update(coord);named(f,'i','drawOrder').text=str(order)
    e.opacity_binding(name,'ParamSad',True)
    for pid in ('ParamHappy','ParamRelaxed','ParamSurprised','ParamAngry'):e.opacity_binding(name,pid,False)
    if name=='Mouth_Sad':e.opacity_binding(name,'ParamMouthOpenY',False)
    e.flush()
e=lib.lib.Editor(doc)
for name in ('Brow_R','Brow_L','Brow_Angry','Mouth_Line_Upper','Mouth_Line_Lower','Mouth_Small','Mouth_Skin_Upper','Mouth_Skin_Lower','Mouth_Happy','Mouth_Relaxed','Mouth_Surprised','Mouth_Angry'):
    e.opacity_binding(name,'ParamSad',False)
e.flush()
for side in 'LR':
    for part in ('Sclera','LidSkin_Upper','LidSkin_Lower','LashUpper','LashLower','Crease','Iris','Highlight'):
        name=f'Eye_{side}_{part}';e=lib.lib.Editor(doc);mesh=e.meshes[name]
        old=[float(named(f,'f','opacity').text) for f in named(mesh,'carray_list','keyforms')]
        e.opacity_binding(name,'ParamSad',True);mesh=e.meshes[name]
        opening=lib.form_parameter(e,mesh,f'ParamEye{side}Open');smile=lib.form_parameter(e,mesh,f'ParamEye{side}Smile')
        info=lib.parent_info(e,doc,mesh);W=info['x1']-info['x0'];H=info['y1']-info['y0']
        for i,f in enumerate(named(mesh,'carray_list','keyforms')):
            named(f,'f','opacity').text=str(old[i%len(old)])
            if i<len(old):continue
            guid=named(f,'CFormGuid','guid').get('xs.ref');op=opening.get(guid,1)
            if not op or smile.get(guid,0):continue
            pos=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2)
            absolute=pos*[W,H]+[info['x0'],info['y0']]
            delta=eye_delta(side,part,absolute)
            pos[:,1]+=delta*op/H;named(f,'float-array','positions').text=lib.lib.array(pos)
        e.flush()
doc.save(sys.argv[2]);print('SAD_INTEGRATED')
