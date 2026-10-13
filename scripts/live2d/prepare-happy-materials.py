"""Prepare the accepted v31 happy artwork for Cubism; keep other overlays."""
from pathlib import Path
import json,shutil
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.local/happy-integration';WORK.mkdir(parents=True,exist_ok=True)
SRC=ROOT/'assets/ciel/generated/v31/layers';DST=WORK/'layers';DST.mkdir(exist_ok=True)
for name in ('Eye_L_Happy','Eye_R_Happy','Mouth_Happy'):
    shutil.copy2(SRC/(name+'.png'),DST/(name+'.png'))
shutil.copy2(SRC/'Nose.png',DST/'Nose_Happy.png')
cheek=Image.open(SRC/'Cheek_R_Blush_Happy.png').convert('RGBA')
cheek.alpha_composite(Image.open(SRC/'Cheek_L_Blush_Happy.png').convert('RGBA'))
cheek.save(DST/'Cheek_Happy.png')
manifest={'canvas':[2172,2896],'out':'.local/happy-integration/happy-additions',
    'layers':[{'name':n,'path':str((DST/(n+'.png')).relative_to(ROOT)).replace('\\','/'),'visible':False}
              for n in ('Cheek_Happy','Mouth_Happy','Nose_Happy')]}
(WORK/'additions.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
if not (WORK/'ciel-before.cmo3').exists():shutil.copy2(ROOT/'assets/ciel/rig/ciel.cmo3',WORK/'ciel-before.cmo3')
shutil.copy2(WORK/'ciel-before.cmo3',WORK/'happy-base.cmo3')
print('HAPPY_INPUTS_READY')
