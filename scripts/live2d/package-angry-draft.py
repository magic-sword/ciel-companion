"""Keep the angry candidate separate from the approved Unity package."""
from pathlib import Path
import json,hashlib,shutil,sys
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.local/angry-integration';OUT=ROOT/'assets/ciel/rig/drafts/angry';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=WORK/'angry-integrated.cmo3';shutil.copy2(source,OUT/'angry.cmo3')
shutil.copytree(Path(sys.argv[1]) if len(sys.argv)>1 else WORK/'brow-export',OUT/'runtime',dirs_exist_ok=True)
for folder in ('Expressions','Motions'):shutil.copytree(ROOT/'assets/ciel/runtime'/folder,OUT/'runtime'/folder,dirs_exist_ok=True)
shutil.copy2(ROOT/'assets/ciel/runtime/Ciel.physics3.json',OUT/'runtime/Ciel.physics3.json')
model=json.loads((ROOT/'assets/ciel/runtime/Ciel.model3.json').read_text(encoding='utf-8'))
for p in (OUT/'runtime/Expressions').glob('*.exp3.json'):
    exp=json.loads(p.read_text(encoding='utf-8'));exp['Parameters'] += [{'Id':'ParamAngry','Value':0,'Blend':'Overwrite'},{'Id':'ParamEarFold','Value':0,'Blend':'Overwrite'}]
    p.write_text(json.dumps(exp,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
exp={'Type':'Live2D Expression','FadeInTime':.2,'FadeOutTime':.2,'Parameters':[{'Id':pid,'Value':value,'Blend':'Overwrite'} for pid,value in [('ParamAngry',1),('ParamEarFold',1),('ParamHappy',0),('ParamRelaxed',0),('ParamSurprised',0),('ParamEyeLSmile',0),('ParamEyeRSmile',0),('ParamEar',0),('ParamCheek',.2),('ParamMouthForm',0),('ParamMouthOpenY',0)]]}
(OUT/'runtime/Expressions/angry.exp3.json').write_text(json.dumps(exp,indent=2)+'\n',encoding='utf-8')
model['FileReferences']['Expressions']=[{'Name':p.stem.replace('.exp3',''),'File':'Expressions/'+p.name} for p in sorted((OUT/'runtime/Expressions').glob('*.exp3.json'))]
(OUT/'runtime/Ciel.model3.json').write_text(json.dumps(model,indent=2)+'\n',encoding='utf-8')
layers=json.loads((ROOT/'assets/ciel/current/layers.json').read_text(encoding='utf-8'))
layers['out']='.local/angry-integration/candidate-materials'
layers['layers'] += [{'name':n,'path':'assets/ciel/generated/v35/layers/'+n+'.png','visible':False} for n in ('Mouth_Angry','Brow_Angry','Ear_R_Folded','Ear_L_Folded')]
(OUT/'layers.json').write_text(json.dumps(layers,indent=2)+'\n',encoding='utf-8')
status={'status':'draft','approved':False,'base_approved_rig_sha256':sha(ROOT/'assets/ciel/rig/ciel.cmo3'),'draft_rig_sha256':sha(OUT/'angry.cmo3'),'material_count':len(layers['layers']),'unity_applied':False,'proofs':'assets/ciel/rig/proofs/angry-v35','controls':{'ParamAngry':'pouting face','ParamEarFold':'reusable folded ears'}}
status['brow_canvas_offset']=[0,-32]
(OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
files={str(p.relative_to(OUT/'runtime')).replace('\\','/'):sha(p) for p in (OUT/'runtime').rglob('*') if p.is_file() and p.name!='manifest.json'}
(OUT/'runtime/manifest.json').write_text(json.dumps({'status':'draft','files':files},indent=2)+'\n',encoding='utf-8')
gen=ROOT/'assets/ciel/generated/v35';provenance={'method':'contextual image edit followed by non-generative separation','reference':'assets/ciel/generated/v22/expressions/angry.png','generated_original':'edits/angry-face-ears-with-contour.png','original_sha256':sha(gen/'edits/angry-face-ears-with-contour.png'),'generator':'image_gen','image_edit_count':1,'used_generated_parts':['Ear_R_Folded','Ear_L_Folded'],'direct_reference_parts':['Mouth_Angry','Brow_Angry'],'existing_materials_reused':['eyes','cheeks','face base'],'placement':'placement.json','approved':False}
provenance['brow_cleanup']='Reference brow outlines traced and cleaned to remove overlapping hair strokes'
provenance['brow_model_position']='brow-position.json'
(gen/'generation-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
assert sha(ROOT/'assets/ciel/rig/ciel.cmo3')=='ff5a8947af5f12028a5a024f5ccc89e8c739c75673a2d92e5d5733565f4ab008'
print('ANGRY_DRAFT_PACKAGED',len(layers['layers']))
