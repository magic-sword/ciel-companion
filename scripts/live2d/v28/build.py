"""Register existing extracted artwork to reference facial proportions; no redraw."""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'assets/ciel/generated/v28'
PREV = ROOT / 'assets/ciel/generated/v27'
SIZE = (2172, 2896)
CROP = (550, 650, 1600, 1700)
for folder in ('layers', 'proofs'):
    (OUT / folder).mkdir(parents=True, exist_ok=True)

def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'assets/ciel/current').rglob('*')) if p.is_file()}

before = hashes()
reference = Image.open(ROOT / 'assets/ciel/generated/v25/inputs/happy-reference-face.png').convert('RGBA')
source = Image.open(PREV / 'edits/reference-extracted-01.png').convert('RGBA')
# Manually read landmarks in the unscaled reference crop and current canvas.
ref_nose, ref_chin = (491, 459), (504, 697)
target_nose, target_chin = (1100, 1165), (1106, 1386)
scale = (target_chin[1] - target_nose[1]) / (ref_chin[1] - ref_nose[1])
offset = (target_nose[0] - scale * ref_nose[0], target_nose[1] - scale * ref_nose[1])

def dark_bounds(im, box):
    a = np.asarray(im.crop(box))
    mask = (a[:, :, :3].max(axis=2) < 130) & (a[:, :, 3] > 32)
    y, x = np.nonzero(mask)
    return (int(x.min()) + box[0], int(y.min()) + box[1],
            int(x.max()) + box[0] + 1, int(y.max()) + box[1] + 1)

placements = {'registration': {'reference_nose': ref_nose, 'reference_chin': ref_chin,
    'target_nose': target_nose, 'target_chin': target_chin, 'scale': scale, 'offset': offset,
    'method': 'Uniform registration anchored at nose; scale from nose-to-chin distance'}}
old = json.loads((PREV / 'placement.json').read_text(encoding='utf-8'))
ref_boxes = {'Eye_R_Happy': (145, 285, 410, 420), 'Eye_L_Happy': (585, 285, 845, 420),
             'Mouth_Happy': (420, 515, 570, 595)}
layers = {}
for name, ref_box in ref_boxes.items():
    crop = old[name]['separation_crop']
    b = old[name]['alpha_crop']
    patch = source.crop((crop[0]+b[0], crop[1]+b[1], crop[0]+b[2], crop[1]+b[3]))
    rb = dark_bounds(reference, ref_box)
    pb = dark_bounds(patch, (0, 0, patch.width, patch.height))
    part_scale = scale * (rb[2] - rb[0]) / (pb[2] - pb[0])
    dims = (round(patch.width * part_scale), round(patch.height * part_scale))
    patch = patch.resize(dims, Image.Resampling.LANCZOS)
    pos = (round(offset[0] + scale * (rb[0] + rb[2])/2 - part_scale * (pb[0]+pb[2])/2),
           round(offset[1] + scale * rb[1] - part_scale * pb[1]))
    layer = Image.new('RGBA', SIZE)
    layer.paste(patch, pos)
    layers[name] = layer
    placements[name] = {'source': str((PREV/'edits/reference-extracted-01.png').relative_to(ROOT)),
        'source_crop': [crop[0]+b[0],crop[1]+b[1],crop[0]+b[2],crop[1]+b[3]],
        'reference_dark_bounds': rb, 'uniform_scale': part_scale, 'size': dims,
        'translate': pos, 'bbox': layer.getbbox(),
        'previous_size': [old[name]['bbox'][2]-old[name]['bbox'][0], old[name]['bbox'][3]-old[name]['bbox'][1]]}

# Preserve the earlier, lighter pigment. Place each side by its alpha centroid.
blush = Image.open(ROOT / 'assets/ciel/current/layers/Cheek_Blush.png').convert('RGBA')
result = Image.new('RGBA', SIZE)
blush_moves = []
for box, anchor in [((0,0,1100,SIZE[1]), (275,443)), ((1100,0,SIZE[0],SIZE[1]), (712,437))]:
    piece = blush.crop(box)
    alpha = np.asarray(piece.getchannel('A')).astype(float)
    y,x = np.indices(alpha.shape)
    center = (float((x*alpha).sum()/alpha.sum())+box[0], float((y*alpha).sum()/alpha.sum()))
    goal = (offset[0]+scale*anchor[0], offset[1]+scale*anchor[1])
    move = (round(goal[0]-center[0]), round(goal[1]-center[1]))
    result.paste(piece, (box[0]+move[0],box[1]+move[1]))
    blush_moves.append({'reference_center': anchor, 'source_center': center, 'translate': move})
layers['Cheek_Blush_Happy'] = result
placements['Cheek_Blush_Happy'] = {'source': 'assets/ciel/current/layers/Cheek_Blush.png',
    'sides': blush_moves, 'preview_weight': .45, 'uniform_scale': 1}

manifest = json.loads((ROOT / 'assets/ciel/current/layers.json').read_text(encoding='utf-8'))
assembled = Image.new('RGBA',SIZE)
for entry in manifest['layers']:
    name = entry['name']
    visible = entry.get('visible',True) and not name.startswith(('Eye_L_','Eye_R_','Mouth_'))
    if visible:
        assembled.alpha_composite(Image.open(ROOT / entry['path']).convert('RGBA'))
    if name == 'Face_Shadow_Hair':
        preview=result.copy()
        preview.putalpha(preview.getchannel('A').point(lambda v: round(v*.45)))
        assembled.alpha_composite(preview)
    for slot, part in [('Eye_R_Closed','Eye_R_Happy'),('Eye_L_Closed','Eye_L_Happy'),('Mouth_Large','Mouth_Happy')]:
        if name==slot:
            assembled.alpha_composite(layers[part])
for name, layer in layers.items():
    layer.save(OUT/'layers'/(name+'.png'))
assembled.save(OUT/'proofs/happy-assembled.png')

# Display all panels at the same nose position and nose-to-chin scale.
aligned = reference.transform(SIZE, Image.Transform.AFFINE,
    (1/scale,0,-offset[0]/scale,0,1/scale,-offset[1]/scale), Image.Resampling.BICUBIC)
panels=[('見本（鼻・顎の倍率を統一）',aligned),
        ('調整前（v27）',Image.open(PREV/'proofs/happy-assembled.png')),
        ('サイズ・配置調整（v28）',assembled)]
board=Image.new('RGB',(1575,565),(64,72,104))
draw=ImageDraw.Draw(board)
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',21)
for i,(label,im) in enumerate(panels):
    panel=im.convert('RGBA').crop(CROP)
    bg=Image.new('RGBA',panel.size,(64,72,104,255));bg.alpha_composite(panel)
    board.paste(bg.convert('RGB').resize((525,525),Image.Resampling.LANCZOS),(i*525,40))
    draw.text((i*525+8,8),label,font=font,fill='white')
board.save(OUT/'proofs/happy-face-comparison.png')
assert hashes()==before
assert all(layer.mode=='RGBA' and layer.size==SIZE and layer.getbbox() for layer in layers.values())
(OUT/'placement.json').write_text(json.dumps(placements,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'verification.json').write_text(json.dumps({'current_unchanged':True,'rig_imported':False,
    'layer_count':4,'canvas':SIZE,'artwork_redrawn':False,'blush_preview_weight':.45,
    'reference_display_aligned_by_nose_and_chin':True},indent=2)+'\n',encoding='utf-8')
print(json.dumps(placements,ensure_ascii=False,indent=2))
