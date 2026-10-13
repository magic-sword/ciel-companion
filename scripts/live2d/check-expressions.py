"""Render the actual exported rig beside v22 references and check expression controls.

Usage: python -B scripts/live2d/check-expressions.py model.model3.json output-directory
Reads Unity's expression table so previews use the same parameter units.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import cubism_core as cc
spec = importlib.util.spec_from_file_location('render_moc', HERE/'render-moc.py')
renderer = importlib.util.module_from_spec(spec); spec.loader.exec_module(renderer)


def main():
    modelpath, output = sys.argv[1:3]
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    source = (ROOT/'unity/Assets/Scripts/Conversation/CielExpression.cs').read_text(encoding='utf-8-sig')
    table = source.split('static readonly Dictionary<string, (string id, float v)[]> Targets')[1].split('public string Current')[0]
    targets = {}
    for name, body in re.findall(r'\{ "(\w+)", (.*?) \},', table):
        targets[name] = {pid:float(value) for pid,value in re.findall(r'\("(Param\w+)", (-?[\d.]+)f\)',body)}
    assert len(targets)==12
    names = dict(re.findall(r'\{ "(\w+)", "([^"\n]+)" \}', source.split('JapaneseNames')[1].split('// 表情 →')[0]))
    model = cc.Model(modelpath); textures=renderer.load_textures(model)
    # Match CielExpression's new-rig branch; old exported rigs retain the legacy targets.
    if 'ParamRelaxed' in model.param_range:targets['relaxed']={'ParamRelaxed':1.0}
    if 'ParamHappy' in model.param_range:targets['happy']['ParamHappy']=1.0
    if 'ParamSurprised' in model.param_range:
        targets['surprised']={'ParamSurprised':1.0,'ParamEar':1.0,'ParamBrowLY':.8,'ParamBrowRY':.8,'ParamCheek':.15}
    controls = {'ParamCheek':['Cheek_Blush'], 'ParamEyeLSmile':['Eye_L_Happy'], 'ParamEyeRSmile':['Eye_R_Happy'],
                'ParamTear':['Tear_L','Tear_R'], 'ParamSweat':['Sweat'], 'ParamSparkle':['Eye_L_Sparkle','Eye_R_Sparkle']}
    report={'model':str(modelpath), 'parameters':model.param_range, 'controls':{}, 'expressions':targets}
    for pid,drawables in controls.items():
        assert pid in model.param_range,pid
        model.reset(); model.update(); before={d['id']:d for d in model.drawables()}
        model.set({pid:1});model.update(); after={d['id']:d for d in model.drawables()}
        for name in drawables:
            assert before[name]['opacity']<0.001,(pid,name,'neutral opacity')
            assert after[name]['opacity']>0.99,(pid,name,'active opacity')
        if pid in ('ParamEyeLSmile','ParamEyeRSmile'):
            prefix='Eye_L_' if pid=='ParamEyeLSmile' else 'Eye_R_'
            assert all(d['opacity']<0.001 for name,d in after.items() if name.startswith(prefix) and name not in sum(controls.values(),[]))
        report['controls'][pid]='off at 0, on at 1; smile hides original eye'
    font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',19)
    # Same canvas-space crop for every pose; wide enough to retain drooping ear tips.
    crop=(100,-110,2070,1530);scale=0.2; w,h=394,328
    sheet=Image.new('RGB',(w*4,(h+38)*3),(64,72,104))
    comparison=Image.new('RGB',(w*2*3,(h+38)*4),(64,72,104))
    for i,(name,deltas) in enumerate(targets.items()):
        model.reset(); values={pid:model.param_range[pid][1]+v for pid,v in deltas.items()}
        assert not model.set(values)
        model.update()
        for d in model.drawables():
            assert np.isfinite(d['pos']).all() and np.isfinite(d['uv']).all()
            assert 0<=d['texture']<len(textures)
        tile=renderer.render(model,textures,scale,crop,(64,72,104));tile.save(out/(name+'.png'))
        x,y=(i%4)*w,(i//4)*(h+38);sheet.paste(tile,(x,y+38));ImageDraw.Draw(sheet).text((x+8,y+7),names[name],font=font,fill='white')
        ref=Image.open(ROOT/'assets/ciel/generated/v22/expressions'/(name+'.png')).convert('RGBA')
        background=Image.new('RGBA',ref.size,(64,72,104,255))
        ref=Image.alpha_composite(background,ref).convert('RGB')
        # v22 uses its approved face/ear crop rather than the model's canvas.
        ref.thumbnail((w,h)); x,y=(i%3)*w*2,(i//3)*(h+38)
        comparison.paste(ref,(x+(w-ref.width)//2,y+38+(h-ref.height)//2));comparison.paste(tile,(x+w,y+38))
        ImageDraw.Draw(comparison).text((x+8,y+7),names[name]+'：見本 / リグ',font=font,fill='white')
    sheet.save(out/'expressions-12.png');comparison.save(out/'reference-comparison.png')
    # Interpolation + blinking + gaze + head rotation must remain finite and reset cleanly.
    for level in (0,0.25,0.5,0.75,1):
        for angle in (-30,0,30):
            model.reset();model.set({'ParamEar':-level,'ParamEyeLOpen':level,'ParamEyeROpen':level,
                                    'ParamAngleX':angle,'ParamAngleY':-angle,'ParamEyeBallX':1-level*2,
                                    'ParamEyeLSmile':level,'ParamEyeRSmile':level,'ParamTear':level,'ParamSparkle':level})
            model.update();assert all(np.isfinite(d['pos']).all() for d in model.drawables())
    model.reset();model.update();ds={d['id']:d for d in model.drawables()}
    assert all(ds[n]['opacity']<0.001 for ns in controls.values() for n in ns)
    report['interpolated_poses_checked']=15;report['neutral_reset']='all overlays hidden'
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('EXPRESSION_CHECK_DONE',out)


if __name__=='__main__': main()
