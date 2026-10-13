"""One surprise control: rounded open eyes, smaller irises and reference round mouth."""
from pathlib import Path
import sys,importlib.util
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE))
import cmo3_tool as t;import mesh_ops
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib)
named=lib.named;doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc);e.add_param('ParamSurprised','驚き')
e.flush()
for side in 'LR':
    for part in ('Sclera','LidSkin_Upper','LidSkin_Lower','LashUpper','LashLower','Crease','Iris','Highlight'):
        name=f'Eye_{side}_{part}';e=lib.lib.Editor(doc);mesh=e.meshes[name]
        old=[float(named(f,'f','opacity').text) for f in named(mesh,'carray_list','keyforms')]
        e.opacity_binding(name,'ParamSurprised',True);mesh=e.meshes[name]
        opening=lib.form_parameter(e,mesh,f'ParamEye{side}Open');smile=lib.form_parameter(e,mesh,f'ParamEye{side}Smile')
        info=lib.parent_info(e,doc,mesh);W=info['x1']-info['x0'];H=info['y1']-info['y0']
        for i,f in enumerate(named(mesh,'carray_list','keyforms')):
            named(f,'f','opacity').text=str(old[i%len(old)])
            if i<len(old):continue
            guid=named(f,'CFormGuid','guid').get('xs.ref');op=opening.get(guid,1)
            if not op or smile.get(guid,0):continue
            pos=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2)
            if part in ('Iris','Highlight'):
                center=pos.mean(0);pos=(pos-center)*[.70,.742]+center
                pos[:,1]+=20*op/H
            else:
                # Stretch vertically around the eye center. Closed keys remain unchanged.
                cy=(1050-info['y0'])/H;pos[:,1]=cy+(pos[:,1]-cy)*(1+.15*op)
            named(f,'float-array','positions').text=lib.lib.array(pos)
        e.flush()
name='Mouth_Surprised';image=Image.open(ROOT/'.local/surprised-integration/layers'/(name+'.png'))
x0,y0,x1,y1=image.getbbox();mesh_ops.remesh_quad(doc,name,(x0-4,y0-4,x1+4,y1+4),8,6)
e=lib.lib.Editor(doc);mesh=e.meshes[name];ref=e.meshes['Mouth_Large']
target=named(mesh,'CDeformerGuid','targetDeformerGuid');target.attrib.clear();target.attrib.update(named(ref,'CDeformerGuid','targetDeformerGuid').attrib)
info=lib.parent_info(e,doc,mesh);points=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2)
pos=(points-[info['x0'],info['y0']])/[info['x1']-info['x0'],info['y1']-info['y0']]
coord=named(named(ref,'carray_list','keyforms')[0],'CoordType','coordType').attrib
named(mesh,'b','isVisible').text='true'
for f in named(mesh,'carray_list','keyforms'):
    named(f,'float-array','positions').text=lib.lib.array(pos)
    c=named(f,'CoordType','coordType');c.attrib.clear();c.attrib.update(coord)
    named(f,'i','drawOrder').text='351'
e.opacity_binding(name,'ParamSurprised',True);e.opacity_binding(name,'ParamMouthOpenY',False)
e.opacity_binding(name,'ParamHappy',False);e.opacity_binding(name,'ParamRelaxed',False);e.flush()
e=lib.lib.Editor(doc)
for name in ('Mouth_Line_Upper','Mouth_Line_Lower','Mouth_Small','Mouth_Skin_Upper','Mouth_Skin_Lower','Mouth_Happy','Mouth_Relaxed'):
    e.opacity_binding(name,'ParamSurprised',False)
e.flush();doc.save(sys.argv[2]);print('SURPRISED_INTEGRATED')
