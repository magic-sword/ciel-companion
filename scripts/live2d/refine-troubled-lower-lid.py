"""Use the white-eye mask and an existing lower line for the troubled face.

Input: original v37 CMO3. Its SDK export remains in .local/troubled-integration/export.
Only ParamTroubled=1 forms change; existing expression forms stay intact.
"""
from pathlib import Path
import sys,importlib.util,json
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];HERE=ROOT/'scripts/live2d';sys.path.insert(0,str(HERE));import cmo3_tool as t,cubism_core as cc
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib);named=lib.named
sp=importlib.util.spec_from_file_location('ren',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
doc=t.Cmo3(sys.argv[1]);core=cc.Model(ROOT/'.local/troubled-integration/export/Ciel.model3.json');tex=r.load_textures(core);report={}
for side in 'LR':
 e=lib.lib.Editor(doc)
 for part in ('LidSkin_Lower','LashLower'):
  mesh=e.meshes[f'Eye_{side}_{part}'];levels=lib.form_parameter(e,mesh,'ParamTroubled')
  for f in named(mesh,'carray_list','keyforms'):
   if levels[named(f,'CFormGuid','guid').get('xs.ref')]==1:named(f,'f','opacity').text='0.0'
 e.flush()
 name=f'Eye_{side}_RelaxedLowerLine';e=lib.lib.Editor(doc);mesh=e.meshes[name];old=[float(named(f,'f','opacity').text) for f in named(mesh,'carray_list','keyforms')];e.opacity_binding(name,'ParamTroubled',True);mesh=e.meshes[name]
 values={pid:lib.form_parameter(e,mesh,pid) for pid in ('ParamTroubled','ParamRelaxed','ParamHappy',f'ParamEye{side}Open',f'ParamEye{side}Smile')}
 white=e.meshes[f'Eye_{side}_Sclera'];whitevalues={pid:lib.form_parameter(e,white,pid) for pid in ('ParamTroubled','ParamRelaxed','ParamSurprised','ParamAngry','ParamSad',f'ParamEye{side}Open',f'ParamEye{side}Smile')}
 info=lib.parent_info(e,doc,mesh);W=info['x1']-info['x0'];H=info['y1']-info['y0'];points=np.array(named(mesh,'float-array','point').text.split(),float).reshape(-1,2);rest=(points-[info['x0'],info['y0']])/[W,H]
 image=np.asarray(Image.open(ROOT/'assets/ciel/current/layers'/(name+'.png')).convert('RGBA'));alpha=image[:,:,3].astype(float);columns=np.flatnonzero(alpha.sum(axis=0)>8);sourcey=np.array([np.average(np.arange(image.shape[0]),weights=alpha[:,x]) for x in columns]);curves={}
 for opening in (.5,1):
  core.reset();core.set({'ParamTroubled':1,f'ParamEye{side}Open':opening});core.update();d=next(d for d in core.drawables() if d['id']==f'Eye_{side}_Sclera')
  mask=r.raster(d,tex[d['texture']],1460,520,2,np.array([740,950]))[:,:,3]
  yy,xx=np.nonzero(mask>.5);cols=np.unique(xx);edge=np.array([yy[xx==x].max()/2+950 for x in cols]);worldcols=cols/2+740
  wf=next(f for f in named(white,'carray_list','keyforms') if all(whitevalues[pid].get(named(f,'CFormGuid','guid').get('xs.ref'),0)==v for pid,v in [('ParamTroubled',1),('ParamRelaxed',0),('ParamSurprised',0),('ParamAngry',0),('ParamSad',0),(f'ParamEye{side}Open',opening),(f'ParamEye{side}Smile',0)]))
  local=np.array(named(wf,'float-array','positions').text.split(),float).reshape(-1,2);scales=(d['pos'].max(axis=0)-d['pos'].min(axis=0))/(local.max(axis=0)-local.min(axis=0));offsets=d['pos'].min(axis=0)-local.min(axis=0)*scales
  curves[opening]=(worldcols,edge,scales,offsets)
 for i,f in enumerate(named(mesh,'carray_list','keyforms')):
  guid=named(f,'CFormGuid','guid').get('xs.ref')
  if values['ParamTroubled'][guid]==0:
   named(f,'f','opacity').text=str(old[i%len(old)]);continue
  opening=values[f'ParamEye{side}Open'][guid];active=opening>0 and values['ParamHappy'][guid]==0 and values[f'ParamEye{side}Smile'][guid]==0
  named(f,'f','opacity').text='1.0' if active else '0.0'
  if not opening:continue
  cols,edge,scales,offsets=curves[opening];worldx=rest[:,0]*scales[0]+offsets[0];desired=np.interp(worldx,cols,edge)+.5;oldcenter=np.interp(points[:,0],columns,sourcey);oldworld=((oldcenter-info['y0'])/H)*scales[1]+offsets[1]
  pos=rest.copy();pos[:,1]+=(desired-oldworld)/scales[1];named(f,'float-array','positions').text=lib.lib.array(pos)
 e.flush();report[side]={'legacy_skin_and_line_hidden_only_in_troubled':True,'existing_relaxed_line_reused':True,'boundary_fit_openings':[.5,1]}
doc.save(sys.argv[2]);Path('.local/lower-lid-review/refinement.json').write_text(json.dumps(report,indent=2));print('TROUBLED_LOWER_LID_REFINED')
