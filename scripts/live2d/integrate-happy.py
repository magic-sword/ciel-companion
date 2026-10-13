"""Replace the accepted happy eyes; bind dedicated mouth, blush and nose."""
import importlib.util,sys,copy,json
from pathlib import Path
import numpy as np
from PIL import Image
import xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import cmo3_tool as t
import mesh_ops
spec=importlib.util.spec_from_file_location('integration',HERE/'integrate-expressions.py')
lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(lib)
named=lib.named

def main():
    src,dst=sys.argv[1:3];doc=t.Cmo3(src);e=lib.Editor(doc)
    e.add_param('ParamHappy','嬉しい 顔（口・頬・鼻）')
    for name in ('Eye_L_Happy','Eye_R_Happy','Cheek_Happy','Mouth_Happy','Nose_Happy'):
        e.replace_image(name,ROOT/'.local/happy-integration/layers'/(name+'.png'))
        named(e.meshes[name],'b','isVisible').text='true'
    e.flush()
    # Existing eye parameter and parent mappings are retained while the image extent changes.
    for name in ('Eye_L_Happy','Eye_R_Happy'):
        image=Image.open(ROOT/'.local/happy-integration/layers'/(name+'.png'))
        x0,y0,x1,y1=image.getbbox();mesh_ops.remesh_rect(doc,name,(x0-4,y0-4,x1+4,y1+4),8,4)
    for name,ref,order in [('Cheek_Happy','Face_Skin',265),('Mouth_Happy','Mouth_Large',315),('Nose_Happy','Nose',280)]:
        image=Image.open(ROOT/'.local/happy-integration/layers'/(name+'.png'))
        x0,y0,x1,y1=image.getbbox();mesh_ops.remesh_quad(doc,name,(x0-4,y0-4,x1+4,y1+4),8,4)
        e=lib.Editor(doc);mesh=e.meshes[name];reference=e.meshes[ref]
        points=np.array(named(reference,'float-array','point').text.split(),float).reshape(-1,2)
        form=named(reference,'carray_list','keyforms')[0]
        positions=np.array(named(form,'float-array','positions').text.split(),float).reshape(-1,2)
        # The face/normal mouth are deformed by neutral parameter keys in the stored rig.
        # Use their rest mapping to attach the new image to the same deformer.
        target=named(mesh,'CDeformerGuid','targetDeformerGuid')
        target.attrib.clear();target.attrib.update(named(reference,'CDeformerGuid','targetDeformerGuid').attrib)
        parent=target.get('xs.ref')
        info=None
        for node in e.root.iter('CWarpDeformerSource'):
            if not node.get('xs.id'):continue
            warp=named(node,'s','localName').text
            wi=doc.warp_info(warp)
            if wi['guid']==parent:info=wi;break
        pts=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2)
        if info:
            mapped=(pts-[info['x0'],info['y0']])/[info['x1']-info['x0'],info['y1']-info['y0']]
        else:
            coef=np.linalg.lstsq(np.c_[points,np.ones(len(points))],positions,rcond=None)[0]
            mapped=np.c_[pts,np.ones(len(pts))]@coef
        for f in named(mesh,'carray_list','keyforms'):
            named(f,'float-array','positions').text=lib.array(mapped)
            coord=named(f,'CoordType','coordType');coord.attrib.clear();coord.attrib.update(named(form,'CoordType','coordType').attrib)
            named(f,'i','drawOrder').text=str(order)
        e.opacity_binding(name,'ParamHappy',True);e.flush()
    e=lib.Editor(doc)
    for name in ('Cheek_Blush','Nose')+tuple(n for n in e.meshes if n.startswith('Mouth_') and n!='Mouth_Happy'):
        e.opacity_binding(name,'ParamHappy',False)
    e.flush()
    root=ET.fromstring(doc.xml);ids={n.get('xs.id') for n in root.iter() if n.get('xs.id')}
    assert all(n.get('xs.ref') in ids for n in root.iter() if n.get('xs.ref'))
    for n in root.iter():
        if n.tag in ('float-array','short-array','int-array','byte-array') and n.text:
            assert int(n.get('count'))==len(n.text.split())
    doc.save(dst);print('HAPPY_INTEGRATION_DONE',dst)

if __name__=='__main__':main()
