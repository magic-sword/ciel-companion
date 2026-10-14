"""Verify a texture-only skin update and render the native SDK's expressions."""
from pathlib import Path
import importlib.util,json,sys,hashlib
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
old=cc.Model(ROOT/'.local/skin-adoption/runtime-before/Ciel.model3.json');new=cc.Model(sys.argv[1]);out=Path(sys.argv[2]);tex=r.load_textures(new)
def pose(m,v):
    m.reset();assert not m.set(v);m.update();return {d['id']:d for d in m.drawables()}
recipes=ROOT/'assets/ciel/runtime/Expressions';entries=[]
for p in sorted(recipes.glob('*.json')):
    entries.append((p.name.replace('.exp3.json',''),{v['Id']:v['Value'] for v in json.loads(p.read_text(encoding='utf-8'))['Parameters']}))
entries.append(('thinking (pending)',{'ParamEyeBallX':-.5,'ParamEyeBallY':.6,'ParamBrowLY':.4,'ParamMouthForm':-.3}))
assert len(entries)==12
poses=[v for _,v in entries]
for angle in (-30,0,30):
 for blink in (0,.5,1):
  for mouth in (0,.5,1):
   for hair in (-1,0,1):
    poses.append({'ParamJitome':1,'ParamAngleX':angle,'ParamAngleY':-angle,'ParamEyeLOpen':blink,'ParamEyeROpen':blink,'ParamMouthOpenY':mouth,'ParamHairFront':hair,'ParamHairBack':hair})
for v in poses:
    a=pose(old,v);b=pose(new,v);assert set(a)==set(b) and len(b)==92
    for name in a:
        assert np.allclose(a[name]['pos'],b[name]['pos'],atol=.001),name
        assert np.array_equal(a[name]['tri'],b[name]['tri']),name
        assert abs(a[name]['opacity']-b[name]['opacity'])<.001,name
        assert a[name]['draw_order']==b[name]['draw_order'],name
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',18)
board=Image.new('RGB',(1600,1320),(64,72,104));draw=ImageDraw.Draw(board)
for i,(name,values) in enumerate(entries):
    pose(new,values);im=r.render(new,tex,800/1700,(250,0,1950,1700)).resize((400,400),Image.Resampling.LANCZOS)
    board.paste(im,(i%4*400,i//4*440+40));draw.text((i%4*400+8,i//4*440+7),name,font=font,fill='white')
board.save(out/'all-expressions.png')
pose(new,{});r.render(new,tex,1,(550,650,1600,1700)).save(out/'native-neutral.png')
pose(old,{})
before=np.asarray(r.render(old,r.load_textures(old),1,(1040,1120,1160,1190))).reshape(-1,3)
after=np.asarray(r.render(new,tex,1,(1040,1120,1160,1190))).reshape(-1,3)
before=np.median(before,axis=0);after=np.median(after,axis=0)
assert before[0]-after[0]>1 and after[2]-before[2]>1,'SDK atlas still has old skin colors'
info=json.loads((ROOT/'assets/ciel/generated/v46/generation-provenance.json').read_text(encoding='utf-8'))
for v in info['layers']:
    name=v['name'];a=np.asarray(Image.open(ROOT/'.local/skin-adoption/current-before/layers'/(name+'.png')));b=np.asarray(Image.open(ROOT/'assets/ciel/generated/v46/layers'/(name+'.png')))
    assert np.array_equal(a[:,:,3],b[:,:,3]),name
verify={'reset_passed':True,'drawables':92,'expression_poses':len(entries),'combined_motion_poses':81,
        'geometry_triangles_opacity_and_draw_order_preserved':True,'material_alpha_preserved':True,
        'skin_materials_replaced':[v['name'] for v in info['layers']],
        'native_face_rgb_before':before.tolist(),'native_face_rgb_after':after.tolist(),
        'moc_bytes_unchanged':Path(new.dir,'Ciel.moc3').read_bytes()==Path(old.dir,'Ciel.moc3').read_bytes()}
(out/'verification.json').write_text(json.dumps(verify,indent=2)+'\n',encoding='utf-8');print('SKIN_NATIVE_CHECK_PASSED',len(poses))
