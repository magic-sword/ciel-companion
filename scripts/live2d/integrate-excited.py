"""Bind extracted sparkling irises and smile to an independent excited control."""
from pathlib import Path
import sys,importlib.util,copy,json
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE))
import cmo3_tool as t,mesh_ops
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib);named=lib.named
data=json.loads((ROOT/'assets/ciel/generated/v43/placement.json').read_text())
doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc);e.add_param('ParamExcited','わくわく');e.flush()
controls=('ParamHappy','ParamRelaxed','ParamSurprised','ParamAngry','ParamSad','ParamTroubled','ParamEmbarrassed','ParamTeary')
for name,reference,order,nx,ny in [('Mouth_Excited','Mouth_Large',355,12,8),('Cheek_Excited','Face_Skin',268,24,8),('Eye_R_ExcitedIris','Eye_R_Iris',351,12,12),('Eye_L_ExcitedIris','Eye_L_Iris',441,12,12)]:
    box=Image.open(ROOT/'.local/excited-integration/layers'/(name+'.png')).getbbox()
    mesh_ops.remesh_quad(doc,name,(box[0]-4,box[1]-4,box[2]+4,box[3]+4),nx,ny)
    e=lib.lib.Editor(doc);mesh=e.meshes[name];ref=e.meshes[reference]
    target=named(mesh,'CDeformerGuid','targetDeformerGuid');target.attrib.clear();target.attrib.update(named(ref,'CDeformerGuid','targetDeformerGuid').attrib)
    if 'ExcitedIris' in name:
        clips=named(mesh,'carray_list','clipGuidList');clips.clear();clips.attrib.update(named(ref,'carray_list','clipGuidList').attrib)
        for n in named(ref,'carray_list','clipGuidList'):clips.append(copy.deepcopy(n))
    info=lib.parent_info(e,doc,mesh);points=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2)
    pos=(points-[info['x0'],info['y0']])/[info['x1']-info['x0'],info['y1']-info['y0']]
    coord=named(named(ref,'carray_list','keyforms')[0],'CoordType','coordType').attrib
    named(mesh,'b','isVisible').text='true'
    for f in named(mesh,'carray_list','keyforms'):
        named(f,'float-array','positions').text=lib.lib.array(pos)
        c=named(f,'CoordType','coordType');c.attrib.clear();c.attrib.update(coord);named(f,'i','drawOrder').text=str(order)
    e.opacity_binding(name,'ParamExcited',True)
    for pid in controls:e.opacity_binding(name,pid,False)
    if name=='Mouth_Excited':e.opacity_binding(name,'ParamMouthOpenY',False)
    if 'ExcitedIris' in name:
        side=name[4];e.opacity_binding(name,f'ParamEye{side}Open',True,key_values=(0,.5,1));e.opacity_binding(name,f'ParamEye{side}Smile',False)
    e.flush()
e=lib.lib.Editor(doc)
for name in ('Mouth_Line_Upper','Mouth_Line_Lower','Mouth_Small','Mouth_Skin_Upper','Mouth_Skin_Lower','Mouth_Happy','Mouth_Relaxed','Mouth_Surprised','Mouth_Angry','Mouth_Sad','Mouth_Troubled','Mouth_Embarrassed','Mouth_Teary','Cheek_Blush','Cheek_Happy','Cheek_Relaxed','Cheek_Embarrassed','Eye_L_Sparkle','Eye_R_Sparkle','Eye_R_Iris','Eye_L_Iris','Eye_R_Highlight','Eye_L_Highlight'):
    if name in e.meshes:e.opacity_binding(name,'ParamExcited',False)
e.flush()
for side in 'LR':
    for part in ('Sclera','LidSkin_Upper','LidSkin_Lower','LashUpper','LashLower','Crease'):
        name=f'Eye_{side}_{part}';e=lib.lib.Editor(doc);mesh=e.meshes[name]
        old=[float(named(f,'f','opacity').text) for f in named(mesh,'carray_list','keyforms')]
        e.opacity_binding(name,'ParamExcited',True);mesh=e.meshes[name]
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
            if part in ('LashUpper','LidSkin_Upper','Crease'):delta=upper
            elif part=='Sclera':
                ty=np.clip((absolute[:,1]-985)/145,0,1);delta=(1-ty)*upper+ty*data['lower_edge_offset']
            else:delta=np.full(len(pos),data['lower_edge_offset'])
            pos[:,1]+=delta*op/H;named(f,'float-array','positions').text=lib.lib.array(pos)
        e.flush()
doc.save(sys.argv[2]);print('EXCITED_INTEGRATED')
