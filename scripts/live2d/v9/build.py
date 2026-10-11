"""Reproducible v9 assembly. Python 3.8+, Pillow, numpy; writes only v9 roots.

python -I scripts/live2d/v9/build.py init
python -I scripts/live2d/v9/build.py render <placement.json> <output-subdirectory>
All placements sample original RGBA files once using premultiplied alpha.
"""
import copy
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / 'assets/ciel/generated/v9'
OUT = ROOT / 'assets/ciel/layers/v9'
SIZE = (2172, 2896)
HEAD = (318, 236, 1854, 1772)
BG = (64, 72, 104, 255)
ORDER = ['Hair_Back', 'Body', 'Choker_Back', 'Neck', 'Outer_R', 'Outer_L', 'Choker', 'Face_Skin', 'Nose', 'Mouth', 'Eye_R', 'Eye_L', 'Ear_R', 'Ear_L', 'Hair_Ahoge', 'Hair_Side_R', 'Hair_Side_L', 'Hair_Front', 'Brow_R', 'Brow_L']

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def rgba(path):
    return Image.open(path).convert('RGBA')

def font(size=24):
    return ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc', size)

def on_bg(im, color=BG):
    b = Image.new('RGBA', im.size, color)
    b.alpha_composite(im)
    return b.convert('RGB')

def sheet(images, labels, path, crop=None, scale=.5, bg=BG):
    views = [on_bg(i, bg).crop(crop) if crop else on_bg(i, bg) for i in images]
    w, h = [round(x * scale) for x in views[0].size]
    out = Image.new('RGB', (w * len(views), h + 48), bg[:3])
    d = ImageDraw.Draw(out)
    for n, (im, label) in enumerate(zip(views, labels)):
        out.paste(im.resize((w, h), Image.Resampling.LANCZOS), (n * w, 48))
        d.text((n*w+14, 10), label, fill='white' if sum(bg[:3])<420 else '#283148', font=font(22))
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path)

def transform(p):
    src = ROOT / p['source']
    if sha(src) != p['sha256']:
        raise ValueError('Source changed: '+str(src))
    im = rgba(src)
    if 'source_bezier' in p:
        path = p['source_bezier']
        points = [path[0]]
        previous = np.array(path[0], dtype=float)
        for segment in path[1:]:
            q,r,s = [np.array(v,dtype=float) for v in segment]
            for t in np.linspace(0,1,65)[1:]:
                pt=(1-t)**3*previous+3*(1-t)**2*t*q+3*(1-t)*t*t*r+t**3*s
                points.append(tuple(pt))
            previous=s
        mask=Image.new('L',(im.width*3,im.height*3))
        ImageDraw.Draw(mask).polygon([(round(x*3),round(y*3)) for x,y in points],fill=255)
        mask=mask.resize(im.size,Image.Resampling.LANCZOS)
        im.putalpha(ImageChops.multiply(im.getchannel('A'),mask))
    if p.get('remove_detached_alpha'):
        from scipy import ndimage
        alpha=np.asarray(im.getchannel('A'))
        labels,count=ndimage.label(alpha>32)
        sizes=np.bincount(labels.ravel()); sizes[0]=0
        support=labels==sizes.argmax()
        support=ndimage.binary_dilation(support,iterations=2)
        im.putalpha(Image.fromarray(np.where(support,alpha,0).astype('uint8')))
    if p.get('alpha_gain'):
        gain=p['alpha_gain']
        im.putalpha(im.getchannel('A').point(lambda v:min(255,round(v*gain))))
    # Masks are in original source pixels, never applied to an already resized layer.
    if 'source_rect' in p:
        mask = Image.new('L', im.size)
        ImageDraw.Draw(mask).rectangle(tuple(p['source_rect']), fill=255)
        im.putalpha(ImageChops.multiply(im.getchannel('A'), mask))
    if 'source_polygon' in p:
        mask = Image.new('L', (im.width*2, im.height*2))
        ImageDraw.Draw(mask).polygon([(round(x*2), round(y*2)) for x,y in p['source_polygon']], fill=255)
        mask = mask.resize(im.size, Image.Resampling.LANCZOS)
        im.putalpha(ImageChops.multiply(im.getchannel('A'), mask))
    a,b,c,d,e,f = p['matrix']
    det = a*e-b*d
    inv = (e/det, -b/det, (b*f-e*c)/det, -d/det, a/det, (d*c-a*f)/det)
    layer = im.convert('RGBa').transform(SIZE, Image.Transform.AFFINE, inv, Image.Resampling.BICUBIC).convert('RGBA')
    if 'canvas_rect' in p:
        mask = Image.new('L', SIZE)
        ImageDraw.Draw(mask).rectangle(tuple(p['canvas_rect']), fill=255)
        layer.putalpha(ImageChops.multiply(layer.getchannel('A'), mask))
    if p.get('opacity', 1) != 1:
        layer.putalpha(layer.getchannel('A').point(lambda v:round(v*p['opacity'])))
    return layer

def correction(p, scale=1, dx=0, dy=0, pivot=None, angle=0):
    pivot = pivot or p['anchor_canvas']
    x,y = pivot
    a,b,c,d,e,f = p['matrix']
    co,si = math.cos(math.radians(angle))*scale, math.sin(math.radians(angle))*scale
    p['matrix'] = [co*a-si*d,co*b-si*e,co*(c-x)-si*(f-y)+x+dx,
                   si*a+co*d,si*b+co*e,si*(c-x)+co*(f-y)+y+dy]
    p.setdefault('corrections', []).append(dict(scale=scale,dx=dx,dy=dy,pivot=pivot,angle_degrees=angle))

def composite(layers, omit=()):
    out = Image.new('RGBA', SIZE)
    for name, im in layers.items():
        if name not in omit:
            out.alpha_composite(im)
    return out

def layers_for(config):
    layers = {}
    for p in sorted(config['layers'], key=lambda x:x['z']):
        if not p.get('enabled', True):
            continue
        if p.get('type') == 'ellipse':
            im=Image.new('RGBA', SIZE)
            small=Image.new('RGBA',(SIZE[0]*2,SIZE[1]*2))
            ImageDraw.Draw(small).ellipse(tuple(round(v*2) for v in p['box']),fill=tuple(p['color'])+(255,))
            im=small.resize(SIZE,Image.Resampling.LANCZOS)
        elif p.get('type') == 'cast_shadow':
            owner=next(q for q in config['layers'] if q['name']==p['owner'])
            silhouette=transform(owner).getchannel('A')
            shifted=Image.new('L',SIZE)
            shifted.paste(silhouette,tuple(p['offset']))
            shifted=shifted.filter(ImageFilter.GaussianBlur(p['edge_blur']))
            alpha=ImageChops.multiply(shifted,layers[p['clip_to']].getchannel('A'))
            alpha=alpha.point(lambda v:round(v*p['opacity']))
            im=Image.new('RGBA',SIZE,tuple(p['color'])+(0,))
            im.putalpha(alpha)
        elif p.get('type') == 'shadow':
            mask = layers[p['clip_to']].getchannel('A')
            yy = np.arange(SIZE[1], dtype=np.float32)[:,None]
            strength = np.clip((p['fade_end_y']-yy)/(p['fade_end_y']-p['full_until_y']), 0, 1)*p['opacity']
            alpha = (np.asarray(mask, dtype=np.float32)*strength).astype('uint8')
            im = Image.new('RGBA', SIZE, tuple(p['color'])+(0,))
            im.putalpha(Image.fromarray(alpha))
        else:
            im = transform(p)
        layers[p['name']] = im
    return layers

def render(config, dest, export=False):
    dest.mkdir(parents=True, exist_ok=True)
    layers = layers_for(config)
    comp = composite(layers)
    comp.save(dest/'compose.png')
    if export:
        for n, im in layers.items():
            im.save(dest/(n+'.png'))
    master = rgba(ROOT/'assets/ciel/master/ciel-upper-body-2x.png')
    v8 = rgba(ROOT/'assets/ciel/layers/v8/_compose.png')
    sheet([master,v8,comp], ['原画','v8','v9 候補'], dest/'compare-face.png', HEAD, .5)
    sheet([master,v8,comp], ['原画','v8','v9 候補'], dest/'compare-upper.png', scale=.3)
    return layers, comp

def init():
    GEN.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    frames = read_json(ROOT/'assets/ciel/generated/v8/frames.json')
    config = dict(schema=1, canvas=list(SIZE), coordinates='L/R はキャラクター視点。行列 [a,b,c,d,e,f]: x=a*u+b*v+c, y=d*u+e*v+f。基準点はキャンバス座標。', stage='0: v8 originals baseline', layers=[])
    for z,n in enumerate(ORDER):
        suffix = '-v2' if n in ['Choker','Choker_Back','Hair_Side_R','Hair_Side_L','Hair_Front'] else ''
        source = ROOT/('assets/ciel/generated/v8/parts/'+n+suffix+'.png')
        im = rgba(source)
        x0,y0,x1,y1 = frames[n]['box']
        p = dict(name=n,source=source.relative_to(ROOT).as_posix(),sha256=sha(source),source_size=list(im.size),frame=frames[n]['box'],matrix=[(x1-x0)/im.width,0,x0,0,(y1-y0)/im.height,y0],anchor_canvas=[(x0+x1)/2,(y0+y1)/2],z=z*10,opacity=1,blend='normal',status='v8 inherited; v9 not yet reviewed',corrections=[],initial_fit_reason='v8 枠変換を段階1の比較基準として明示的に継承。追加補正は原則等方倍率。')
        config['layers'].append(p)
    write_json(GEN/'placement-stage0.json', config)
    old_files = list((ROOT/'assets/ciel/generated/v8').rglob('*'))+list((ROOT/'assets/ciel/layers/v8').rglob('*'))+[ROOT/'assets/ciel/master/ciel-upper-body-2x.png',ROOT/'docs/ciel-codex-consult-parts-ja.md',ROOT/'docs/ciel-live2d-rebuild-analysis-plan-ja.md',ROOT/'scripts/live2d/assemble-v8.py']
    write_json(GEN/'input-sha256.json', {p.relative_to(ROOT).as_posix():sha(p) for p in old_files if p.is_file()})
    stage1 = copy.deepcopy(config)
    stage1['stage'] = '1: placement rescue candidate'
    for p in stage1['layers']:
        n = p['name']
        if n.startswith('Eye_'):
            correction(p,1.05,pivot=[930 if n=='Eye_R' else 1282,1050])
        if n=='Choker':
            correction(p,.93,dy=-40,pivot=[1117,1490])
        if n=='Choker_Back':
            correction(p,.98,dy=8,pivot=[1117,1440])
        if n=='Hair_Back':
            p['canvas_rect'] = [0,365,SIZE[0],SIZE[1]]
            p['mask_reason'] = '頭頂の重複を隠す仮切り分け。正面で前髪と耳の下へ入る。動作用の補完は段階3。'
    write_json(GEN/'placement-stage1.json', stage1)
    layers,comp = render(stage1,GEN/'stage1')
    refs = GEN/'references'
    refs.mkdir(exist_ok=True)
    master = rgba(ROOT/'assets/ciel/master/ciel-upper-body-2x.png')
    on_bg(master).crop(HEAD).save(refs/'master-head.png')
    boxes = {'Hair_Front':[600,230,1610,1240], 'Hair_Side_R':[460,520,1020,1820], 'Hair_Side_L':[1200,520,1760,1820]}
    for n,box in boxes.items():
        on_bg(master).crop(box).save(refs/(n+'-frame.png'))
    composite(layers, ['Hair_Front','Hair_Side_R','Hair_Side_L']).save(refs/'current-no-front.png')
    write_json(refs/'frames.json', boxes)
    print('Initialized baseline, stage1, hashes, references')

if __name__=='__main__':
    if sys.argv[1]=='init':
        init()
    elif sys.argv[1]=='render':
        config = read_json(ROOT/sys.argv[2])
        destination = (ROOT/sys.argv[3]).resolve()
        if GEN not in destination.parents and OUT not in destination.parents and destination != OUT:
            raise ValueError('Output must be in v9 roots')
        render(config, destination, '--export' in sys.argv)
        print('Rendered', destination)
