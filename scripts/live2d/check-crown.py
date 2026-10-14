"""Check the native common crown, expression poses and inherited head/hair motion."""
from pathlib import Path
import importlib.util,json,sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
m=cc.Model(sys.argv[1]);out=Path(sys.argv[2]);tex=r.load_textures(m);font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',18)
def pose(values):
    m.reset();assert not m.set(values);m.update();return {d['id']:d for d in m.drawables()}
base=pose({})['Hair_Crown'];assert base['opacity']>.99 and len(m.drawables())==92
for pid in ('ParamAngleX','ParamAngleY','ParamAngleZ'):
    lo,default,hi=m.param_range[pid]
    ds=pose({pid:hi});assert not np.allclose(base['pos'],ds['Hair_Crown']['pos']),pid
    assert np.isfinite(ds['Hair_Crown']['pos']).all()
ds=pose({'ParamHairBack':1})
assert np.allclose(base['pos'],ds['Hair_Crown']['pos'],atol=.05), 'Crown root should remain anchored during lower-hair sway'
recipes=ROOT/'assets/ciel/rig/drafts/jitome/runtime/Expressions'
if not recipes.exists():recipes=ROOT/'assets/ciel/runtime/Expressions'
files=sorted(recipes.glob('*.json'));assert len(files)==11
entries=[(path.name.replace('.exp3.json',''),{p['Id']:p['Value'] for p in json.loads(path.read_text(encoding='utf-8'))['Parameters']}) for path in files]
entries.append(('thinking (pending)',{'ParamEyeBallX':-.5,'ParamEyeBallY':.6,'ParamBrowLY':.4,'ParamMouthForm':-.3}))
board=Image.new('RGB',(1600,3*440),(64,72,104));draw=ImageDraw.Draw(board)
for i,(name,values) in enumerate(entries):
    ds=pose(values);assert ds['Hair_Crown']['opacity']>.99
    crop=(250,0,1950,1700);im=r.render(m,tex,800/1700,crop).resize((400,400),Image.Resampling.LANCZOS)
    board.paste(im,(i%4*400,i//4*440+40));draw.text((i%4*400+8,i//4*440+7),name,font=font,fill='white')
board.save(out/'all-expressions.png')
board=Image.new('RGB',(1500,480),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,values) in enumerate([('Angle X -30',{'ParamAngleX':-30}),('Angle Y +30',{'ParamAngleY':30}),('Hair back +1',{'ParamHairBack':1})]):
    pose(values);im=r.render(m,tex,1000/1700,(250,0,1950,1450)).resize((500,426),Image.Resampling.LANCZOS)
    board.paste(im,(500*i,40));draw.text((500*i+8,7),label,font=font,fill='white')
board.save(out/'crown-head-and-hair.png')
path=out/'verification.json';v=json.loads(path.read_text(encoding='utf-8'))
v.update(common_crown_in_all_expressions=True,crown_follows_head_and_preserves_hair_sway=True,crown_root_anchored_during_hair_sway=True,
    adopted_expression_poses=len(files),expression_poses_including_pending_thinking=len(entries),common_crown_motion_controls=['ParamAngleX','ParamAngleY','ParamAngleZ','ParamHairBack'])
path.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8');print('COMMON_CROWN_CHECK_PASSED',len(entries))
