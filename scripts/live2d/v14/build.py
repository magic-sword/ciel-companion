"""Extract generated mouth pixels without drawing, scaling or relocating the mouth.

Run from any cwd with Python/Pillow/NumPy/SciPy. All writes stay inside v14.
The only geometric transform is the inverse of the documented v11 face crop.
"""
import copy
import hashlib
import json
import shutil
import warnings
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / 'assets/ciel/generated/v14'
LAY = ROOT / 'assets/ciel/layers/v14'
PROOF = GEN / 'proofs'
CROP = (318, 236, 1854, 1772)
SIZE = (2172, 2896)
ROI = (555, 780, 730, 905)  # Excludes nose, jaw, cheeks, eyes and hair.
SELECTED = {'small': 'small-03', 'large': 'large-04'}
CLOSED = ['Mouth_Skin_Upper', 'Mouth_Skin_Lower', 'Mouth_Line_Upper', 'Mouth_Line_Lower']
FONT = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 22)

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def bbox(mask):
    y, x = np.where(mask)
    return [int(x.min()), int(y.min()), int(x.max()+1), int(y.max()+1)]

def flatten(im, color='#f4f5f7'):
    bg = Image.new('RGBA', im.size, color)
    bg.alpha_composite(im.convert('RGBA'))
    return bg.convert('RGB')

def face(im):
    return flatten(im.crop(CROP).resize((1254, 1254), Image.Resampling.LANCZOS))

def composite(state, mouth='closed', blink=False):
    im = Image.new('RGBA', SIZE)
    for row in state['layers']:
        name = row['name']
        on = row['visible']
        if name.startswith('Mouth_'):
            if name in CLOSED:
                on = True if state.get('mouth_overlay') or name.startswith('Mouth_Skin_') else mouth == 'closed'
            elif name in ('Mouth_Small', 'Mouth_Large'):
                on = name.lower() == 'mouth_' + mouth
            elif name.startswith(('Mouth_Small_', 'Mouth_Large_')):
                on = name.startswith('Mouth_' + mouth.title() + '_')
        if blink and name.startswith('Eye_'):
            on = name.endswith('_Closed')
        if on:
            im.alpha_composite(Image.open(ROOT / row['path']).convert('RGBA'))
    return im

def panel(items, path, cols=3, side=520, height=None):
    height = height or side
    rows = (len(items)+cols-1)//cols
    sheet = Image.new('RGB', (cols*side, rows*(height+42)), '#e7e9ee')
    draw = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(items):
        x, y = (i%cols)*side, (i//cols)*(height+42)
        draw.text((x+12, y+10), label, font=FONT, fill='#192338')
        im = flatten(im) if im.mode == 'RGBA' else im.convert('RGB')
        sheet.paste(im.resize((side,height), Image.Resampling.LANCZOS), (x,y+42))
    sheet.save(path)

def extract(original, edited, label):
    a = np.asarray(original).astype(np.int16)
    b = np.asarray(edited).astype(np.int16)
    diff = np.abs(b-a).max(axis=2)
    gate = np.zeros(diff.shape, dtype=bool)
    x0,y0,x1,y1 = ROI
    gate[y0:y1,x0:x1] = True
    # Mouth differences, plus every original lip pixel so the old line is erased.
    changed = (diff > 8) & gate
    changed = ndi.binary_closing(changed, iterations=2)
    labels, n = ndi.label(changed)
    areas = np.bincount(labels.ravel())
    # Use explicit component IDs rather than assuming background size/order.
    core = np.isin(labels, [i for i in range(1,n+1) if areas[i] >= 12])
    closed_ink = (a[:,:,0]-a[:,:,1] > 7) & gate
    core |= closed_ink
    core = ndi.binary_fill_holes(ndi.binary_closing(core, iterations=3))
    core = ndi.binary_dilation(core, iterations=6)
    distance = ndi.distance_transform_edt(~core)
    t = np.clip(1-distance/9, 0, 1)
    alpha = np.rint(255*t*t*(3-2*t)).astype(np.uint8)
    alpha[~gate] = 0
    patch = edited.convert('RGBA')
    patch.putalpha(Image.fromarray(alpha))
    patch.save(GEN / 'extraction' / f'{label}-input-space.png')
    Image.fromarray(alpha).save(GEN / 'extraction' / f'{label}-mask.png')
    Image.fromarray(np.uint8(np.clip(diff*8,0,255))).save(GEN / 'extraction' / f'{label}-difference-x8.png')
    # Pillow resizes RGBA with premultiplied-alpha handling.
    inverse = patch.resize((1536,1536), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', SIZE)
    canvas.paste(inverse, CROP[:2])
    canvas.save(LAY / f'Mouth_{label.title()}.png')
    metrics = {'source': SELECTED[label], 'roi_input_xyxy': ROI,
               'difference_threshold': 8, 'opaque_margin_input_px': 6,
               'feather_input_px': 9, 'alpha_bbox_canvas': list(canvas.getbbox()),
               'outside_mouth_generated_difference_mae': float(np.abs(b-a)[~gate].mean()),
               'outside_mouth_generated_changed_pixels': int(np.count_nonzero((diff>0)&~gate))}
    return canvas, alpha, metrics

def mouth_landmarks(im):
    a = np.asarray(im).astype(np.int16)
    x0,y0,x1,y1 = ROI
    mask = (a[:,:,0]-a[:,:,1]>12) & (a[:,:,1]<224)
    gate = np.zeros(mask.shape, bool); gate[y0:y1,x0:x1] = True
    mask &= gate
    bb = bbox(mask)
    # Anatomical mouth corners estimated at the outside bands of visible pigment.
    corners=[]
    for lo,hi in ((bb[0],bb[0]+4),(bb[2]-4,bb[2])):
        yy,xx=np.where(mask[:,lo:hi])
        corners.append([float((xx+lo).mean()),float(yy.mean())])
    anchor=np.mean(corners,axis=0)
    return {'pigment_bbox_input':bb, 'corner_midpoint_input':anchor.tolist(),
            'corner_midpoint_canvas':(anchor*1536/1254+np.array(CROP[:2])).tolist(),
            'pigment_size_canvas':[(bb[2]-bb[0])*1536/1254,(bb[3]-bb[1])*1536/1254]}

def main():
    for d in (LAY, PROOF, GEN/'selected', GEN/'extraction', GEN/'private'):
        d.mkdir(parents=True, exist_ok=True)
    original = Image.open(GEN/'inputs/v11-face-closed.png').convert('RGB')
    base = Image.open(GEN/'inputs/v11-neutral.png').convert('RGBA')
    old = read(ROOT/'assets/ciel/layers/v11/layer-state.json')
    state = copy.deepcopy(old)
    state['layers'] = []
    for row in old['layers']:
        if row['name'].startswith(('Mouth_Small_', 'Mouth_Large_')):
            continue
        r = copy.deepcopy(row)
        dest = LAY / (r['name']+'.png')
        shutil.copyfile(ROOT/r['path'],dest)
        r['path']=dest.relative_to(ROOT).as_posix()
        if r['name'] in CLOSED:
            r['group']=None
        state['layers'].append(r)
        if r['name']=='Mouth_Line_Lower':
            for j,label in enumerate(('small','large')):
                name='Mouth_'+label.title()
                state['layers'].append({'name':name,'path':f'assets/ciel/layers/v14/{name}.png',
                    'z':94+j,'visible':False,'group':'mouth_'+label,'clip':None,
                    'source':'v14 generated '+SELECTED[label],
                    'description':'生成された口内・歯・舌・輪郭と周囲の肌を一体で抽出。縁だけ透明化。',
                    'hidden_by':'別の口状態と排他','motion':'口の開閉（状態切替）'})
    state['mouth_overlay']=True
    state['mouth_switch']={'closed':CLOSED,'small':CLOSED+['Mouth_Small'],'large':CLOSED+['Mouth_Large'],
                           'rule':'Keep v11 closed mouth and skin visible underneath. Enable exactly one open overlay, or neither for closed. Open overlays fully cover the closed line.'}
    for preset in state['presets'].values():
        preset['mouth_visible_layers']=state['mouth_switch'][preset['mouth']]
    write(LAY/'layer-state.json',state)
    write(LAY/'psd-manifest.json',{'canvas':list(SIZE),'out':'assets/ciel/psd/ciel-v14',
          'layers':[{k:r[k] for k in ('name','path')} for r in state['layers']]})
    metrics={}
    edits={}
    alphas={}
    for label, name in SELECTED.items():
        shutil.copyfile(GEN/f'candidates/{name}.png',GEN/f'selected/{name}.png')
        edited=Image.open(GEN/f'selected/{name}.png').convert('RGB')
        edits[label]=edited
        _,alphas[label],metrics[label]=extract(original,edited,label)
    renders={m:composite(state,m) for m in ('closed','small','large')}
    faces={m:face(im) for m,im in renders.items()}
    for m,im in renders.items():
        im.save(PROOF/f'{m}-composite.png')
        faces[m].save(PROOF/f'{m}-face.png')
    panel([(m,faces[m]) for m in faces],PROOF/'three-states.png')
    comparisons=[]
    for v in ('v12','v13','v14'):
        s=state if v=='v14' else read(ROOT/f'assets/ciel/layers/{v}/layer-state.json')
        for m in ('closed','small','large'):
            comparisons.append((f'{v} / {m}',faces[m] if v=='v14' else face(composite(s,m))))
    panel(comparisons,PROOF/'v12-v13-v14.png',side=440)
    pairs=[]
    zooms=[]
    for m in ('small','large'):
        pairs.extend([(m+' / generated',edits[m]),(m+' / extracted over v11',faces[m])])
        zooms.extend([(m+' / generated',edits[m].crop(ROI)),(m+' / extracted over v11',faces[m].crop(ROI))])
        rgb=np.asarray(renders[m].crop(CROP).convert('RGB')).astype(np.int16)
        target=np.asarray(edits[m].resize((1536,1536),Image.Resampling.LANCZOS)).astype(np.int16)
        alpha=np.asarray(Image.open(LAY/f'Mouth_{m.title()}.png'))[236:1772,318:1854,3]
        core=ndi.binary_erosion(alpha==255,iterations=3)
        err=np.abs(rgb-target)
        metrics[m]['inverse_space_opaque_core_mae']=float(err[core].mean())
        metrics[m]['inverse_space_opaque_core_max']=int(err[core].max())
        err2=np.abs(np.asarray(faces[m]).astype(np.int16)-np.asarray(edits[m]).astype(np.int16))
        metrics[m]['input_space_opaque_core_mae']=float(err2[alphas[m]==255].mean())
        # Outside the patch the delivered face equals the v11 neutral pixel-for-pixel.
        support=np.asarray(Image.open(LAY/f'Mouth_{m.title()}.png'))[:,:,3]>0
        fullerr=np.any(np.asarray(renders[m])!=np.asarray(base),axis=2)
        metrics[m]['changed_pixels_outside_patch']=int(np.count_nonzero(fullerr&~support))
        metrics[m]['landmarks']=mouth_landmarks(edits[m])
    panel(pairs,PROOF/'generated-vs-composite.png',cols=2,side=627)
    panel(zooms,PROOF/'generated-vs-composite-mouth.png',cols=2,side=525,height=375)
    metrics['closed_landmarks']=mouth_landmarks(original)
    panel([(m,flatten(Image.open(LAY/f'Mouth_{m.title()}.png').crop((990,1160,1230,1360)),color))
           for m in ('small','large') for color in ('#fafafa','#252938')],
          PROOF/'parts-light-dark.png',cols=2,side=480,height=400)
    frames=[faces[m].resize((752,752),Image.Resampling.LANCZOS) for m in ('closed','small','large','small')]
    # One shared palette avoids apparent color flicker from per-frame quantization.
    stack=Image.new('RGB',(752,752*4))
    for i,f in enumerate(frames): stack.paste(f,(0,i*752))
    palette=stack.quantize(colors=256)
    q=[f.quantize(palette=palette,dither=Image.Dither.NONE) for f in frames]
    q[0].save(PROOF/'mouth-switch.gif',save_all=True,append_images=q[1:],duration=[750,600,750,600],loop=0,disposal=2)
    frames[0].save(PROOF/'mouth-switch.png',save_all=True,append_images=frames[1:],duration=[750,600,750,600],loop=0)
    # Candidate sheet, retained locally (candidate source directory is gitignored).
    items=[]
    for name in sorted(read(GEN/'generation-log.json')['outputs']):
        im=Image.open(GEN/f'candidates/{name}.png')
        items.append((name+(' / selected' if name in SELECTED.values() else ''),im))
    panel(items,PROOF/'candidates.png',cols=4,side=400)
    panel([('PRIVATE anime reference',Image.open(ROOT/'.local/reference/anime-mouth-zoom.png')),
           ('v14 small',edits['small'].crop(ROI)),('v14 large',edits['large'].crop(ROI))],
          GEN/'private/reference-mouths-PRIVATE.png',cols=3,side=500,height=350)
    write(GEN/'extraction/metrics.json',metrics)
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':
    main()
