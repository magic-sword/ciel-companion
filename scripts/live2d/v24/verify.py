"""Additional review proofs; transformations here affect proofs only."""
import json,hashlib
import numpy as np
from PIL import Image,ImageChops
from build import SIZE,assemble,board
from prepare import ROOT,OUT,CURRENT,NAMES,hashes

def main():
    old={n:Image.open(CURRENT/'layers'/f'{n}.png').convert('RGBA') for n in NAMES}
    new={n:Image.open(OUT/'layers'/f'{n}.png').convert('RGBA') for n in NAMES}
    rect=(300,0,1880,1300)
    for angle in [30,55]:
        sets=[]
        for label,data in [('current',old),('v24',new)]:
            turned=dict(data)
            for n in NAMES:
                if not n.startswith('Ear_'):continue
                right=n.split('_')[1]=='R'
                turned[n]=data[n].rotate(angle if right else -angle,Image.Resampling.BICUBIC,center=(665,680) if right else (1520,700))
            sets.append((label+f' rigid rotation {angle} deg (proof only)',assemble(turned,True).crop(rect)))
        board(sets,OUT/'proofs'/f'ears-tilt-{angle}.png',(790,650))
    meta=json.loads((OUT/'placement.json').read_text(encoding='utf-8'))
    verify=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
    verify['iris_core_pixel_identical']={n:bool(np.array_equal(np.asarray(old[n])[meta[n]['original_core_from_y']:],np.asarray(new[n])[meta[n]['original_core_from_y']:])) for n in NAMES if n.endswith('_Iris')}
    verify['layer_sha256']={n:hashlib.sha256((OUT/'layers'/f'{n}.png').read_bytes()).hexdigest() for n in NAMES}
    before=assemble({});after=assemble(new)
    before_array=np.asarray(before,dtype=np.int16);after_array=np.asarray(after,dtype=np.int16)
    delta=np.abs(before_array-after_array)
    ear_only=np.asarray(assemble({n:im for n,im in new.items() if n.startswith('Ear_')}),dtype=np.int16)
    ed=np.abs(before_array-ear_only)
    verify['ears_front_difference']={'max':int(ed.max()),'changed_pixels':int(np.any(ed,axis=2).sum()),'pixels_over_5':int((ed.max(axis=2)>5).sum()),'mean_absolute_rgba':float(ed.mean())}
    mask=Image.new('L',SIZE)
    for im in list(old.values())+list(new.values()):mask=ImageChops.lighter(mask,im.getchannel('A'))
    verify['outside_replaced_layer_support_identical']=bool((delta[np.asarray(mask)==0]==0).all())
    verify['current_unchanged']=json.loads((OUT/'current-before.json').read_text(encoding='utf-8'))==hashes()
    verify['motion_proofs']='Rigid rotation and clipped iris translation on PNG composites only, not Cubism deformation tests'
    (OUT/'verification.json').write_text(json.dumps(verify,indent=2),encoding='utf-8')
    contact=Image.new('RGB',(1200,1900),(40,43,57))
    for i,n in enumerate(NAMES):
        proof=Image.open(OUT/'proofs'/f'{n}-compare.png');proof.thumbnail((600,365))
        contact.paste(proof,((i%2)*600,(i//2)*380))
    contact.save(OUT/'layers-comparison.png')
    for path in sorted((OUT/'edits').glob('*.png')):
        name=path.stem.rsplit('-',1)[0]
        suffix='-extended-key.png' if name.endswith('_Base') else '-key.png'
        src=Image.open(OUT/'inputs'/f'{name}{suffix}').convert('RGBA')
        edit=Image.open(path).convert('RGBA')
        scale=src.width/edit.width
        edit=edit.resize((src.width,round(edit.height*scale)),Image.Resampling.LANCZOS)
        board([('original on green',src),('raw image edit '+path.stem,edit)],OUT/'qa'/f'{path.stem}-raw-compare.png')
    print(json.dumps(verify,indent=2))
if __name__=='__main__':main()
