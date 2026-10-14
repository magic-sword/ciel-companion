"""Verify the exported v47 crown and preserve all other drawable geometry."""
from pathlib import Path
import importlib.util, json, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE)); import cubism_core as cc
spec=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py')
r=importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
work=ROOT/'.local/crown-completion-adoption'
old=cc.Model(work/'runtime-before/Ciel.model3.json'); new=cc.Model(sys.argv[1])
out=Path(sys.argv[2]); tex=r.load_textures(new); oldtex=r.load_textures(old)
def pose(m,values):
    m.reset(); assert not m.set(values); m.update()
    return {d['id']:d for d in m.drawables()}
entries=[]
for p in sorted((ROOT/'assets/ciel/runtime/Expressions').glob('*.json')):
    entries.append((p.name.replace('.exp3.json',''),{q['Id']:q['Value'] for q in json.loads(p.read_text(encoding='utf-8'))['Parameters']}))
entries.append(('thinking (pending)',{'ParamEyeBallX':-.5,'ParamEyeBallY':.6,'ParamBrowLY':.4,'ParamMouthForm':-.3}))
assert len(entries)==12
poses=[v for _,v in entries]
for angle in (-30,0,30):
    for fold in (0,.5,1):
        for blink in (0,.5,1):
            for hair in (-1,0,1):
                poses.append({'ParamAngleX':angle,'ParamAngleY':-angle,'ParamAngleZ':angle,'ParamEarFold':fold,'ParamEyeLOpen':blink,'ParamEyeROpen':blink,'ParamHairFront':hair,'ParamHairBack':hair,'ParamMouthOpenY':blink})
for v in poses:
    a=pose(old,v); b=pose(new,v); assert set(a)==set(b) and len(b)==92
    for name in a:
        assert np.isfinite(b[name]['pos']).all(),name
        assert abs(a[name]['opacity']-b[name]['opacity'])<.001,name
        assert a[name]['draw_order']==b[name]['draw_order'],name
        if name!='Hair_Crown':
            assert np.allclose(a[name]['pos'],b[name]['pos'],atol=.001),name
            assert np.array_equal(a[name]['tri'],b[name]['tri']),name
    assert b['Hair_Crown']['opacity']>.99
base=pose(new,{})['Hair_Crown']['pos'].copy()
assert len(base)==561
for pid in ('ParamAngleX','ParamAngleY','ParamAngleZ'):
    ds=pose(new,{pid:30}); assert not np.allclose(base,ds['Hair_Crown']['pos']),pid
assert np.allclose(base,pose(new,{'ParamHairBack':1})['Hair_Crown']['pos'],atol=.05)
a=np.asarray(Image.open(work/'current-before/layers/Hair_Back.png'))
b=np.asarray(Image.open(ROOT/'assets/ciel/generated/v47/layers/Hair_Back.png'))
assert np.array_equal(a[:,:,:3],b[:,:,:3]) and np.array_equal(a[600:],b[600:])
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',18)
board=Image.new('RGB',(1600,1320),(64,72,104)); draw=ImageDraw.Draw(board)
for i,(name,v) in enumerate(entries):
    pose(new,v); im=r.render(new,tex,800/1700,(250,0,1950,1700)).resize((400,400),Image.Resampling.LANCZOS)
    board.paste(im,(i%4*400,i//4*440+40)); draw.text((i%4*400+8,i//4*440+7),name,font=font,fill='white')
board.save(out/'all-expressions.png')
troubled=dict(entries[[name for name,_ in entries].index('troubled')][1])
pose(old,troubled); before=np.asarray(r.render(old,oldtex,1,(700,240,1500,430))).astype(float)
pose(new,troubled); after=np.asarray(r.render(new,tex,1,(700,240,1500,430))).astype(float)
changed=int((np.max(np.abs(before-after),axis=2)>10).sum())
assert changed>100,'The exported atlas does not show the crown completion'
board=Image.new('RGB',(1500,1000),(64,72,104)); draw=ImageDraw.Draw(board)
for row,(model,textures,label) in enumerate(((old,oldtex,'Before'),(new,tex,'v47 native SDK'))):
    for i,angle in enumerate((-30,0,30)):
        pose(model,dict(troubled,ParamAngleZ=angle))
        im=r.render(model,textures,800/1700,(250,0,1950,1530)).resize((500,450),Image.Resampling.LANCZOS)
        board.paste(im,(i*500,row*500+40)); draw.text((i*500+8,row*500+7),f'{label}: Z {angle}',font=font,fill='white')
board.save(out/'native-head-roll.png')
board=Image.new('RGB',(1200,800),(64,72,104)); draw=ImageDraw.Draw(board)
for row,(name,v) in enumerate([q for q in entries if q[0] in ('neutral','troubled')]):
    for col,(model,textures,label) in enumerate(((old,oldtex,'Before'),(new,tex,'v47 native SDK'))):
        pose(model,v); im=r.render(model,textures,1,(650,100,1550,650)).resize((600,366),Image.Resampling.LANCZOS)
        board.paste(im,(col*600,row*400+34)); draw.text((col*600+8,row*400+5),name+' / '+label,font=font,fill='white')
board.save(out/'native-crown-comparison.png')
pose(new,{})
assert np.allclose(base,new.drawables()[[d['id'] for d in new.drawables()].index('Hair_Crown')]['pos'])
v={'stage':'native Cubism SDK export','reset_passed':True,'drawables':92,'expression_poses_including_pending_thinking':12,'combined_motion_poses':81,'other_91_drawable_geometry_preserved':True,'all_opacity_and_draw_order_preserved':True,'common_crown_in_all_expressions':True,'crown_follows_head_and_preserves_hair_sway':True,'crown_vertices':561,'native_crown_changed_pixels':changed,'back_hair_rgb_preserved':True,'back_hair_below_y600_unchanged':True,'materials_changed':['Hair_Crown','Hair_Back'],'unity_applied':False}
(out/'verification.json').write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
print('CROWN_COMPLETION_NATIVE_VERIFIED',len(poses))
