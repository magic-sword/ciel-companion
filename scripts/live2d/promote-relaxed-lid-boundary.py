"""Adopt verified lower boundary ink; keep shared parts for other expressions."""
from pathlib import Path
import json,shutil,hashlib
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.local/lid-boundary-integration'
CURRENT=ROOT/'assets/ciel/current';OUT=ROOT/'assets/ciel/rig/proofs/relaxed-boundary-v33'
v=json.loads((WORK/'proofs/boundary-verification.json').read_text())
assert v['neutral_happy_and_closed_blink_preserved'] and v['iris_geometry_unchanged']
assert json.loads((WORK/'proofs/verification.json').read_text())['reset_passed']
m=json.loads((CURRENT/'layers.json').read_text(encoding='utf-8'))
for side in 'LR':
    name=f'Eye_{side}_RelaxedLowerLine'
    shutil.copy2(ROOT/'assets/ciel/generated/v33/layers'/(name+'.png'),CURRENT/'layers'/(name+'.png'))
    if not any(e['name']==name for e in m['layers']):
        i=next(i for i,e in enumerate(m['layers']) if e['name']==f'Eye_{side}_LashLower')+1
        m['layers'].insert(i,{'name':name,'path':f'assets/ciel/current/layers/{name}.png','visible':False})
assert len(m['layers'])==len({e['name'] for e in m['layers']})==66
(CURRENT/'layers.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copy2(WORK/'boundary-integrated.cmo3',ROOT/'assets/ciel/rig/ciel.cmo3')
OUT.mkdir(parents=True,exist_ok=True)
for p in (WORK/'proofs').iterdir():
    if p.is_file():shutil.copy2(p,OUT/p.name)
(OUT/'adoption.json').write_text(json.dumps({'source_version':'v33','expression_control':'ParamRelaxed',
    'rig_sha256':hashlib.sha256((ROOT/'assets/ciel/rig/ciel.cmo3').read_bytes()).hexdigest(),
    'unity_updated':False},indent=2)+'\n',encoding='utf-8')
print('LID_BOUNDARY_PROMOTED')
