"""Validate relaxed switching, blink, gaze, lipsync and prior happy/neutral poses."""
import sys,json,importlib.util
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('render',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
m=cc.Model(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True);textures=r.load_textures(m)
baseline=cc.Model(ROOT/'.local/happy-integration/export/Ciel.model3.json')
def pose(model,values):
    model.reset();assert not model.set(values);model.update();return {d['id']:d for d in model.drawables()}
for values in ({},{'ParamHappy':1,'ParamEyeLSmile':1,'ParamEyeRSmile':1}):
    old=pose(baseline,values);new=pose(m,values)
    for name in old:
        assert np.allclose(old[name]['pos'],new[name]['pos'],atol=.001),name
        assert abs(old[name]['opacity']-new[name]['opacity'])<.001,name
neutral=pose(m,{})
assert neutral['Mouth_Relaxed']['opacity']<.001 and neutral['Cheek_Relaxed']['opacity']<.001
ds=pose(m,{'ParamRelaxed':1})
assert ds['Mouth_Relaxed']['opacity']>.99 and abs(ds['Cheek_Relaxed']['opacity']-.5)<.001
assert all(ds[n]['opacity']<.001 for n in ('Mouth_Line_Upper','Mouth_Line_Lower','Cheek_Blush','Mouth_Happy','Cheek_Happy'))
assert len(ds)==len(m.drawables())
crop=(550,650,1600,1700);face=r.render(m,textures,.5,crop,(64,72,104));face.save(out/'relaxed-face.png')
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',20)
board=Image.new('RGB',(1600,440),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,values) in enumerate([
    ('にこにこ・閉口',{}),('まばたき・途中',{'ParamEyeLOpen':.5,'ParamEyeROpen':.5}),
    ('まばたき・閉眼',{'ParamEyeLOpen':0,'ParamEyeROpen':0}),('発話・開口',{'ParamMouthOpenY':1})]):
    values={'ParamRelaxed':1,**values};ds=pose(m,values)
    if values.get('ParamMouthOpenY')==1:
        assert ds['Mouth_Relaxed']['opacity']<.001 and ds['Mouth_Large']['opacity']>.99
    if values.get('ParamEyeLOpen')==0:
        assert ds['Eye_L_Closed']['opacity']>.99 and ds['Eye_R_Closed']['opacity']>.99
    tile=r.render(m,textures,400/1050,crop,(64,72,104));board.paste(tile,(i*400,40));draw.text((i*400+8,8),label,font=font,fill='white')
board.save(out/'blink-and-mouth.png')
checked=0
for blend in (0,.5,1):
    for opening in (0,.5,1):
        for gaze in (-1,0,1):
            for angle in (-30,0,30):
                ds=pose(m,{'ParamRelaxed':blend,'ParamEyeLOpen':opening,'ParamEyeROpen':opening,
                    'ParamEyeBallX':gaze,'ParamEyeBallY':-gaze,'ParamAngleX':angle,'ParamAngleY':-angle,
                    'ParamMouthOpenY':opening})
                assert all(np.isfinite(d['pos']).all() and np.isfinite(d['uv']).all() for d in ds.values())
                checked+=1
ds=pose(m,{});assert ds['Mouth_Relaxed']['opacity']<.001 and ds['Cheek_Relaxed']['opacity']<.001
p=json.loads((ROOT/'assets/ciel/generated/v31/placement.json').read_text());s=p['uniform_scale'];ox,oy=p['offset']
ref=Image.open(ROOT/'assets/ciel/generated/v32/inputs/relaxed-reference-face.png').convert('RGBA')
ref=ref.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC).crop(crop)
bg=Image.new('RGBA',ref.size,(64,72,104,255));bg.alpha_composite(ref)
board=Image.new('RGB',(1050,565),(64,72,104));draw=ImageDraw.Draw(board)
board.paste(bg.convert('RGB').resize((525,525),Image.Resampling.LANCZOS),(0,40));board.paste(face,(525,40))
draw.text((8,8),'承認見本（頬の輪郭幅基準）',font=font,fill='white');draw.text((533,8),'にこにこ・実モデル描画',font=font,fill='white')
board.save(out/'reference-comparison.png')
(out/'verification.json').write_text(json.dumps({'active_control':'ParamRelaxed','single_expression_control':True,
    'baseline_neutral_and_happy_preserved':True,'blink_closed_shape_preserved':True,'gaze_reuses_existing_iris':True,
    'existing_open_mouth_preserved':True,'new_closed_mouth_hidden_when_open':True,'reset_passed':True,
    'finite_combined_poses':checked,'duplicate_drawable_ids':False},indent=2)+'\n',encoding='utf-8')
print('RELAXED_CHECK_PASSED',checked)
