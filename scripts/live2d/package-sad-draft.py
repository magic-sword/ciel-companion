"""Store the latest sad candidate separately from angry and approved packages."""
from pathlib import Path
import json,hashlib,shutil,sys
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.local/sad-integration';OUT=ROOT/'assets/ciel/rig/drafts/sad';BASE=ROOT/'.local/sad-adoption/adopted-drafts/angry'
OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
shutil.copy2(WORK/'sad-integrated.cmo3',OUT/'sad.cmo3');shutil.copytree(Path(sys.argv[1]) if len(sys.argv)>1 else WORK/'lids-export',OUT/'runtime',dirs_exist_ok=True)
for folder in ('Expressions','Motions'):shutil.copytree(BASE/'runtime'/folder,OUT/'runtime'/folder,dirs_exist_ok=True)
shutil.copy2(BASE/'runtime/Ciel.physics3.json',OUT/'runtime/Ciel.physics3.json')
for p in (BASE/'runtime/Expressions').glob('*.exp3.json'):
    exp=json.loads(p.read_text(encoding='utf-8'));exp['Parameters'].append({'Id':'ParamSad','Value':0,'Blend':'Overwrite'})
    (OUT/'runtime/Expressions'/p.name).write_text(json.dumps(exp,indent=2)+'\n',encoding='utf-8')
exp={'Type':'Live2D Expression','FadeInTime':.2,'FadeOutTime':.2,'Parameters':[{'Id':pid,'Value':v,'Blend':'Overwrite'} for pid,v in [('ParamSad',1),('ParamEarFold',1),('ParamAngry',0),('ParamHappy',0),('ParamRelaxed',0),('ParamSurprised',0),('ParamEar',0),('ParamCheek',.2),('ParamEyeLSmile',0),('ParamEyeRSmile',0),('ParamMouthForm',0),('ParamMouthOpenY',0)]]}
(OUT/'runtime/Expressions/sad.exp3.json').write_text(json.dumps(exp,indent=2)+'\n',encoding='utf-8')
model=json.loads((BASE/'runtime/Ciel.model3.json').read_text());model['FileReferences']['Expressions']=[{'Name':p.stem.replace('.exp3',''),'File':'Expressions/'+p.name} for p in sorted((OUT/'runtime/Expressions').glob('*.exp3.json'))]
(OUT/'runtime/Ciel.model3.json').write_text(json.dumps(model,indent=2)+'\n',encoding='utf-8')
layers=json.loads((BASE/'layers.json').read_text());layers['out']='.local/sad-integration/candidate-materials'
layers['layers'] += [{'name':n,'path':'assets/ciel/generated/v36/layers/'+n+'.png','visible':False} for n in ('Mouth_Sad','Brow_Sad')]
(OUT/'layers.json').write_text(json.dumps(layers,indent=2)+'\n',encoding='utf-8')
status={'status':'draft','approved':False,'material_count':len(layers['layers']),'base_angry_rig_sha256':sha(BASE/'angry.cmo3'),'rig_sha256':sha(OUT/'sad.cmo3'),'unity_applied':False,'controls':{'ParamSad':'sad face','ParamEarFold':'v35 folded ears'},'proofs':'assets/ciel/rig/proofs/sad-v36'}
(OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
files={str(p.relative_to(OUT/'runtime')).replace('\\','/'):sha(p) for p in (OUT/'runtime').rglob('*') if p.is_file() and p.name!='manifest.json'}
(OUT/'runtime/manifest.json').write_text(json.dumps({'status':'draft','files':files},indent=2)+'\n',encoding='utf-8')
print('SAD_DRAFT_PACKAGED',len(layers['layers']))
