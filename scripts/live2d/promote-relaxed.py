"""Adopt the verified one-control relaxed pose without changing Unity assets."""
from pathlib import Path
import json,shutil,hashlib
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.local/relaxed-integration';CURRENT=ROOT/'assets/ciel/current'
v=json.loads((WORK/'proofs/verification.json').read_text());assert v['baseline_neutral_and_happy_preserved'] and v['reset_passed']
if not (WORK/'current-before').exists():shutil.copytree(CURRENT,WORK/'current-before')
for name in ('Mouth_Relaxed','Cheek_Relaxed'):shutil.copy2(WORK/'layers'/(name+'.png'),CURRENT/'layers'/(name+'.png'))
m=json.loads((CURRENT/'layers.json').read_text(encoding='utf-8'))
for slot,name in [('Cheek_Happy','Cheek_Relaxed'),('Mouth_Happy','Mouth_Relaxed')]:
    if not any(e['name']==name for e in m['layers']):
        i=next(i for i,e in enumerate(m['layers']) if e['name']==slot)+1
        m['layers'].insert(i,{'name':name,'path':f'assets/ciel/current/layers/{name}.png','visible':False})
assert len(m['layers'])==len({e['name'] for e in m['layers']})==64
(CURRENT/'layers.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copy2(WORK/'relaxed-integrated.cmo3',ROOT/'assets/ciel/rig/ciel.cmo3')
OUT=ROOT/'assets/ciel/rig/proofs/relaxed-v32';OUT.mkdir(parents=True,exist_ok=True)
for p in (WORK/'proofs').iterdir():
    if p.is_file():shutil.copy2(p,OUT/p.name)
expressions=ROOT/'assets/ciel/rig/expressions';expressions.mkdir(exist_ok=True)
for name,values in {'neutral':(0,0,0,0),'happy':(1,1,1,0),'relaxed':(0,0,0,1)}.items():
    doc={'Type':'Live2D Expression','FadeInTime':.2,'FadeOutTime':.2,
        'Parameters':[{'Id':pid,'Value':value,'Blend':'Overwrite'} for pid,value in
                      zip(('ParamHappy','ParamEyeLSmile','ParamEyeRSmile','ParamRelaxed'),values)]}
    (expressions/(name+'.exp3.json')).write_text(json.dumps(doc,indent=2)+'\n',encoding='utf-8')
(OUT/'adoption.json').write_text(json.dumps({'source_version':'v32','expression_control':'ParamRelaxed',
    'rig_sha256':hashlib.sha256((ROOT/'assets/ciel/rig/ciel.cmo3').read_bytes()).hexdigest(),
    'new_materials':['Mouth_Relaxed','Cheek_Relaxed'],'unity_updated':False},indent=2)+'\n',encoding='utf-8')
print('RELAXED_PROMOTED')
