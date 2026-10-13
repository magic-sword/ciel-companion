"""Verify that only the angry brow position changed; render an enlarged comparison."""
from pathlib import Path
import sys,importlib.util,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
old=cc.Model(sys.argv[1]);new=cc.Model(sys.argv[2]);out=Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=True)
values={'ParamAngry':1,'ParamEarFold':1,'ParamCheek':.2}
def pose(m):
    m.reset();assert not m.set(values);m.update();return {d['id']:d for d in m.drawables()}
a=pose(old);b=pose(new);delta=b['Brow_Angry']['pos']-a['Brow_Angry']['pos']
assert np.allclose(delta,[0,-32],atol=.01),delta
for name in a:
    assert np.array_equal(a[name]['uv'],b[name]['uv']),name
    assert abs(a[name]['opacity']-b[name]['opacity'])<.0001,name
    if name!='Brow_Angry':assert np.allclose(a[name]['pos'],b[name]['pos'],atol=.001),name
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',22);crop=(740,800,1460,1190)
board=Image.new('RGB',(1440,430),(64,72,104));d=ImageDraw.Draw(board)
overlaps={}
for i,(title,m,ds) in enumerate([('変更前',old,a),('眉だけを上へ32px移動',new,b)]):
    textures=r.load_textures(m)
    im=r.render(m,textures,2,crop).resize((720,390),Image.Resampling.LANCZOS)
    board.paste(im,(720*i,40));d.text((720*i+8,7),title,font=font,fill='white')
    brow=ds['Brow_Angry'];ba=r.raster(brow,textures[brow['texture']],720,390,1,np.array(crop[:2]))[:,:,3]*brow['opacity']
    overlaps[title]={}
    for side in 'LR':
        crease=ds[f'Eye_{side}_Crease'];ca=r.raster(crease,textures[crease['texture']],720,390,1,np.array(crop[:2]))[:,:,3]*crease['opacity']
        overlaps[title][side]=int(np.count_nonzero((ba>.05)&(ca>.05)))
board.save(out/'brow-position-comparison.png')
(out/'brow-position-verification.json').write_text(json.dumps({'brow_translation_canvas_pixels':delta.mean(0).tolist(),'all_other_meshes_preserved':True,'uv_and_opacity_preserved':True,'brow_crease_overlap_pixels':overlaps},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('BROW_POSITION_CHECK_PASSED',delta.mean(0))
