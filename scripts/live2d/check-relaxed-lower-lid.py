"""Compare the lower-lid adjustment to v32 and show unchanged upper rims/blinks."""
from pathlib import Path
import sys,json,importlib.util
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
before=cc.Model(ROOT/'.local/relaxed-integration/export/Ciel.model3.json');after=cc.Model(sys.argv[1])
out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
def pose(model,values):
    model.reset();assert not model.set(values);model.update();return {d['id']:d for d in model.drawables()}
for values in ({},{'ParamHappy':1,'ParamEyeLSmile':1,'ParamEyeRSmile':1},
               {'ParamRelaxed':1,'ParamEyeLOpen':0,'ParamEyeROpen':0}):
    a=pose(before,values);b=pose(after,values)
    for n in a:
        assert np.allclose(a[n]['pos'],b[n]['pos'],atol=.001),n
        assert abs(a[n]['opacity']-b[n]['opacity'])<.001,n
a=pose(before,{'ParamRelaxed':1});b=pose(after,{'ParamRelaxed':1})
changed=[]
for n in a:
    if not np.allclose(a[n]['pos'],b[n]['pos'],atol=.001):changed.append(n)
expected=[f'Eye_{s}_{p}' for s in 'LR' for p in ('Sclera','LidSkin_Lower','LashLower')]
assert set(changed)==set(expected),(changed,expected)
for s in 'LR':
    # The top row of the white mesh is unmodified, even though its bottom changes.
    n=f'Eye_{s}_Sclera';top=a[n]['pos'][:,1].min();mask=np.abs(a[n]['pos'][:,1]-top)<2
    assert np.allclose(a[n]['pos'][mask],b[n]['pos'][mask],atol=.001)
crop=(550,650,1600,1700);textures=r.load_textures(after)
face=r.render(after,textures,.5,crop,(64,72,104));face.save(out/'relaxed-face.png')
old=r.render(before,r.load_textures(before),.5,crop,(64,72,104))
reference=Image.open(ROOT/'assets/ciel/generated/v32/inputs/relaxed-reference-face.png').convert('RGBA')
p=json.loads((ROOT/'assets/ciel/generated/v31/placement.json').read_text());s=p['uniform_scale'];ox,oy=p['offset']
ref=reference.transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC).crop(crop)
bg=Image.new('RGBA',ref.size,(64,72,104,255));bg.alpha_composite(ref)
board=Image.new('RGB',(1575,565),(64,72,104));draw=ImageDraw.Draw(board);font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',21)
for i,(label,im) in enumerate([('承認見本',bg.convert('RGB').resize((525,525),Image.Resampling.LANCZOS)),('調整前（v32）',old),('下まぶたの中央を調整',face)]):
    board.paste(im,(525*i,40));draw.text((525*i+8,8),label,font=font,fill='white')
board.save(out/'lower-lid-comparison.png')
(out/'lower-lid-verification.json').write_text(json.dumps({'changed_meshes':changed,'upper_rims_unchanged':True,
    'neutral_and_happy_unchanged':True,'closed_blink_unchanged':True,'extra_lift_px':18},indent=2)+'\n',encoding='utf-8')
print('LOWER_LID_CHECK_PASSED')
