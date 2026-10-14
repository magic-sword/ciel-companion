"""Promote an approved skin-color-only SDK and its seven replacement PNGs."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.local/skin-adoption'
rig,raw=map(Path,sys.argv[1:3]);current=ROOT/'assets/ciel/current';proof=ROOT/'assets/ciel/rig/proofs/skin-v46'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert (WORK/'ciel-before.cmo3').exists()
check=json.loads((proof/'verification.json').read_text(encoding='utf-8'));assert check['reset_passed'] and check['geometry_triangles_opacity_and_draw_order_preserved'] and check['material_alpha_preserved']
provenance=ROOT/'assets/ciel/generated/v46/generation-provenance.json';v=json.loads(provenance.read_text(encoding='utf-8'))
for item in v['layers']:
    name=item['name'];dst=current/'layers'/(name+'.png');assert sha(dst)==item['source_sha256'],name
    shutil.copy2(ROOT/'assets/ciel/generated/v46/layers'/(name+'.png'),dst)
shutil.copy2(rig,ROOT/'assets/ciel/rig/ciel.cmo3')
info=json.loads((current/'approved.json').read_text(encoding='utf-8'))
info.update(rig_sha256=sha(ROOT/info['rig']),latest_proofs='assets/ciel/rig/proofs/skin-v46',
    skin_tone_revision='v46',latest_skin_tone_proofs='assets/ciel/rig/proofs/skin-v46')
info['export_files']=[{'path':str(p.relative_to(raw)).replace('\\','/'),'sha256':sha(p)} for p in (raw/'Ciel.moc3',raw/'Ciel.cdi3.json',raw/'Ciel.model3.json',raw/'Ciel.4096/texture_00.png')]
write(current/'approved.json',info)
write(proof/'adoption.json',{'approved_date':'2026-10-14','rig':info['rig'],'rig_sha256':info['rig_sha256'],
    'material_count':92,'skin_tone_source':'v46','replaced_materials':[q['name'] for q in v['layers']],
    'geometry_changed':False,'sdk_package':'assets/ciel/runtime','unity_applied':False})
v.update(approved=True,cubism_integrated=True,unity_applied=False,current_materials='assets/ciel/current/layers.json');write(provenance,v)
print('SKIN_TONE_ADOPTED',info['rig_sha256'])
