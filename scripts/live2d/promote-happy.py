"""Promote verified happy materials and the Cubism-saved model."""
import shutil,json,hashlib
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.local/happy-integration'
report=json.loads((WORK/'proofs/verification.json').read_text(encoding='utf-8'))
assert report['neutral_reset_passed'] and not report['duplicate_drawable_ids']
current=ROOT/'assets/ciel/current'
if not (WORK/'current-before').exists():shutil.copytree(current,WORK/'current-before')
names=('Eye_L_Happy','Eye_R_Happy','Cheek_Happy','Mouth_Happy','Nose_Happy')
for name in names:shutil.copy2(WORK/'layers'/(name+'.png'),current/'layers'/(name+'.png'))
manifest=json.loads((current/'layers.json').read_text(encoding='utf-8'))
for slot,name in [('Face_Shadow_Hair','Cheek_Happy'),('Mouth_Large','Mouth_Happy'),('Nose','Nose_Happy')]:
    if any(e['name']==name for e in manifest['layers']):continue
    index=next(i for i,e in enumerate(manifest['layers']) if e['name']==slot)+1
    manifest['layers'].insert(index,{'name':name,'path':f'assets/ciel/current/layers/{name}.png','visible':False})
assert len({e['name'] for e in manifest['layers']})==len(manifest['layers'])
(current/'layers.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copy2(WORK/'happy-final-work.cmo3',ROOT/'assets/ciel/rig/ciel.cmo3')
out=ROOT/'assets/ciel/rig/proofs/happy-v31';out.mkdir(parents=True,exist_ok=True)
for p in (WORK/'proofs').iterdir():
    if p.is_file():shutil.copy2(p,out/p.name)
(out/'adoption.json').write_text(json.dumps({'source_version':'v31','adopted_materials':list(names),
    'obsolete_happy_eye_files_replaced_in_place':True,'mesh_names_unique':True,
    'other_expression_shared_materials_retained':True,'unity_updated':False,
    'rig_sha256':hashlib.sha256((ROOT/'assets/ciel/rig/ciel.cmo3').read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf-8')
print('HAPPY_PROMOTED',len(manifest['layers']))
