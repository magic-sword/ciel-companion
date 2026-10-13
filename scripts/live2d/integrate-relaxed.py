"""One relaxed control, preserving blink/gaze and the existing open-mouth rig."""
import sys,importlib.util,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cmo3_tool as t;import mesh_ops
sp=importlib.util.spec_from_file_location('integration',HERE/'integrate-expressions.py')
lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib);named=lib.named

def parent_info(e,doc,mesh):
    guid=named(mesh,'CDeformerGuid','targetDeformerGuid').get('xs.ref')
    for node in e.root.iter('CWarpDeformerSource'):
        if node.get('xs.id'):
            info=doc.warp_info(named(node,'s','localName').text)
            if info['guid']==guid:return info
    raise ValueError('Expected warp parent')

def form_parameter(e,mesh,pid):
    grid=e.ids[named(mesh,'KeyformGridSource','keyformGridSource').get('xs.ref')]
    result={}
    for item in named(grid,'array_list','keyformsOnGrid'):
        guid=named(item,'CFormGuid','keyformGuid').get('xs.ref')
        for key in item.iter('KeyOnParameter'):
            binding=e.ids[named(key,'KeyformBindingSource','binding').get('xs.ref')]
            if named(binding,'CParameterGuid','parameterGuid').get('xs.ref')==e.params[pid]:
                values=named(binding,'array_list','keys')
                result[guid]=float(values[int(named(key,'i','keyIndex').text)].text)
    return result

def main():
    doc=t.Cmo3(sys.argv[1]);e=lib.Editor(doc);e.add_param('ParamRelaxed','にこにこ')
    for name in ('Mouth_Relaxed','Cheek_Relaxed'):
        named(e.meshes[name],'b','isVisible').text='true'
    e.flush()
    for name,ref,order in [('Mouth_Relaxed','Mouth_Large',350),('Cheek_Relaxed','Face_Skin',266)]:
        im=Image.open(ROOT/'.local/relaxed-integration/layers'/(name+'.png'));a=np.asarray(im)
        y,x=np.nonzero(a[:,:,3]>8);box=(int(x.min())-4,int(y.min())-4,int(x.max())+5,int(y.max())+5)
        mesh_ops.remesh_quad(doc,name,box,12,5)
        e=lib.Editor(doc);mesh=e.meshes[name];reference=e.meshes[ref]
        target=named(mesh,'CDeformerGuid','targetDeformerGuid');target.attrib.clear()
        target.attrib.update(named(reference,'CDeformerGuid','targetDeformerGuid').attrib)
        info=parent_info(e,doc,mesh)
        pts=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2)
        mapped=(pts-[info['x0'],info['y0']])/[info['x1']-info['x0'],info['y1']-info['y0']]
        ref_form=named(reference,'carray_list','keyforms')[0]
        for f in named(mesh,'carray_list','keyforms'):
            named(f,'float-array','positions').text=lib.array(mapped)
            coord=named(f,'CoordType','coordType');coord.attrib.clear();coord.attrib.update(named(ref_form,'CoordType','coordType').attrib)
            named(f,'i','drawOrder').text=str(order)
            if name=='Cheek_Relaxed':named(f,'f','opacity').text='0.5'
        e.opacity_binding(name,'ParamRelaxed',True)
        if name=='Mouth_Relaxed':e.opacity_binding(name,'ParamMouthOpenY',False)
        # Happy and relaxed overlays must not be stacked.
        e.opacity_binding(name,'ParamHappy',False);e.flush()
    e=lib.Editor(doc)
    for name in ('Mouth_Line_Upper','Mouth_Line_Lower','Cheek_Blush','Cheek_Happy','Mouth_Happy','Nose_Happy'):
        e.opacity_binding(name,'ParamRelaxed',False)
    e.flush()
    # Additive deformation keys duplicate existing blink/smile forms without changing level 0.
    for side in 'LR':
        for part in ('Sclera','LidSkin_Upper','LidSkin_Lower','LashUpper','LashLower','Crease'):
            name=f'Eye_{side}_{part}';e=lib.Editor(doc);mesh=e.meshes[name]
            old_opacity=[float(named(f,'f','opacity').text) for f in named(mesh,'carray_list','keyforms')]
            e.opacity_binding(name,'ParamRelaxed',True)
            mesh=e.meshes[name];forms=named(mesh,'carray_list','keyforms');opens=form_parameter(e,mesh,f'ParamEye{side}Open')
            info=parent_info(e,doc,mesh);W=info['x1']-info['x0'];H=info['y1']-info['y0']
            for index,f in enumerate(forms):
                named(f,'f','opacity').text=str(old_opacity[index%len(old_opacity)])
                if index<len(old_opacity):continue
                opening=opens[named(f,'CFormGuid','guid').get('xs.ref')]
                pos=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2)
                absolute=pos*[W,H]+[info['x0'],info['y0']]
                # Relaxed smile: upper lid slightly down, lower lid raised in the middle.
                cx=1285 if side=='L' else 920
                u=np.clip((absolute[:,0]-cx)/145,-1,1);lift=20*(1-.55*u*u)
                if part in ('LashUpper','LidSkin_Upper','Crease'):
                    delta=30*(1-.35*u*u)
                elif part in ('LashLower','LidSkin_Lower'):
                    delta=-lift
                else:
                    ty=np.clip((absolute[:,1]-985)/145,0,1)
                    delta=(1-ty)*30*(1-.35*u*u)-ty*lift
                pos[:,1]+=delta*opening/H
                named(f,'float-array','positions').text=lib.array(pos)
            e.flush()
    e=lib.Editor(doc);ids=set(e.ids)
    assert all(n.get('xs.ref') in ids for n in e.root.iter() if n.get('xs.ref'))
    doc.save(sys.argv[2]);print('RELAXED_INTEGRATION_DONE')

if __name__=='__main__':main()
