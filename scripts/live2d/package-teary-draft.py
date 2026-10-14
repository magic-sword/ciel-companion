"""Package the teary candidate without changing the approved model."""
from pathlib import Path
import json,hashlib,shutil,argparse
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.local/teary-integration';OUT=ROOT/'assets/ciel/rig/drafts/teary';BASE=ROOT/'assets/ciel/runtime'
parser=argparse.ArgumentParser()
parser.add_argument('--rig',type=Path,default=WORK/'teary-integrated.cmo3')
parser.add_argument('--export',type=Path,default=WORK/'export')
parser.add_argument('--proofs',default='assets/ciel/rig/proofs/teary-v40')
args=parser.parse_args()
OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
shutil.copy2(args.rig,OUT/'teary.cmo3');shutil.copytree(args.export,OUT/'runtime',dirs_exist_ok=True)
for folder in ('Expressions','Motions'):shutil.copytree(BASE/folder,OUT/'runtime'/folder,dirs_exist_ok=True)
shutil.copy2(BASE/'Ciel.physics3.json',OUT/'runtime/Ciel.physics3.json')
for p in (BASE/'Expressions').glob('*.exp3.json'):
    exp=json.loads(p.read_text(encoding='utf-8'));exp['Parameters'].append({'Id':'ParamTeary','Value':0,'Blend':'Overwrite'})
    exp['Parameters'].append({'Id':'ParamTear','Value':0,'Blend':'Overwrite'})
    (OUT/'runtime/Expressions'/p.name).write_text(json.dumps(exp,indent=2)+'\n',encoding='utf-8')
exp={'Type':'Live2D Expression','FadeInTime':.2,'FadeOutTime':.2,'Parameters':[{'Id':pid,'Value':v,'Blend':'Overwrite'} for pid,v in [('ParamTeary',1),('ParamEarFold',1),('ParamAngry',0),('ParamSad',0),('ParamTroubled',0),('ParamEmbarrassed',0),('ParamTear',0),('ParamHappy',0),('ParamRelaxed',0),('ParamSurprised',0),('ParamEar',0),('ParamSweat',0),('ParamCheek',.25),('ParamEyeLSmile',0),('ParamEyeRSmile',0),('ParamMouthForm',0),('ParamMouthOpenY',0)]]}
(OUT/'runtime/Expressions/teary.exp3.json').write_text(json.dumps(exp,indent=2)+'\n',encoding='utf-8')
model=json.loads((BASE/'Ciel.model3.json').read_text());model['FileReferences']['Expressions']=[{'Name':p.stem.replace('.exp3',''),'File':'Expressions/'+p.name} for p in sorted((OUT/'runtime/Expressions').glob('*.exp3.json'))]
(OUT/'runtime/Ciel.model3.json').write_text(json.dumps(model,indent=2)+'\n',encoding='utf-8')
layers=json.loads((ROOT/'assets/ciel/current/layers.json').read_text());layers['out']='.local/teary-integration/candidate-materials'
layers['layers'] += [{'name':n,'path':'assets/ciel/generated/v40/layers/'+n+'.png','visible':False} for n in ('Mouth_Teary','Brow_Teary','Tears_R_Teary','Tears_L_Teary')]
(OUT/'layers.json').write_text(json.dumps(layers,indent=2)+'\n',encoding='utf-8')
status={'status':'draft','approved':False,'material_count':len(layers['layers']),'base_rig_sha256':sha(ROOT/'assets/ciel/rig/ciel.cmo3'),'rig_sha256':sha(OUT/'teary.cmo3'),'unity_applied':False,'proofs':args.proofs,'control':'ParamTeary','ear_control':'ParamEarFold'}
(OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
files={str(p.relative_to(OUT/'runtime')).replace('\\','/'):sha(p) for p in (OUT/'runtime').rglob('*') if p.is_file() and p.name!='manifest.json'}
(OUT/'runtime/manifest.json').write_text(json.dumps({'status':'draft','files':files},indent=2)+'\n',encoding='utf-8')
print('TEARY_DRAFT_PACKAGED',len(layers['layers']))
