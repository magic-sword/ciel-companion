"""Bind straight upper lashes, flat brows and mouth to a jitome control."""
from pathlib import Path
import sys,importlib.util,copy,json
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE))
import cmo3_tool as t,mesh_ops
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib);named=lib.named
data=json.loads((ROOT/'assets/ciel/generated/v44/placement.json').read_text())
doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc);e.add_param('ParamJitome','ジト目');e.flush()
controls=('ParamHappy','ParamRelaxed','ParamSurprised','ParamAngry','ParamSad','ParamTroubled','ParamEmbarrassed','ParamTeary','ParamExcited')
for name,reference,order,nx,ny in [('Mouth_Jitome','Mouth_Large',355,12,8),('Brow_Jitome','Face_Skin',638,24,4),('Eye_R_JitomeUpper','Eye_R_LashUpper',391,20,8),('Eye_L_JitomeUpper','Eye_L_LashUpper',481,20,8)]:
    box=Image.open(ROOT/'.local/jitome-integration/layers'/(name+'.png')).getbbox()
    mesh_ops.remesh_quad(doc,name,(box[0]-4,box[1]-4,box[2]+4,box[3]+4),nx,ny)
    e=lib.lib.Editor(doc);mesh=e.meshes[name];ref=e.meshes[reference]
    target=named(mesh,'CDeformerGuid','targetDeformerGuid');target.attrib.clear();target.attrib.update(named(ref,'CDeformerGuid','targetDeformerGuid').attrib)
    info=lib.parent_info(e,doc,mesh);points=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2)
    pos=(points-[info['x0'],info['y0']])/[info['x1']-info['x0'],info['y1']-info['y0']]
    coord=named(named(ref,'carray_list','keyforms')[0],'CoordType','coordType').attrib
    named(mesh,'b','isVisible').text='true'
    for f in named(mesh,'carray_list','keyforms'):
        named(f,'float-array','positions').text=lib.lib.array(pos)
        c=named(f,'CoordType','coordType');c.attrib.clear();c.attrib.update(coord);named(f,'i','drawOrder').text=str(order)
    e.opacity_binding(name,'ParamJitome',True)
    for pid in controls:e.opacity_binding(name,pid,False)
    if name=='Mouth_Jitome':e.opacity_binding(name,'ParamMouthOpenY',False)
    if 'JitomeUpper' in name:
        side=name[4];e.opacity_binding(name,f'ParamEye{side}Open',True,key_values=(0,.5,1));e.opacity_binding(name,f'ParamEye{side}Smile',False)
        opening=lib.form_parameter(e,mesh,f'ParamEye{side}Open')
        for f in named(mesh,'carray_list','keyforms'):
            guid=named(f,'CFormGuid','guid').get('xs.ref');op=opening[guid]
            if op==.5:named(f,'f','opacity').text=str(float(named(f,'f','opacity').text)*2)
            p=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2);p[:,1]+=40*(1-op)/(info['y1']-info['y0']);named(f,'float-array','positions').text=lib.lib.array(p)
    e.flush()
e=lib.lib.Editor(doc)
for name in ('Mouth_Line_Upper','Mouth_Line_Lower','Mouth_Small','Mouth_Skin_Upper','Mouth_Skin_Lower','Mouth_Happy','Mouth_Relaxed','Mouth_Surprised','Mouth_Angry','Mouth_Sad','Mouth_Troubled','Mouth_Embarrassed','Mouth_Teary','Mouth_Excited','Brow_R','Brow_L','Brow_Angry','Brow_Sad','Brow_Troubled','Brow_Embarrassed','Brow_Teary','Eye_R_LashUpper','Eye_L_LashUpper','Eye_L_Sparkle','Eye_R_Sparkle'):
    if name in e.meshes:e.opacity_binding(name,'ParamJitome',False)
e.flush()
for side in 'LR':
    for part in ('Sclera','LidSkin_Upper','LidSkin_Lower','LashLower','Crease','Iris','Highlight'):
        name=f'Eye_{side}_{part}';e=lib.lib.Editor(doc);mesh=e.meshes[name]
        old=[float(named(f,'f','opacity').text) for f in named(mesh,'carray_list','keyforms')]
        e.opacity_binding(name,'ParamJitome',True);mesh=e.meshes[name]
        opening=lib.form_parameter(e,mesh,f'ParamEye{side}Open');smile=lib.form_parameter(e,mesh,f'ParamEye{side}Smile')
        info=lib.parent_info(e,doc,mesh);W=info['x1']-info['x0'];H=info['y1']-info['y0']
        for i,f in enumerate(named(mesh,'carray_list','keyforms')):
            named(f,'f','opacity').text=str(old[i%len(old)])
            if i<len(old):continue
            guid=named(f,'CFormGuid','guid').get('xs.ref');op=opening.get(guid,1)
            if not op or smile.get(guid,0):continue
            pos=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2)
            absolute=pos*[W,H]+[info['x0'],info['y0']];cx=1285 if side=='L' else 920
            upper=np.polyval(data['eye_profiles'][side]['coefficients'],np.clip((absolute[:,0]-cx)/145,-1,1))
            upper=np.clip(upper,-5,100)
            if part in ('Iris','Highlight'):delta=np.full(len(pos),data['iris_y_offset']/op)
            elif part in ('LidSkin_Upper','Crease'):delta=upper
            elif part=='Sclera':
                ty=np.clip((absolute[:,1]-985)/145,0,1);delta=(1-ty)*upper+ty*data['lower_edge_offset']
            else:delta=np.full(len(pos),data['lower_edge_offset'])
            pos[:,1]+=delta*op/H;named(f,'float-array','positions').text=lib.lib.array(pos)
        e.flush()
doc.save(sys.argv[2]);print('JITOME_INTEGRATED')
