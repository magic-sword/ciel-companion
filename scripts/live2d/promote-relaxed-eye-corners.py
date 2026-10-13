"""Adopt the saved, exported and verified localized eye-corner edit."""
from pathlib import Path
import json,shutil,hashlib
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.local/eye-corner-integration'
v=json.loads((WORK/'proofs/eye-corner-verification.json').read_text())
assert v['neutral_happy_closed_blink_unchanged'] and v['iris_white_lower_lid_unchanged']
assert json.loads((WORK/'proofs/verification.json').read_text())['reset_passed']
assert json.loads((WORK/'proofs/boundary-verification.json').read_text())['iris_geometry_unchanged']
rig=ROOT/'assets/ciel/rig/ciel.cmo3';shutil.copy2(WORK/'corners-adjusted.cmo3',rig)
out=ROOT/'assets/ciel/rig/proofs/relaxed-eye-corners';out.mkdir(parents=True,exist_ok=True)
for p in (WORK/'proofs').iterdir():
    if p.is_file():shutil.copy2(p,out/p.name)
(out/'adoption.json').write_text(json.dumps({'edit':'relaxed_outer_lash_tail_compression',
    'strength':.55,'new_material_generation':False,'current_material_layers':66,
    'rig_sha256':hashlib.sha256(rig.read_bytes()).hexdigest(),'unity_updated':False},indent=2)+'\n',encoding='utf-8')
print('RELAXED_EYE_CORNERS_PROMOTED')
