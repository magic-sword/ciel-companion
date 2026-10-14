"""Promote the verified common crown and approved jitome together."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.local/crown-adoption'
rig,raw=map(Path,sys.argv[1:3]);current=ROOT/'assets/ciel/current';runtime=ROOT/'assets/ciel/runtime'
proof=ROOT/'assets/ciel/rig/proofs/crown-v45'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert (WORK/'ciel-before.cmo3').exists()
check=json.loads((proof/'verification.json').read_text(encoding='utf-8'))
assert check['reset_passed'] and check['finite_combined_poses']==81
assert check['common_crown_in_all_expressions'] and check['crown_follows_head_and_preserves_hair_sway']
draft=ROOT/'assets/ciel/rig/drafts/jitome'
layers=json.loads((draft/'layers.json').read_text(encoding='utf-8'))
layers['layers'].insert(1,{'name':'Hair_Crown','path':'assets/ciel/generated/v45/layers/Hair_Crown.png','visible':True})
assert len(layers['layers'])==len({p['name'] for p in layers['layers']})==92
for layer in layers['layers']:
    src=ROOT/layer['path'];dst=current/'layers'/(layer['name']+'.png')
    if src.resolve()!=dst.resolve():shutil.copy2(src,dst)
    layer['path']=str(dst.relative_to(ROOT)).replace('\\','/')
layers['out']='assets/ciel/psd/ciel-current';write(current/'layers.json',layers)
shutil.copy2(rig,ROOT/'assets/ciel/rig/ciel.cmo3')
for p in (draft/'runtime').rglob('*'):
    if p.is_file() and p.name!='manifest.json':
        dest=runtime/p.relative_to(draft/'runtime');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
for p in raw.rglob('*'):
    if p.is_file():
        dest=runtime/p.relative_to(raw);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
# Keep physics, motions, expression registrations and eye/lip-sync groups.
model=json.loads((draft/'runtime/Ciel.model3.json').read_text(encoding='utf-8'))
write(runtime/'Ciel.model3.json',model)
shutil.copytree(runtime/'Expressions',ROOT/'assets/ciel/rig/expressions',dirs_exist_ok=True)
info=json.loads((current/'approved.json').read_text(encoding='utf-8'))
expressions=info['approved_expressions']+['jitome']
info.update(approved_expressions=expressions,material_count=92,rig_sha256=sha(ROOT/info['rig']),
    latest_proofs='assets/ciel/rig/proofs/crown-v45',latest_jitome_proofs='assets/ciel/rig/proofs/crown-v45',
    jitome_control='ParamJitome',jitome_revision='v44',common_crown_revision='v45',
    latest_crown_proofs='assets/ciel/rig/proofs/crown-v45')
info['export_files']=[{'path':str(p.relative_to(raw)).replace('\\','/'),'sha256':sha(p)} for p in (raw/'Ciel.moc3',raw/'Ciel.cdi3.json',raw/'Ciel.model3.json',raw/'Ciel.4096/texture_00.png')]
write(current/'approved.json',info)
write(proof/'adoption.json',{'approved_date':'2026-10-14','rig':info['rig'],'rig_sha256':info['rig_sha256'],
    'material_count':92,'common_material':'Hair_Crown','common_material_source':'v45','jitome_source':'v44',
    'common_material_expressions':'all','sdk_package':'assets/ciel/runtime','unity_applied':False})
for v in (44,45):
    p=ROOT/f'assets/ciel/generated/v{v}/generation-provenance.json';data=json.loads(p.read_text(encoding='utf-8'))
    data.update(approved=True,cubism_integrated=True,unity_applied=False,current_materials='assets/ciel/current/layers.json');write(p,data)
print('CROWN_JITOME_ADOPTED',info['rig_sha256'])
