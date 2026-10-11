"""Build v14c's 54 layers and proofs, retaining v14b everywhere except two tiny fangs."""
import shutil
import numpy as np
from PIL import Image, ImageDraw
from common import ROOT,GEN,LAY,PROOF,SIZE,CROP,ROI,FONT,read,write,composite,face,panel,flatten
from measure import corners
from transplant import main as transplant

def main():
    transplant()
    state=read(ROOT/'assets/ciel/layers/v14b/layer-state.json')
    for r in state['layers']:
        dest=LAY/(r['name']+'.png')
        if r['name']!='Mouth_Large':shutil.copyfile(ROOT/r['path'],dest)
        else:
            r['source']='v14b Mouth_Large plus paired native v14 fang transplant; no image generation'
            r['description']='v14bの大口を保持し、v14の小さな八重歯だけを左右対称に2本追加。'
        r['path']=dest.relative_to(ROOT).as_posix()
    write(LAY/'layer-state.json',state)
    write(LAY/'psd-manifest.json',{'canvas':list(SIZE),'out':'assets/ciel/psd/ciel-v14c',
          'layers':[{k:r[k] for k in ('name','path')} for r in state['layers']]})
    write(GEN/'generation-log.json',{'count':0,'limit':3,'method':'Python transplant',
          'reason':'Preserve the approved v14b contour, size, position, interior colors and alpha pixel-for-pixel outside the added teeth; reuse the natural tiny v14 fang.'})
    rendered={m:composite(state,m) for m in ('closed','small','large')}
    faces={m:face(im) for m,im in rendered.items()}
    for m,im in rendered.items():
        im.save(PROOF/f'{m}-composite.png');faces[m].save(PROOF/f'{m}-face.png')
    panel([(m,faces[m]) for m in faces],PROOF/'three-states.png')
    prior={v:Image.open(ROOT/f'assets/ciel/generated/{v}/proofs/large-face.png').convert('RGB') for v in ('v14','v14b')}
    prior['v14c']=faces['large']
    panel([(v+' / large',im) for v,im in prior.items()],PROOF/'v14-v14b-v14c-large.png')
    panel([(v+' / large',im.crop(ROI)) for v,im in prior.items()],PROOF/'v14-v14b-v14c-mouth.png',cols=3,side=525,height=375)
    # Combined board with faces AND the matching mouth closeups.
    upper=Image.open(PROOF/'v14-v14b-v14c-large.png')
    panel([(v+' / mouth close-up',im.crop(ROI)) for v,im in prior.items()],PROOF/'comparison-mouth-row.png',cols=3,side=520,height=371)
    lower=Image.open(PROOF/'comparison-mouth-row.png')
    board=Image.new('RGB',(upper.width,upper.height+lower.height))
    board.paste(upper,(0,0));board.paste(lower,(0,upper.height));board.save(PROOF/'v14-v14b-v14c-large-with-zoom.png')
    fangs=Image.open(GEN/'extraction/paired-fangs.png').convert('RGBA')
    target=Image.alpha_composite(Image.open(ROOT/'assets/ciel/generated/v14b/proofs/large-composite.png').convert('RGBA'),fangs)
    target.save(GEN/'selected/edited-full-canvas.png')
    target_face=face(target);target_face.save(GEN/'selected/edited-face.png')
    panel([('v14b face + transferred teeth',target_face),('v14c layer composite',faces['large'])],
          PROOF/'edited-face-vs-composite.png',cols=2,side=627)
    panel([('edited face / mouth',target_face.crop(ROI)),('layer composite / mouth',faces['large'].crop(ROI))],
          PROOF/'edited-face-vs-composite-mouth.png',cols=2,side=525,height=375)
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
    # Same contour measurement on actual composite faces before/after.
    measured={v:corners(im) for v,im in prior.items()}
    write(GEN/'extraction/corner-measurements.json',measured)
    annotation=[]
    for v in ('v14b','v14c'):
        im=prior[v].crop(ROI).resize((700,500),Image.Resampling.NEAREST)
        draw=ImageDraw.Draw(im)
        for key,color in [('left_input_xy','#00a0ee'),('right_input_xy','#ee5090')]:
            x,y=measured[v][key];x=(x-ROI[0])*4;y=(y-ROI[1])*4
            draw.line((0,y,700,y),fill=color,width=2);draw.ellipse((x-5,y-5,x+5,y+5),outline=color,width=2)
        annotation.append((f'{v}: corner dy={measured[v]["height_difference_input_px"]:.1f}px',im))
    panel(annotation,PROOF/'corner-measurements.png',cols=2,side=700,height=500)
    # Show unchanged pixels and the exact tooth-only support; no reference art is used.
    base=np.asarray(Image.open(ROOT/'assets/ciel/layers/v14b/Mouth_Large.png'))
    actual=np.asarray(Image.open(LAY/'Mouth_Large.png'))
    difference=np.any(base!=actual,axis=2)
    diff=Image.new('RGB',SIZE,'#283044');d=np.asarray(diff).copy();d[difference]=[255,90,130]
    panel([('v14c mouth',faces['large'].crop(ROI)),('Only changed pixels (native canvas)',Image.fromarray(d).crop((990,1160,1230,1360)))],
          PROOF/'tooth-only-difference.png',cols=2,side=480,height=400)
    print('Built v14c: 54 layers and all proofs.')

if __name__=='__main__':main()
