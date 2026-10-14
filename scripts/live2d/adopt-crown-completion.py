"""Promote the verified two-material v47 crown completion."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2]
work=ROOT/'.local/crown-completion-adoption'
rig,raw=map(Path,sys.argv[1:3]); current=ROOT/'assets/ciel/current'
proof=ROOT/'assets/ciel/rig/proofs/crown-v47'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
check=json.loads((proof/'verification.json').read_text(encoding='utf-8'))
assert check['reset_passed'] and check['other_91_drawable_geometry_preserved'] and check['back_hair_below_y600_unchanged']
provenance=ROOT/'assets/ciel/generated/v47/generation-provenance.json'
v=json.loads(provenance.read_text(encoding='utf-8'))
assert sha(ROOT/'assets/ciel/rig/ciel.cmo3')==sha(work/'ciel-before.cmo3'),'Formal rig changed during integration'
for p in (current/'layers').glob('*.png'):
    if p.stem not in ('Hair_Crown','Hair_Back'):
        assert sha(p)==sha(work/'current-before/layers'/p.name),p.name
for name,key in [('Hair_Crown','source_sha256'),('Hair_Back','back_hair_source_sha256')]:
    dst=current/'layers'/f'{name}.png'; assert sha(dst)==v[key],name
    shutil.copy2(ROOT/'assets/ciel/generated/v47/layers'/f'{name}.png',dst)
shutil.copy2(rig,ROOT/'assets/ciel/rig/ciel.cmo3')
info=json.loads((current/'approved.json').read_text(encoding='utf-8'))
info.update(rig_sha256=sha(ROOT/info['rig']),latest_proofs='assets/ciel/rig/proofs/crown-v47',common_crown_revision='v47',crown_original_revision='v45',crown_completion_revision='v47',latest_crown_proofs='assets/ciel/rig/proofs/crown-v47')
info['export_files']=[{'path':str(p.relative_to(raw)).replace('\\','/'),'sha256':sha(p)} for p in (raw/'Ciel.moc3',raw/'Ciel.cdi3.json',raw/'Ciel.model3.json',raw/'Ciel.4096/texture_00.png')]
write(current/'approved.json',info)
write(proof/'adoption.json',{'approved_date':'2026-10-14','rig':info['rig'],'rig_sha256':info['rig_sha256'],'material_count':92,'source_revision':'v47','replaced_materials':['Hair_Crown','Hair_Back'],'common_to_all_expressions':True,'sdk_package':'assets/ciel/runtime','unity_applied':False})
v.update(approved=True,cmo_updated=True,cubism_integrated=True,unity_updated=False,unity_applied=False,current_materials='assets/ciel/current/layers.json',source_rig_sha256=sha(work/'ciel-before.cmo3'),source_archive='.local/crown-completion-adoption/current-before/layers'); write(provenance,v)
print('CROWN_COMPLETION_ADOPTED',info['rig_sha256'])
