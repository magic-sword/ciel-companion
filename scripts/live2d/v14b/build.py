"""Build v14b: only regenerate/extract Mouth_Large, copy all 53 other PNGs."""
import copy
import shutil
import numpy as np
from PIL import Image
from common import ROOT,GEN,LAY,PROOF,SIZE,CROP,ROI,read,write,extract,composite,face,panel,flatten,ndi
from measure import corners

SELECTED='large-01'

def main():
    state=read(ROOT/'assets/ciel/layers/v14/layer-state.json')
    for r in state['layers']:
        dest=LAY/(r['name']+'.png')
        if r['name']!='Mouth_Large':
            shutil.copyfile(ROOT/r['path'],dest)
        else:
            r['source']='v14b generated '+SELECTED
            r['description']='正面・左右対称を明示して生成した大口。口内・輪郭・周囲肌を一体抽出。'
        r['path']=dest.relative_to(ROOT).as_posix()
    write(LAY/'layer-state.json',state)
    write(LAY/'psd-manifest.json',{'canvas':list(SIZE),'out':'assets/ciel/psd/ciel-v14b',
          'layers':[{k:r[k] for k in ('name','path')} for r in state['layers']]})
    log=read(GEN/'generation-log.json');log['selected']=SELECTED
    log['selection_reason']='Equal-height corners under every tested color threshold; narrowest of the three new candidates, soft rounded natural opening.'
    write(GEN/'generation-log.json',log)
    shutil.copyfile(GEN/f'candidates/{SELECTED}.png',GEN/f'selected/{SELECTED}.png')
    shutil.copyfile(ROOT/'assets/ciel/generated/v14/selected/small-03.png',GEN/'selected/small-03-inherited-v14.png')
    original=Image.open(GEN/'inputs/v11-face-closed.png').convert('RGB')
    edit=Image.open(GEN/f'selected/{SELECTED}.png').convert('RGB')
    _,alpha,metrics=extract(original,edit,'large')
    renders={m:composite(state,m) for m in ('closed','small','large')}
    faces={m:face(im) for m,im in renders.items()}
    for m,im in renders.items():
        im.save(PROOF/f'{m}-composite.png');faces[m].save(PROOF/f'{m}-face.png')
    panel([(m,faces[m]) for m in faces],PROOF/'three-states.png')
    panel([(f'{v} / {m}',faces[m] if v=='v14b' else Image.open(ROOT/f'assets/ciel/generated/v14/proofs/{m}-face.png'))
           for v in ('v14','v14b') for m in ('closed','small','large')],PROOF/'v14-v14b.png')
    # Preserve the exact already-produced v12/v13/v14 comparisons and append v14b.
    old=Image.open(ROOT/'assets/ciel/generated/v14/proofs/v12-v13-v14.png').convert('RGB')
    panel([(f'v14b / {m}',faces[m]) for m in faces],PROOF/'comparison-row.png',side=440)
    row=Image.open(PROOF/'comparison-row.png')
    combined=Image.new('RGB',(old.width,old.height+row.height))
    combined.paste(old,(0,0));combined.paste(row,(0,old.height))
    combined.save(PROOF/'v12-v13-v14-v14b.png')
    small=Image.open(GEN/'selected/small-03-inherited-v14.png').convert('RGB')
    edits={'small':small,'large':edit}
    panel([(m+' / '+label,im) for m in ('small','large') for label,im in
           [('generated'+(' in v14' if m=='small' else ''),edits[m]),('composite',faces[m])]],
          PROOF/'generated-vs-composite.png',cols=2,side=627)
    panel([(m+' / '+label,im.crop(ROI)) for m in ('small','large') for label,im in
           [('generated',edits[m]),('composite',faces[m])]],PROOF/'generated-vs-composite-mouth.png',cols=2,side=525,height=375)
    panel([(m+' / '+label,flatten(Image.open(LAY/f'Mouth_{m.title()}.png').crop((990,1160,1230,1360)),color))
           for m in ('small','large') for label,color in [('light','#fafafa'),('dark','#252938')]],
          PROOF/'parts-light-dark.png',cols=2,side=480,height=400)
    frames=[faces[m].resize((752,752),Image.Resampling.LANCZOS) for m in ('closed','small','large','small')]
    stack=Image.new('RGB',(752,752*4))
    for i,im in enumerate(frames):stack.paste(im,(0,i*752))
    palette=stack.quantize(colors=256)
    q=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in frames]
    q[0].save(PROOF/'mouth-switch.gif',save_all=True,append_images=q[1:],duration=[750,600,750,600],loop=0,disposal=2)
    frames[0].save(PROOF/'mouth-switch.png',save_all=True,append_images=frames[1:],duration=[750,600,750,600],loop=0)
    panel([('PRIVATE anime reference',Image.open(ROOT/'.local/reference/anime-mouth-zoom.png')),
           ('v14 large',Image.open(ROOT/'assets/ciel/generated/v14/selected/large-04.png').crop(ROI)),
           ('v14b large',edit.crop(ROI))],GEN/'private/reference-mouths-PRIVATE.png',cols=3,side=500,height=350)
    rgb=np.asarray(renders['large'].crop(CROP).convert('RGB')).astype(np.int16)
    target=np.asarray(edit.resize((1536,1536),Image.Resampling.LANCZOS)).astype(np.int16)
    fullalpha=np.asarray(Image.open(LAY/'Mouth_Large.png'))[:,:,3]
    core=ndi.binary_erosion(fullalpha[236:1772,318:1854]==255,iterations=3)
    err=np.abs(rgb-target)
    metrics['inverse_space_opaque_core_mae']=float(err[core].mean())
    metrics['inverse_space_opaque_core_max']=int(err[core].max())
    err2=np.abs(np.asarray(faces['large']).astype(np.int16)-np.asarray(edit).astype(np.int16))
    metrics['input_space_opaque_core_mae']=float(err2[alpha==255].mean())
    metrics['corner_measurement']=corners(edit)
    metrics['geometry']='Only the inverse whole-face crop transform; no mouth reflection, warp, rotation, separate scaling or translation.'
    write(GEN/'extraction/metrics.json',metrics)
    print(metrics)

if __name__=='__main__':main()
