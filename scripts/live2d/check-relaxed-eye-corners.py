"""Verify the localized lash edit and compare actual exported renders."""
from pathlib import Path
import sys,importlib.util,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE));import cubism_core as cc
sp=importlib.util.spec_from_file_location('renderer',HERE/'render-moc.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
old=cc.Model(ROOT/'.local/lid-boundary-integration/export/Ciel.model3.json');new=cc.Model(sys.argv[1])
out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
def pose(m,v):
    m.reset();assert not m.set(v);m.update();return {d['id']:d for d in m.drawables()}
changed=set();tail_metrics={};tex=r.load_textures(new);oldtex=r.load_textures(old)
for values in ({},{'ParamHappy':1,'ParamEyeLSmile':1,'ParamEyeRSmile':1},
               {'ParamRelaxed':1,'ParamEyeLOpen':0,'ParamEyeROpen':0},
               {'ParamRelaxed':1,'ParamEyeLOpen':.5,'ParamEyeROpen':.5},{'ParamRelaxed':1}):
    a=pose(old,values);b=pose(new,values)
    active=values.get('ParamRelaxed')==1 and values.get('ParamEyeLOpen',1)>0
    assert a.keys()==b.keys()
    for name in a:
        assert abs(a[name]['opacity']-b[name]['opacity'])<.001,name
        same=np.allclose(a[name]['pos'],b[name]['pos'],atol=.001)
        if active and name in ('Eye_L_LashUpper','Eye_R_LashUpper'):
            assert not same,name;changed.add(name)
            x=a[name]['pos'][:,0]
            mask=x<=1350 if '_L_' in name else x>=860
            assert np.allclose(a[name]['pos'][mask],b[name]['pos'][mask],atol=.001),name
            assert np.allclose(a[name]['pos'][:,0],b[name]['pos'][:,0],atol=.001),name
            def area(d):
                p=d['pos'][d['tri']];u=p[:,1]-p[:,0];v=p[:,2]-p[:,0]
                return u[:,0]*v[:,1]-u[:,1]*v[:,0]
            ar,br=area(a[name]),area(b[name]);valid=np.abs(ar)>.01
            assert np.all(ar[valid]*br[valid]>0),(name,'folded triangles')
        else:assert same,name
a=pose(old,{'ParamRelaxed':1});b=pose(new,{'ParamRelaxed':1})
for side in 'LR':
    name=f'Eye_{side}_LashUpper';region=(1360,950) if side=='L' else (740,950)
    ends=[]
    for ds,textures in ((a,oldtex),(b,tex)):
        d=ds[name];alpha=r.raster(d,textures[d['texture']],110,240,1,np.array(region))[:,:,3]
        yy,xx=np.nonzero(alpha>.5);assert len(yy);ends.append(int(yy.max()+950))
    assert ends[0]-ends[1]>12,(side,ends)
    tail_metrics[side]={'before_bottom_y':ends[0],'after_bottom_y':ends[1],'shortened_px':ends[0]-ends[1]}
crop=(550,650,1600,1700);font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',21)
board=Image.new('RGB',(1050,565),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,model,textures) in enumerate([('目尻の調整前（v33）',old,oldtex),('目尻の下向きを短く調整',new,tex)]):
    pose(model,{'ParamRelaxed':1});face=r.render(model,textures,.5,crop,(64,72,104))
    board.paste(face,(525*i,40));draw.text((525*i+8,8),label,font=font,fill='white')
board.save(out/'eye-corner-comparison.png')
(out/'eye-corner-verification.json').write_text(json.dumps({'changed_meshes':sorted(changed),
    'iris_white_lower_lid_unchanged':True,'central_upper_lash_unchanged':True,
    'neutral_happy_closed_blink_unchanged':True,'tail_metrics':tail_metrics},indent=2)+'\n',encoding='utf-8')
print('EYE_CORNER_CHECK_PASSED',json.dumps(tail_metrics))
