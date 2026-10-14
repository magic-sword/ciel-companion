"""Use the reference crease in the upper-lash artwork instead of warping the old crease.

Run prepare-jitome.py first to restore clean source parts before repeating this step.
Input is the saved model before this polish, not a previously polished model.
"""
from pathlib import Path
import sys,importlib.util,json
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE))
import cmo3_tool as t,mesh_ops
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib);named=lib.named
source=np.asarray(Image.open(ROOT/'assets/ciel/generated/v22/expressions/jitome.png').convert('RGBA'));rgb=source[:,:,:3].astype(float);y,x=np.indices(source.shape[:2])
data=json.loads((ROOT/'assets/ciel/generated/v44/placement.json').read_text());s=data['shared_scale'];ox,oy=data['offset']
doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc)
for side,box in [('R',(530,975,745,1004)),('L',(930,965,1150,991))]:
    x0,y0,x1,y1=box;roi=(x>=x0)&(x<x1)&(y>=y0)&(y<y1)
    from scipy.ndimage import label,gaussian_filter
    selection=roi&(rgb[:,:,0]-rgb[:,:,1]>10)&(rgb[:,:,0]-rgb[:,:,2]>4)
    regions,count=label(selection);clean=np.zeros(selection.shape,bool)
    for i in range(1,count+1):
        yy,xx=np.nonzero(regions==i)
        if len(xx)>=8 and (xx.max()-xx.min()+1)/(yy.max()-yy.min()+1)>1.5:clean|=regions==i
    raw_alpha=np.clip((rgb[:,:,0]-rgb[:,:,1]-3)/50,0,.75)*roi
    alpha=raw_alpha*gaussian_filter(clean.astype(float),.5)
    # Remove the pale skin matte; recomposition retains the guide's line colour.
    skin=np.array([255,248,248]);a=np.maximum(raw_alpha[:,:,None],1e-8)
    colour=np.clip((rgb-skin*(1-a))/a,0,255)
    b=np.zeros_like(source);b[:,:,:3]=np.round(colour).astype(np.uint8);b[:,:,3]=np.round(alpha*255).astype(np.uint8);b[b[:,:,3]==0]=0
    name=f'Eye_{side}_JitomeUpper';p=ROOT/'assets/ciel/generated/v44/parts'/(name+'.png')
    art=Image.open(p).convert('RGBA');art.alpha_composite(Image.fromarray(b));art.save(p)
    layer=art.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
    layer.save(ROOT/'assets/ciel/generated/v44/layers'/(name+'.png'));layer.save(ROOT/'.local/jitome-integration/layers'/(name+'.png'))
    e.replace_image(name,ROOT/'assets/ciel/generated/v44/layers'/(name+'.png'))
    data['parts'][name]={'source_bbox':art.getbbox(),'target_bbox':layer.getbbox()}
e.flush()
for side in 'LR':
    name=f'Eye_{side}_JitomeUpper';box=Image.open(ROOT/'assets/ciel/generated/v44/layers'/(name+'.png')).getbbox()
    mesh_ops.remesh_rect(doc,name,(box[0]-4,box[1]-4,box[2]+4,box[3]+4),20,8)
    e=lib.lib.Editor(doc);mesh=e.meshes[name];info=lib.parent_info(e,doc,mesh);opening=lib.form_parameter(e,mesh,f'ParamEye{side}Open')
    for f in named(mesh,'carray_list','keyforms'):
        op=opening[named(f,'CFormGuid','guid').get('xs.ref')];pos=np.array(named(f,'float-array','positions').text.split(),float).reshape(-1,2)
        pos[:,1]+=40*(1-op)/(info['y1']-info['y0']);named(f,'float-array','positions').text=lib.lib.array(pos)
    old=e.meshes[f'Eye_{side}_Crease'];levels=lib.form_parameter(e,old,'ParamJitome')
    for f in named(old,'carray_list','keyforms'):
        if levels[named(f,'CFormGuid','guid').get('xs.ref')]==1:named(f,'f','opacity').text='0.0'
    e.flush()
data['crease_in_upper_artwork']=True
(ROOT/'assets/ciel/generated/v44/placement.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
doc.save(sys.argv[2]);print('JITOME_REFERENCE_CREASE_POLISHED')
