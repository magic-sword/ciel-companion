"""Mask image edits, extract difference-only RGBA, and verify ordinary compositing.

No artwork is drawn here. Art comes exclusively from the saved image edits.
Image operations: uniform inverse scaling, crop, difference-based masking,
source-over compositing, algebraic RGBA extraction, and diagnostic layout.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT / 'previews'
PREVIEW.mkdir(exist_ok=True)
FULL_SIZE = (2172, 2896)
CROP_BOX = (700, 820, 1520, 1500)
CENTERS = {'R': (208, 412), 'L': (612, 412)}
# Generative edits land a few pixels from the guide center. These selections
# enclose the actual marks, without moving them or including adjacent hair.
SELECTION_CENTERS = {'R': (212, 416), 'L': (604, 416)}
RADIUS = 35
SOURCES = {'A': 'A-generated-selected.png', 'B': 'B-generated.png'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(mask):
    yy, xx = np.where(mask)
    return [int(xx.min()), int(yy.min()), int(xx.max()+1), int(yy.max()+1)] if len(xx) else None


def difference_layer(src, target):
    """Find minimum byte alpha and integer foreground reconstructing target exactly.

    Per channel: T = (a*F + (255-a)*S)/255.
    The lower alpha bound follows from 0 <= F <= 255. RGB is solved,
    never painted or chosen from a palette. No skin-colored rectangular patch.
    """
    s = src.astype(np.float64)
    t = target.astype(np.float64)
    delta = t-s
    bound = np.where(delta >= 0, delta / np.maximum(255-s, 1), -delta / np.maximum(s, 1))
    a = np.ceil(np.maximum(0, bound.max(axis=2))*255 - 1e-9).astype(np.uint8)
    af = a.astype(np.float64)
    f = np.rint((t*255 - s*(255-af[..., None])) / np.maximum(af[..., None], 1))
    f = np.clip(f, 0, 255).astype(np.uint8)
    f[a == 0] = 0
    rgba = np.dstack([f, a])
    reconstructed = np.array(Image.alpha_composite(Image.fromarray(src).convert('RGBA'), Image.fromarray(rgba)).convert('RGB'))
    assert np.array_equal(reconstructed, target), 'RGBA integer reconstruction failed'
    return rgba


def font(size=20):
    path = Path('C:/Windows/Fonts/segoeui.ttf')
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def title(draw, xy, text, size=20):
    draw.text(xy, text, fill='#eef1f8', font=font(size))


def side_by_side(images, labels, path, scale=1.0):
    thumbs = [im.resize((round(im.width*scale), round(im.height*scale)), Image.Resampling.LANCZOS) for im in images]
    width = sum(im.width for im in thumbs)
    out = Image.new('RGB', (width, max(im.height for im in thumbs)+48), '#252835')
    d = ImageDraw.Draw(out)
    x = 0
    for im, label in zip(thumbs, labels):
        title(d, (x+12, 10), label)
        out.paste(im, (x, 48))
        x += im.width
    out.save(path)


def main():
    original = Image.open(ROOT / 'inputs/neutral-full.png').convert('RGB')
    crop = Image.open(ROOT / 'inputs/neutral-face-crop.png').convert('RGB')
    assert original.size == FULL_SIZE and crop.size == (820, 680)
    assert np.array_equal(np.array(original.crop(CROP_BOX)), np.array(crop))
    src = np.array(crop)
    src_full = np.array(original)
    yy, xx = np.mgrid[:680, :820]
    distances = {side: np.sqrt((xx-cx)**2 + (yy-cy)**2) for side, (cx,cy) in SELECTION_CENTERS.items()}
    support = {side: r < RADIUS for side,r in distances.items()}
    # A selection feather only; generated RGB is never repainted. All visible
    # dimple interiors (r <= 29) are admitted unchanged by this spatial mask.
    edge_alpha = np.maximum.reduce([np.clip((RADIUS-r)/6,0,1) for r in distances.values()])
    roi = support['L'] | support['R']
    metrics = {
        'canvas': list(FULL_SIZE), 'crop_box_xyxy': list(CROP_BOX),
        'centers_full': {s: [x+700,y+820] for s,(x,y) in CENTERS.items()},
        'roi_radius': RADIUS, 'generation_calls': 3,
        'selection_centers_full': {s:[x+700,y+820] for s,(x,y) in SELECTION_CENTERS.items()},
        'selection_feather_px': 6,
        'input_sha256': {p.name: sha(p) for p in sorted((ROOT / 'inputs').glob('*.png'))},
        'variants': {},
    }
    outputs = {}
    for variant, filename in SOURCES.items():
        raw = Image.open(ROOT / 'edits' / filename).convert('RGB')
        # A single scale for both axes; pixel-center alignment, no warp/rotation.
        k = raw.width / crop.width
        normalized = raw.transform(crop.size, Image.Transform.AFFINE,
                                   (k, 0, (k-1)/2, 0, k, (k-1)/2), Image.Resampling.BICUBIC)
        normalized.save(ROOT / 'edits' / (variant+'-normalized.png'))
        gen = np.array(normalized)
        delta = gen.astype(int)-src.astype(int)
        magnitude = np.abs(delta).max(axis=2)
        # Ignore tiny regeneration/quantization drift. Alpha alone, derived from
        # RGB difference, admits the generated dimple without painting its shape.
        gate = np.clip((magnitude.astype(float)-3)/4, 0, 1) * edge_alpha
        gate_byte = np.rint(gate*255).astype('uint8')
        Image.fromarray(gate_byte).save(ROOT / 'edits' / (variant+'-difference-mask.png'))
        target_im = Image.composite(normalized, crop, Image.fromarray(gate_byte))
        target = np.array(target_im)
        changed = np.any(target != src, axis=2)
        assert not np.any(changed & ~roi)
        # Ensure no meaningful edit is clipped by the spatial ROI edge.
        boundary = np.zeros_like(roi)
        for cx,cy in SELECTION_CENTERS.values():
            rr = (xx-cx)**2+(yy-cy)**2
            boundary |= (rr >= (RADIUS-1)**2) & (rr <= RADIUS**2)
        target_im.save(ROOT / 'edits' / (variant+'-edited-face.png'))
        # Nearby source hair/line pixels are cooler/darker than the cheek skin.
        protected_local_non_skin = roi & (src.min(axis=2) < 245)
        assert not np.any(changed & protected_local_non_skin), 'Nearby hair changed'
        edited_full = src_full.copy()
        edited_full[820:1500, 700:1520] = target
        edited_im = Image.fromarray(edited_full)
        edited_im.save(ROOT / 'edits' / (variant+'-edited-full.png'))
        reconstructed = original.convert('RGBA')
        layers = {}
        per_side = {}
        for side in ['L', 'R']:
            one_target = src.copy()
            one_target[support[side]] = target[support[side]]
            local_rgba = difference_layer(src, one_target)
            rgba = np.zeros((2896,2172,4), dtype=np.uint8)
            rgba[820:1500,700:1520] = local_rgba
            im = Image.fromarray(rgba, 'RGBA')
            out_path = ROOT / ('Cheek_Dimple_'+side+'_'+variant+'.png')
            im.save(out_path)
            saved = Image.open(out_path).convert('RGBA')
            reconstructed = Image.alpha_composite(reconstructed, saved)
            layers[side] = saved
            effect = local_rgba[:,:,3] > 0
            vis = support[side] & (np.max(np.abs(target.astype(int)-src.astype(int)),axis=2) >= 8)
            b = bounds(effect)
            strong = bounds(vis)
            per_side[side] = {
                'alpha_bbox_full': [b[0]+700,b[1]+820,b[2]+700,b[3]+820] if b else None,
                'visible_delta_ge8_bbox_full': [strong[0]+700,strong[1]+820,strong[2]+700,strong[3]+820] if strong else None,
                'nonzero_alpha_pixels': int(effect.sum()),
                'max_rgb_change': int(np.abs(one_target.astype(int)-src.astype(int)).max()),
                'sha256': sha(out_path),
            }
        rgb_rebuilt = reconstructed.convert('RGB')
        rgb_rebuilt.save(PREVIEW / (variant+'-recomposed-full.png'))
        error = np.abs(np.array(rgb_rebuilt).astype(int)-edited_full.astype(int))
        assert error.max() == 0
        full_roi = np.zeros(src_full.shape[:2],dtype=bool)
        full_roi[820:1500,700:1520] = roi
        changed_full = np.any(edited_full != src_full,axis=2)
        assert not np.any(changed_full & ~full_roi)
        # Full-frame absolute delta (x8), black outside the two dimples.
        diff_full = np.clip(np.abs(edited_full.astype(int)-src_full.astype(int))*8,0,255).astype('uint8')
        Image.fromarray(diff_full).save(PREVIEW / (variant+'-difference-full-x8.png'))
        # Original / final face overview, 1 source pixel per preview pixel.
        side_by_side([crop,target_im], ['Original', variant+' edited'], PREVIEW/(variant+'-face-overview.png'))
        # Requested three columns; both cheeks enlarged by exactly 3x.
        grid = Image.new('RGB',(1008,2*390+42),'#252835')
        d = ImageDraw.Draw(grid)
        for col,label in enumerate(['Original x3', variant+' edited x3', 'Absolute delta x8 / view x3']):
            title(d,(col*336+10,10),label,18)
        for row,side in enumerate(['R','L']):
            cx,cy=CENTERS[side]
            box=(cx-56,cy-56,cx+56,cy+56)
            local_delta=np.abs(target[cy-56:cy+56,cx-56:cx+56].astype(int)-src[cy-56:cy+56,cx-56:cx+56].astype(int))
            items=[crop.crop(box),target_im.crop(box),Image.fromarray(np.clip(local_delta*8,0,255).astype('uint8'))]
            y=42+row*390
            title(d,(12,y+3),side+(' (screen left)' if side=='R' else ' (screen right)'),18)
            for col,im in enumerate(items):
                grid.paste(im.resize((336,336),Image.Resampling.NEAREST),(col*336,y+30))
        grid.save(PREVIEW/(variant+'-comparison-3x.png'))
        dark_full = Image.new('RGBA',FULL_SIZE,'#242833')
        for im in layers.values():
            dark_full=Image.alpha_composite(dark_full,im)
        dark_full.convert('RGB').save(PREVIEW/(variant+'-layers-dark-full.png'))
        rebuild_crop=rgb_rebuilt.crop(CROP_BOX)
        side_by_side([target_im,rebuild_crop], [variant+' edited target', 'Saved L+R recomposed: exact'], PREVIEW/(variant+'-recomposition-check.png'))
        metrics['variants'][variant]={
            'generated_source': 'edits/'+filename,'generated_sha256':sha(ROOT/'edits'/filename),
            'generated_size':list(raw.size),'inverse_uniform_scale':1/k,
            'raw_normalized_changed_pixels':int((magnitude>0).sum()),
            'raw_normalized_changed_pixels_outside_roi':int(((magnitude>0)&~roi).sum()),
            'final_changed_pixels':int(changed.sum()),'final_changed_pixels_outside_roi':0,
            'roi_boundary_max_change':int(np.abs(target.astype(int)-src.astype(int))[boundary].max()),
            'local_protected_non_skin_changed_pixels':int((changed & protected_local_non_skin).sum()),
            'recomposite_max_channel_error':int(error.max()),
            'recomposite_different_pixels':int(np.any(error>0,axis=2).sum()),
            'sides':per_side,
        }
        outputs[variant]={'edited':target_im,'layers':layers}
    # Four actual transparent layers on a dark background, enlarged 3x.
    dark_grid=Image.new('RGB',(4*336,390),'#242833')
    d=ImageDraw.Draw(dark_grid)
    col=0
    for variant in ['A','B']:
        for side in ['L','R']:
            cx,cy=CENTERS[side]
            patch=outputs[variant]['layers'][side].crop((cx+700-56,cy+820-56,cx+700+56,cy+820+56))
            bg=Image.new('RGBA',patch.size,'#242833')
            actual=Image.alpha_composite(bg,patch).convert('RGB')
            title(d,(col*336+10,10),variant+' / '+side+' / actual alpha x3',18)
            dark_grid.paste(actual.resize((336,336),Image.Resampling.NEAREST),(col*336,44))
            col+=1
    dark_grid.save(PREVIEW/'layers-dark-3x.png')
    side_by_side([crop,outputs['A']['edited'],outputs['B']['edited']],['Original','A - round','B - crescent'],PREVIEW/'variants-overview.png',0.85)
    (ROOT/'verification.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(metrics,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
