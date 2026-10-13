"""Measure rendered lower ink against the white mask, with neutral/happy reset guards."""
from pathlib import Path
import sys,importlib.util,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
new=cc.Model(sys.argv[1]);old=cc.Model(ROOT/'.local/lower-lid-integration/export/Ciel.model3.json')
out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True);tex=r.load_textures(new)
def pose(m,values):
    m.reset();assert not m.set(values);m.update();return {d['id']:d for d in m.drawables()}
new_ids=[f'Eye_{s}_RelaxedLowerLine' for s in 'LR']
for values in ({},{'ParamHappy':1,'ParamEyeLSmile':1,'ParamEyeRSmile':1},{'ParamRelaxed':1,'ParamEyeLOpen':0,'ParamEyeROpen':0}):
    a=pose(old,values);b=pose(new,values)
    for name in a:
        assert np.allclose(a[name]['pos'],b[name]['pos'],atol=.001),name
        assert abs(a[name]['opacity']-b[name]['opacity'])<.001,name
    assert all(b[n]['opacity']<.001 for n in new_ids)
measurements={}
for opening in (.5,1):
    values={'ParamRelaxed':1,'ParamEyeLOpen':opening,'ParamEyeROpen':opening}
    ds=pose(new,values);previous=pose(old,values)
    for side in 'LR':
        for part in ('Iris','Sclera'):
            name=f'Eye_{side}_{part}'
            assert np.allclose(ds[name]['pos'],previous[name]['pos'],atol=.001),name
    for side in 'LR':
        assert ds[f'Eye_{side}_LidSkin_Lower']['opacity']<.001
        assert ds[f'Eye_{side}_LashLower']['opacity']<.001
        assert ds[f'Eye_{side}_RelaxedLowerLine']['opacity']>.99
        off=np.array((740,950));white=ds[f'Eye_{side}_Sclera'];line=ds[f'Eye_{side}_RelaxedLowerLine']
        wa=r.raster(white,tex[white['texture']],730,240,1,off)[:,:,3]
        la=r.raster(line,tex[line['texture']],730,240,1,off)[:,:,3]
        cols=np.flatnonzero(la.sum(axis=0)>.25);gaps=[]
        for col in cols:
            wy=np.flatnonzero(wa[:,col]>.5)
            if not len(wy):continue
            center=np.average(np.arange(240),weights=la[:,col]);gaps.append(float(center-wy.max()))
        assert len(gaps)>30,(side,'not enough visible lower line')
        p95=float(np.percentile(np.abs(gaps),95));assert p95<3.0,(side,opening,p95)
        measurements[f'{side}_open_{opening}']={'columns':len(gaps),'gap_abs_p95_px':p95,'gap_median_px':float(np.median(gaps))}
pose(new,{'ParamRelaxed':1});crop=(550,650,1600,1700)
face=r.render(new,tex,.5,crop,(64,72,104));face.save(out/'relaxed-face.png')
pose(old,{'ParamRelaxed':1});oldface=r.render(old,r.load_textures(old),.5,crop,(64,72,104))
board=Image.new('RGB',(1050,565),(64,72,104));draw=ImageDraw.Draw(board);font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',21)
for i,(label,im) in enumerate([('更新前',oldface),('肌の帯を除去・境界線を一致',face)]):
    board.paste(im,(i*525,40));draw.text((i*525+8,8),label,font=font,fill='white')
board.save(out/'boundary-comparison.png')
(out/'boundary-verification.json').write_text(json.dumps({'neutral_happy_and_closed_blink_preserved':True,
    'lower_skin_hidden_in_relaxed':True,'iris_geometry_unchanged':True,'rendered_edge_measurements':measurements},indent=2)+'\n',encoding='utf-8')
print('LID_BOUNDARY_CHECK_PASSED',json.dumps(measurements))
