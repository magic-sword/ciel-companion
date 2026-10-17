from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np

ROOT = Path(__file__).resolve().parent
src = Image.open(ROOT / 'inputs/neutral-face-crop.png').convert('RGB')
canvas = Image.new('RGB', (4 * 336, 2 * 380), '#282b38')
draw = ImageDraw.Draw(canvas)
for row, (variant, filename) in enumerate([('A', 'A-generated-selected.png'), ('B', 'B-generated.png')]):
    gen = Image.open(ROOT / 'edits' / filename).convert('RGB')
    k = gen.width / src.width
    gen = gen.transform(src.size, Image.Transform.AFFINE,
                        (k, 0, (k-1)/2, 0, k, (k-1)/2), Image.Resampling.BICUBIC)
    gen.save(ROOT / 'edits' / (variant + '-normalized.png'))
    for side, cx in enumerate([208, 612]):
        box = (cx-56, 356, cx+56, 468)
        a = np.array(src.crop(box)).astype(int)
        b = np.array(gen.crop(box)).astype(int)
        diff = np.clip(128 + (b-a)*5, 0, 255).astype('uint8')
        for col, im in enumerate([gen.crop(box), Image.fromarray(diff)]):
            x = (side*2+col)*336
            y = row*380
            draw.text((x+10,y+10), variant + (' R' if side == 0 else ' L') + (' generated x3' if col == 0 else ' signed delta x5'), fill='white')
            canvas.paste(im.resize((336,336)), (x,y+36))
canvas.save(ROOT / 'edits/source-detail-inspection.png')
