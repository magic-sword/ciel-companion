"""Check that starting a blink does not switch to a discontinuous renderer."""
import os,json,hashlib
from pathlib import Path
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
source=ROOT/'scripts/gimp/build_face_remake.py'
exec(source.read_text(encoding='utf-8').split('normal=render(0,0)')[0])
checks=[]
for gaze in [-4,0,4]:
    opened=render(gaze,0)
    tiny=render(gaze,.000001)
    differences=[abs(a-b) for a,b in zip(opened,tiny)]
    maximum=max(differences)
    assert maximum<=1, f'Discontinuous blink onset at gaze {gaze}: {maximum}'
    assert all(tiny[i:i+4]==reference[i:i+4] for i in stationary_fold_indices)
    checks.append(dict(gaze_px=gaze,closure=.000001,max_channel_delta=maximum,
                       changed_pixels=sum(opened[i:i+4]!=tiny[i:i+4] for i in range(0,len(opened),4))))
assert render(0,0)==reference
assert render(-4,1)==render(4,1)==render(0,1)
report=dict(status='endpoint_continuity_verified_not_visual_approval',
    renderer_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),checks=checks,
    neutral_equal=True,closed_independent_of_gaze=True,
    limits=['Finite epsilon check at three gaze positions','Does not establish intermediate geometry or complete visual quality'])
(OUT/'blink-endpoint.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('BLINK_ENDPOINT_READY',json.dumps(report),flush=True)
