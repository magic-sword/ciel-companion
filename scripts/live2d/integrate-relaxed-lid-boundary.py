"""Fit dedicated lower lines to the rendered white-eye edge, not mesh box edges."""
from pathlib import Path
import sys,importlib.util
import numpy as np
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cmo3_tool as t;import mesh_ops;import cubism_core as cc
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib)
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
named=lib.named;doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc)
core=cc.Model(ROOT/'.local/lower-lid-integration/export/Ciel.model3.json');tex=r.load_textures(core)
for side in 'LR':
    for part in ('LidSkin_Lower','LashLower'):
        mesh=e.meshes[f'Eye_{side}_{part}'];levels=lib.form_parameter(e,mesh,'ParamRelaxed')
        for f in named(mesh,'carray_list','keyforms'):
            if levels[named(f,'CFormGuid','guid').get('xs.ref')]==1:named(f,'f','opacity').text='0.0'
e.flush()
for side in 'LR':
    name=f'Eye_{side}_RelaxedLowerLine';path=ROOT/'.local/lid-boundary-integration/layers'/(name+'.png')
    image=Image.open(path).convert('RGBA');a=np.asarray(image);y,x=np.nonzero(a[:,:,3]>8)
    bbox=(int(x.min())-3,int(y.min())-3,int(x.max())+4,int(y.max())+4)
    mesh_ops.remesh_quad(doc,name,bbox,30,2)
    e=lib.lib.Editor(doc);mesh=e.meshes[name];white=e.meshes[f'Eye_{side}_Sclera']
    target=named(mesh,'CDeformerGuid','targetDeformerGuid');target.attrib.clear();target.attrib.update(named(white,'CDeformerGuid','targetDeformerGuid').attrib)
    info=lib.parent_info(e,doc,mesh);W=info['x1']-info['x0'];H=info['y1']-info['y0']
    points=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2)
    rest=(points-[info['x0'],info['y0']])/[W,H]
    refcoord=named(named(white,'carray_list','keyforms')[0],'CoordType','coordType').attrib
    named(mesh,'b','isVisible').text='true'
    for form in named(mesh,'carray_list','keyforms'):
        named(form,'float-array','positions').text=lib.lib.array(rest)
        coord=named(form,'CoordType','coordType');coord.attrib.clear();coord.attrib.update(refcoord)
        named(form,'i','drawOrder').text=str(511 if side=='L' else 401)
    e.opacity_binding(name,'ParamRelaxed',True)
    e.opacity_binding(name,f'ParamEye{side}Open',True,key_values=(0,.5,1))
    e.opacity_binding(name,'ParamHappy',False)
    e.opacity_binding(name,f'ParamEye{side}Smile',False)
    mesh=e.meshes[name]
    values={p:lib.form_parameter(e,mesh,p) for p in ('ParamRelaxed',f'ParamEye{side}Open','ParamHappy',f'ParamEye{side}Smile')}
    white_values={p:lib.form_parameter(e,white,p) for p in ('ParamRelaxed',f'ParamEye{side}Open',f'ParamEye{side}Smile')}
    # Source ink center for each column (same RGBA pixels as v32).
    alpha=a[:,:,3].astype(float);columns=np.flatnonzero(alpha.sum(axis=0)>8)
    source_y=np.array([np.average(np.arange(a.shape[0]),weights=alpha[:,col]) for col in columns])
    curves={}
    for opening in (.5,1):
        core.reset();core.set({'ParamRelaxed':1,f'ParamEye{side}Open':opening});core.update()
        d=next(d for d in core.drawables() if d['id']==f'Eye_{side}_Sclera')
        bounds=(740,950,1470,1190);off=np.array(bounds[:2]);mask=r.raster(d,tex[d['texture']],730,240,1,off)[:,:,3]
        ys,xs=np.nonzero(mask>.5);cols=np.unique(xs);edge=np.array([ys[xs==col].max()+950 for col in cols],float)
        # Recover the neutral-parent affine map from stored local positions and rendered bounds.
        reference_form=next(f for f in named(white,'carray_list','keyforms') if
            white_values['ParamRelaxed'][named(f,'CFormGuid','guid').get('xs.ref')]==1 and
            white_values[f'ParamEye{side}Open'][named(f,'CFormGuid','guid').get('xs.ref')]==opening and
            white_values[f'ParamEye{side}Smile'][named(f,'CFormGuid','guid').get('xs.ref')]==0)
        local=np.array(named(reference_form,'float-array','positions').text.split(),float).reshape(-1,2)
        scales=(d['pos'].max(axis=0)-d['pos'].min(axis=0))/(local.max(axis=0)-local.min(axis=0))
        offsets=d['pos'].min(axis=0)-local.min(axis=0)*scales
        curves[opening]=(cols+740,edge,scales,offsets)
    for form in named(mesh,'carray_list','keyforms'):
        guid=named(form,'CFormGuid','guid').get('xs.ref');opening=values[f'ParamEye{side}Open'][guid]
        active=values['ParamRelaxed'][guid]==1 and values['ParamHappy'][guid]==0 and values[f'ParamEye{side}Smile'][guid]==0 and opening>0
        named(form,'f','opacity').text='1.0' if active else '0.0'
        if not opening:continue
        cols,edge,scales,offsets=curves[opening]
        world_x=rest[:,0]*scales[0]+offsets[0]
        desired=np.interp(world_x,cols,edge)+.5
        old_center=np.interp(points[:,0],columns,source_y)
        old_center_world=((old_center-info['y0'])/H)*scales[1]+offsets[1]
        pos=rest.copy();pos[:,1]+=(desired-old_center_world)/scales[1]
        named(form,'float-array','positions').text=lib.lib.array(pos)
    e.flush()
doc.save(sys.argv[2]);print('LID_BOUNDARY_INTEGRATED')
