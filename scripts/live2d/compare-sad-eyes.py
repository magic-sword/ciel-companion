"""Compare reference, initial sad eyes and revised eyes from actual Core exports."""
from pathlib import Path
import sys,importlib.util,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
old=cc.Model(sys.argv[1]);new=cc.Model(sys.argv[2]);out=Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=True)
stem=sys.argv[4] if len(sys.argv)>4 else 'eye-refinement'
def pose(m):
    m.reset();assert not m.set({'ParamSad':1,'ParamEarFold':1,'ParamCheek':.2});m.update();return {d['id']:d for d in m.drawables()}
a=pose(old);b=pose(new)
if stem=='lid-shape':
    for side in 'LR':
        for part in ('Iris','Highlight'):
            n=f'Eye_{side}_{part}';assert np.allclose(a[n]['pos'],b[n]['pos'],atol=.001),n
for name in a:
    if name.startswith('Eye_'):continue
    assert np.allclose(a[name]['pos'],b[name]['pos'],atol=.001),name
    assert abs(a[name]['opacity']-b[name]['opacity'])<.001,name
crop=(740,830,1460,1190);w=720;h=360
p=json.loads((ROOT/'assets/ciel/generated/v36/placement.json').read_text());s=p['shared_scale'];ox,oy=p['offset']
ref=Image.open(ROOT/p['reference']).convert('RGB').transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC).crop(crop)
board=Image.new('RGB',(w*3,h+40),(64,72,104));d=ImageDraw.Draw(board);font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',21)
ims=[ref]+[r.render(m,r.load_textures(m),2,crop).resize((w,h),Image.Resampling.LANCZOS) for m in (old,new)]
titles=('見本','前回の候補','上瞼のアーチを見本へ調整') if stem=='lid-shape' else ('見本','初案（瞼のみ調整）','目尻・虹彩・ハイライトを調整')
for i,(title,im) in enumerate(zip(titles,ims)):
    board.paste(im,(i*w,40));d.text((i*w+8,6),title,font=font,fill='white')
board.save(out/(stem+'-comparison.png'))
record={'non_eye_parts_preserved':True,'new_material_generation':False,'iris_highlight_preserved':stem=='lid-shape'}
if stem=='lid-shape':
    reference=np.asarray(Image.open(ROOT/p['reference']).convert('RGB').transform((2172,2896),Image.Transform.AFFINE,(1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC))
    metrics={}
    for side,xs in [('R',range(820,971,25)),('L',range(1235,1386,25))]:
        target=[930+np.flatnonzero(reference[930:1080,x,:].max(1)<110)[0] for x in xs]
        metrics[side]={}
        for label,m,ds in [('before',old,a),('after',new,b)]:
            textures=r.load_textures(m);lash=ds[f'Eye_{side}_LashUpper']
            alpha=r.raster(lash,textures[lash['texture']],720,200,1,np.array([740,930]))[:,:,3]
            trace=[930+np.flatnonzero(alpha[:150,x-740]>.5)[0] for x in xs]
            metrics[side][label]=float(np.mean(np.abs(np.array(trace)-target)))
        assert metrics[side]['after']<metrics[side]['before'],metrics
    record['reference_lash_top_mean_error_px']=metrics
(out/(stem+'-verification.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print('SAD_EYE_COMPARISON_READY')
