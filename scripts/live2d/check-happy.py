"""Check the real exported happy rig, original-material hiding and reset."""
import json,sys,importlib.util
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cubism_core as cc
spec=importlib.util.spec_from_file_location('render',HERE/'render-moc.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
model=cc.Model(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
textures=r.load_textures(model)
happy={'ParamHappy':1,'ParamEyeLSmile':1,'ParamEyeRSmile':1}
new=('Cheek_Happy','Mouth_Happy','Nose_Happy','Eye_L_Happy','Eye_R_Happy')
model.reset();model.update();neutral={d['id']:d for d in model.drawables()}
assert all(neutral[n]['opacity']<.001 for n in new)
assert 'ParamHappy' in model.param_range
model.set(happy);model.update();ds={d['id']:d for d in model.drawables()}
assert len(ds)==len(model.drawables()),'duplicate drawable ids'
assert all(ds[n]['opacity']>.99 for n in new)
old=[n for n in ds if (n.startswith(('Mouth_','Eye_L_','Eye_R_')) and n not in new) or n in ('Cheek_Blush','Nose')]
assert all(ds[n]['opacity']<.001 for n in old)
assert all(np.isfinite(d['pos']).all() for d in ds.values())
crop=(550,650,1600,1700)
face=r.render(model,textures,.5,crop,(64,72,104));face.save(out/'happy-face.png')
baseline=cc.Model(ROOT/'unity/Assets/Characters/Ciel/Ciel.model3.json');baseline.reset();baseline.update()
baseline_ds={d['id']:d for d in baseline.drawables()}
unchanged=[n for n in baseline_ds if n not in ('Eye_L_Happy','Eye_R_Happy')]
for n in unchanged:
    assert np.allclose(neutral[n]['pos'],baseline_ds[n]['pos'],atol=.001),n
    assert abs(neutral[n]['opacity']-baseline_ds[n]['opacity'])<.001,n
image=r.render(model,textures,.5,(100,-110,2070,1530),(64,72,104));image.save(out/'happy.png')
for level in (0,.25,.5,.75,1):
    for angle in (-30,0,30):
        for mouth in (0,.5,1):
            model.reset();model.set({'ParamHappy':level,'ParamEyeLSmile':level,'ParamEyeRSmile':level,
                'ParamAngleX':angle,'ParamAngleY':-angle,'ParamMouthOpenY':mouth});model.update()
            assert all(np.isfinite(d['pos']).all() for d in model.drawables())
model.reset();model.update();reset={d['id']:d for d in model.drawables()}
assert all(reset[n]['opacity']<.001 for n in new)
for name in ('Mouth_Large','Nose'):
    assert abs(reset[name]['opacity']-neutral[name]['opacity'])<.001
reference=Image.open(ROOT/'assets/ciel/generated/v22/expressions/happy.png').convert('RGBA')
bg=Image.new('RGBA',reference.size,(64,72,104,255));bg.alpha_composite(reference);ref=bg.convert('RGB');ref.thumbnail(image.size)
board=Image.new('RGB',(image.width*2,image.height+40),(64,72,104));draw=ImageDraw.Draw(board)
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',24)
board.paste(ref,((image.width-ref.width)//2,40+(image.height-ref.height)//2));board.paste(image,(image.width,40))
draw.text((10,7),'承認見本',font=font,fill='white');draw.text((image.width+10,7),'Cubism書き出し後の実描画',font=font,fill='white')
board.save(out/'reference-comparison.png')
reference_face=Image.open(ROOT/'assets/ciel/generated/v30/inputs/happy-reference-face.png').convert('RGBA')
placement=json.loads((ROOT/'assets/ciel/generated/v31/placement.json').read_text())
s=placement['uniform_scale'];ox,oy=placement['offset']
aligned=reference_face.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC).crop(crop)
bg=Image.new('RGBA',aligned.size,(64,72,104,255));bg.alpha_composite(aligned)
board=Image.new('RGB',(1050,565),(64,72,104));draw=ImageDraw.Draw(board)
board.paste(bg.convert('RGB').resize((525,525),Image.Resampling.LANCZOS),(0,40));board.paste(face,(525,40))
draw.text((8,7),'見本（頬の輪郭幅を基準）',font=font,fill='white');draw.text((533,7),'Cubism書き出し後の実描画',font=font,fill='white')
board.save(out/'face-comparison.png')
(out/'verification.json').write_text(json.dumps({'model':sys.argv[1],'active_controls':happy,
    'new_drawables':list(new),'old_drawables_hidden':old,'interpolated_poses':45,
    'neutral_reset_passed':True,'duplicate_drawable_ids':False,'finite_vertices':True,
    'existing_neutral_geometry_and_opacity_preserved':len(unchanged)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('HAPPY_RIG_CHECK_PASSED')
