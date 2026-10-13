"""Validate the actual surprise export and preserve previously approved poses."""
from pathlib import Path
import sys,importlib.util,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
old=cc.Model(sys.argv[3] if len(sys.argv)>3 else ROOT/'assets/ciel/runtime/Ciel.model3.json');new=cc.Model(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
tex=r.load_textures(new)
def pose(m,v):
    m.reset();assert not m.set(v);m.update();return {d['id']:d for d in m.drawables()}
for v in ({},{'ParamHappy':1,'ParamEyeLSmile':1,'ParamEyeRSmile':1},{'ParamRelaxed':1},
          {'ParamRelaxed':1,'ParamEyeLOpen':0,'ParamEyeROpen':0}):
    a=pose(old,v);b=pose(new,v)
    for name in a:
        assert np.allclose(a[name]['pos'],b[name]['pos'],atol=.001),name
        assert abs(a[name]['opacity']-b[name]['opacity'])<.001,name
    assert b['Mouth_Surprised']['opacity']<.001
values={'ParamSurprised':1,'ParamEar':1,'ParamBrowLY':.8,'ParamBrowRY':.8,'ParamCheek':.15}
a=pose(old,{});b=pose(new,values);metrics={}
for side in 'LR':
    n=f'Eye_{side}_Iris';ratio=np.ptp(b[n]['pos'],axis=0)/np.ptp(a[n]['pos'],axis=0)
    assert np.allclose(ratio,[.7,.742],atol=.002),(side,ratio)
    n=f'Eye_{side}_Sclera';height=np.ptp(b[n]['pos'][:,1])/np.ptp(a[n]['pos'][:,1]);assert height>1.10,(side,height)
    metrics[side]={'iris_width_ratio':float(ratio[0]),'iris_height_ratio':float(ratio[1]),'white_height_ratio':float(height)}
    iris=b[f'Eye_{side}_Iris'];white=b[f'Eye_{side}_Sclera'];off=np.array((740,940))
    ia=r.raster(iris,tex[iris['texture']],730,280,1,off)[:,:,3]
    wa=r.raster(white,tex[white['texture']],730,280,1,off)[:,:,3]
    yy,xx=np.nonzero(ia>.5);col=int((xx.min()+xx.max())/2)
    gap=int(np.flatnonzero(wa[:,col]>.5).max()-np.flatnonzero(ia[:,col]>.5).max())
    assert 5<=gap<=20,(side,'lower white margin',gap)
    metrics[side]['lower_white_margin_px']=gap
assert b['Mouth_Surprised']['opacity']>.99
assert all(b[n]['opacity']<.001 for n in ('Mouth_Line_Upper','Mouth_Line_Lower','Mouth_Small','Mouth_Happy','Mouth_Relaxed'))
crop=(550,650,1600,1700);face=r.render(new,tex,.5,crop);face.save(out/'surprised-face.png')
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',20)
p=json.loads((ROOT/'assets/ciel/generated/v34/placement.json').read_text());s=p['shared_scale'];ox,oy=p['offset']
ref=Image.open(ROOT/p['source']).convert('RGBA').transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC).crop(crop)
bg=Image.new('RGBA',ref.size,(64,72,104,255));bg.alpha_composite(ref)
pose(old,{'ParamEar':1,'ParamBrowLY':.8,'ParamBrowRY':.8,'ParamMouthOpenY':.3})
before=r.render(old,r.load_textures(old),.5,crop)
board=Image.new('RGB',(1575,565),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,im) in enumerate([('見本（鼻・顎で位置合わせ）',bg.convert('RGB').resize((525,525),Image.Resampling.LANCZOS)),('調整前',before),('驚き：専用キーと丸口',face)]):
    board.paste(im,(525*i,40));draw.text((525*i+8,8),label,font=font,fill='white')
board.save(out/'reference-comparison.png')
board=Image.new('RGB',(1600,440),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,extra) in enumerate([('驚き・開眼',{}),('半閉眼',{'ParamEyeLOpen':.5,'ParamEyeROpen':.5}),('閉眼',{'ParamEyeLOpen':0,'ParamEyeROpen':0}),('発話・開口',{'ParamMouthOpenY':1})]):
    ds=pose(new,{**values,**extra})
    if extra.get('ParamEyeLOpen')==0:assert ds['Eye_L_Closed']['opacity']>.99 and ds['Eye_R_Closed']['opacity']>.99
    if extra.get('ParamMouthOpenY')==1:assert ds['Mouth_Surprised']['opacity']<.001 and ds['Mouth_Large']['opacity']>.99
    board.paste(r.render(new,tex,400/1050,crop),(i*400,40));draw.text((i*400+8,8),label,font=font,fill='white')
board.save(out/'blink-and-mouth.png')
checked=0
for level in (0,.5,1):
    for opening in (0,.5,1):
        for gaze in (-1,0,1):
            for angle in (-30,0,30):
                ds=pose(new,{'ParamSurprised':level,'ParamEyeLOpen':opening,'ParamEyeROpen':opening,'ParamEyeBallX':gaze,
                    'ParamEyeBallY':-gaze,'ParamAngleX':angle,'ParamAngleY':-angle,'ParamMouthOpenY':opening})
                assert all(np.isfinite(d['pos']).all() and np.isfinite(d['uv']).all() for d in ds.values());checked+=1
assert pose(new,{})['Mouth_Surprised']['opacity']<.001
(out/'verification.json').write_text(json.dumps({'neutral_happy_relaxed_preserved':True,'iris_white_metrics':metrics,
    'blink_preserved':True,'existing_open_mouth_preserved':True,'finite_combined_poses':checked,'reset_passed':True},indent=2)+'\n',encoding='utf-8')
print('SURPRISED_CHECK_PASSED',checked,json.dumps(metrics))
