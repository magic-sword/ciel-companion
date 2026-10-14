"""Promote the approved teary face and v42 ears after validating the SDK export.

Usage: python -B scripts/live2d/adopt-teary.py saved.cmo3 packaged-runtime/ raw-export/
Backups must already exist in .local/teary-adoption/.
"""
from pathlib import Path
import sys,json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.local/teary-adoption'
rig=Path(sys.argv[1]);sdk=Path(sys.argv[2]);raw=Path(sys.argv[3]);current=ROOT/'assets/ciel/current';runtime=ROOT/'assets/ciel/runtime'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert (WORK/'ciel-before.cmo3').is_file() and (WORK/'current-before/layers.json').is_file()
verification=json.loads((ROOT/'assets/ciel/rig/proofs/teary-v42/verification.json').read_text(encoding='utf-8'))
assert verification['finite_combined_poses']==81 and verification['independent_blinks_preserved']
manifest=json.loads((ROOT/'assets/ciel/generated/v42/candidate-layers.json').read_text(encoding='utf-8'))
assert len(manifest['layers'])==83 and len({l['name'] for l in manifest['layers']})==83
for layer in manifest['layers']:
    src=ROOT/layer['path']; dst=current/'layers'/(layer['name']+'.png')
    if src.resolve()!=dst.resolve():shutil.copy2(src,dst)
    layer['path']=str(dst.relative_to(ROOT)).replace('\\','/')
manifest['out']='assets/ciel/psd/ciel-current';write(current/'layers.json',manifest)
shutil.copy2(rig,ROOT/'assets/ciel/rig/ciel.cmo3')
for p in sdk.rglob('*'):
    if p.is_file() and p.name!='manifest.json':
        dst=runtime/p.relative_to(sdk);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
expressions=['happy','relaxed','surprised','angry','sad','troubled','embarrassed','teary']
info=json.loads((current/'approved.json').read_text(encoding='utf-8'))
info.update(approved_expressions=expressions,rig_sha256=sha(ROOT/info['rig']),material_count=83,
    latest_proofs='assets/ciel/rig/proofs/teary-v42',latest_teary_proofs='assets/ciel/rig/proofs/teary-v42',
    teary_control='ParamTeary',teary_revision='v40-tears-and-lid-profile-with-v42-samoyed-ears',
    folded_ear_revision='v42',latest_folded_ear_proofs='assets/ciel/rig/proofs/teary-v42')
info['export_files']=[{'path':str(p.relative_to(raw)).replace('\\','/'),'sha256':sha(p)} for p in (raw/'Ciel.moc3',raw/'Ciel.cdi3.json',raw/'Ciel.model3.json',raw/'Ciel.4096/texture_00.png')]
write(current/'approved.json',info)
shutil.copytree(runtime/'Expressions',ROOT/'assets/ciel/rig/expressions',dirs_exist_ok=True)
files=[{'path':str(p.relative_to(runtime)).replace('\\','/'),'sha256':sha(p)} for p in sorted(runtime.rglob('*')) if p.is_file() and p.suffix!='.md' and p.name!='manifest.json']
assert len(files)==15,len(files)
materials=[{'path':l['path'],'sha256':sha(ROOT/l['path'])} for l in manifest['layers']]
write(runtime/'manifest.json',{'approved_date':'2026-10-14','source_rig':info['rig'],'source_rig_sha256':info['rig_sha256'],
    'material_count':83,'approved_expressions':expressions,'files':files,'materials':materials})
for revision in (40,42):
    p=ROOT/f'assets/ciel/generated/v{revision}/generation-provenance.json'
    if p.exists():
        d=json.loads(p.read_text(encoding='utf-8'));d.update(approved=True,cubism_integrated=True,unity_applied=False,current_materials='assets/ciel/current/layers.json');write(p,d)
write(ROOT/'assets/ciel/rig/proofs/teary-v42/adoption.json',{'approved_date':'2026-10-14','rig':info['rig'],
    'rig_sha256':info['rig_sha256'],'material_count':83,'face_source':'v40','folded_ear_source':'v42',
    'ear_control':'ParamEarFold','expression_control':'ParamTeary','sdk_package':'assets/ciel/runtime',
    'shared_ear_expressions':['angry','sad','troubled','embarrassed','teary'],'unity_applied':False})
print('TEARY_V42_ADOPTED',info['rig_sha256'])
