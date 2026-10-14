"""Validate the embarrassed export, earlier expressions, and existing blink/gaze/speaking."""
from pathlib import Path
import sys,importlib.util,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE));import cubism_core as cc
from embarrassed_eye_shapes import eye_delta
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
old=cc.Model(ROOT/'assets/ciel/runtime/Ciel.model3.json');new=cc.Model(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True);tex=r.load_textures(new)
def pose(m,v):
    m.reset();assert not m.set(v);m.update();return {d['id']:d for d in m.drawables()}
def render(m,textures,scale,crop):
    im=r.render(m,textures,scale*2,crop);return im.resize((int((crop[2]-crop[0])*scale),int((crop[3]-crop[1])*scale)),Image.Resampling.LANCZOS)
poses=[{}, {'ParamHappy':1,'ParamEyeLSmile':1,'ParamEyeRSmile':1},{'ParamRelaxed':1},{'ParamSurprised':1},{'ParamAngry':1,'ParamEarFold':1},{'ParamSad':1,'ParamEarFold':1},{'ParamTroubled':1,'ParamEarFold':1},{'ParamRelaxed':1,'ParamEyeLOpen':0,'ParamEyeROpen':0}]
for v in poses:
    a=pose(old,v);b=pose(new,v)
    for name in a:
        assert np.allclose(a[name]['pos'],b[name]['pos'],atol=.001),name
        assert abs(a[name]['opacity']-b[name]['opacity'])<.001,name
    assert all(b[n]['opacity']<.001 for n in ('Mouth_Embarrassed','Brow_Embarrassed','Cheek_Embarrassed'))
values={'ParamEmbarrassed':1,'ParamEarFold':1,'ParamCheek':0};a=pose(old,{});b=pose(new,values)
assert all(b[n]['opacity']>.99 for n in ('Mouth_Embarrassed','Brow_Embarrassed','Cheek_Embarrassed'))
assert b['Sweat']['opacity']<.001
assert all(b[n]['opacity']<.001 for n in ('Brow_R','Brow_L','Brow_Angry','Mouth_Angry','Mouth_Line_Upper','Mouth_Line_Lower'))
for side in 'LR':
    for part in ('Iris','Highlight'):
        n=f'Eye_{side}_{part}'
        cx=1285 if side=='L' else 920
        expected_x=a[n]['pos'][:,0]+(a[n]['pos'][:,0]-cx)*(-.10 if side=='L' else -.18)+(40 if side=='L' else 24)
        assert np.allclose(expected_x,b[n]['pos'][:,0],atol=1),n
        assert np.allclose(b[n]['pos'][:,1],a[n]['pos'][:,1]+eye_delta(side,part,a[n]['pos']),atol=1),n
    assert b[f'Ear_{side}_Folded']['opacity']>.99
    assert all(b[f'Ear_{side}_{p}']['opacity']<.001 for p in ('Outer','Inner','Base'))
crop=(200,50,1950,1550);scale=.35;w=int(1750*scale);h=int(1500*scale);font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',21)
face=render(new,tex,scale,crop);face.save(out/'embarrassed.png');render(new,tex,.75,(550,650,1600,1700)).save(out/'embarrassed-face.png')
p=json.loads((ROOT/'assets/ciel/generated/v38/placement.json').read_text());s=p['shared_scale'];ox,oy=p['offset']
ref=Image.open(ROOT/p['reference']).convert('RGBA').transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC).crop(crop)
bg=Image.new('RGBA',ref.size,(64,72,104,255));bg.alpha_composite(ref)
pose(old,{'ParamCheek':1,'ParamMouthForm':.2,'ParamEyeBallX':.6,'ParamEar':-.3})
before=render(old,r.load_textures(old),scale,crop);board=Image.new('RGB',(w*3,h+40),(64,72,104));d=ImageDraw.Draw(board)
for i,(title,im) in enumerate([('見本（鼻・顎を基準に配置）',bg.convert('RGB').resize((w,h),Image.Resampling.LANCZOS)),('調整前',before),('照れ・赤みと目線を調整',face)]):
    board.paste(im,(w*i,40));d.text((w*i+8,6),title,font=font,fill='white')
board.save(out/'reference-comparison.png')
board=Image.new('RGB',(1600,440),(64,72,104));d=ImageDraw.Draw(board);crop=(550,650,1600,1700)
for i,(title,extra) in enumerate([('開眼',{}),('半まばたき',{'ParamEyeLOpen':.5,'ParamEyeROpen':.5}),('閉眼',{'ParamEyeLOpen':0,'ParamEyeROpen':0}),('発話',{'ParamMouthOpenY':1})]):
    ds=pose(new,{**values,**extra})
    if extra.get('ParamEyeLOpen')==0:assert ds['Eye_L_Closed']['opacity']>.99 and ds['Eye_R_Closed']['opacity']>.99
    if extra.get('ParamMouthOpenY')==1:assert ds['Mouth_Embarrassed']['opacity']<.001 and ds['Mouth_Large']['opacity']>.99
    board.paste(render(new,tex,400/1050,crop),(i*400,40));d.text((i*400+8,6),title,font=font,fill='white')
board.save(out/'blink-and-mouth.png')
count=0
for level in (0,.5,1):
    for opening in (0,.5,1):
        for gaze in (-1,0,1):
            for angle in (-30,0,30):
                ds=pose(new,{**values,'ParamEmbarrassed':level,'ParamEyeLOpen':opening,'ParamEyeROpen':opening,'ParamEyeBallX':gaze,'ParamEyeBallY':-gaze,'ParamAngleX':angle,'ParamAngleY':-angle})
                assert all(np.isfinite(q['pos']).all() and np.isfinite(q['uv']).all() for q in ds.values());count+=1
board=Image.new('RGB',(1350,425),(64,72,104));d=ImageDraw.Draw(board)
for i,angle in enumerate((-30,0,30)):
    pose(new,{**values,'ParamAngleX':angle,'ParamAngleY':angle});board.paste(render(new,tex,450/1750,(200,50,1950,1550)),(i*450,40));d.text((i*450+8,6),f'Angle X/Y {angle}',font=font,fill='white')
board.save(out/'head-angles.png')
(out/'verification.json').write_text(json.dumps({'previous_poses_preserved':len(poses),'drawables':len(ds),'iris_highlight_base_transform':{'y_scale':.95,'pivot_y':1070,'y_offset':20,'highlight_y_offset':35,'x_scale':{'R':.82,'L':.9},'x_offset':{'R':24,'L':40},'iris_top_extension_px':18},'folded_ears_reused':True,'blink_preserved':True,'speaking_mouth_preserved':True,'finite_combined_poses':count},indent=2)+'\n',encoding='utf-8');print('EMBARRASSED_CHECK_PASSED',count)
