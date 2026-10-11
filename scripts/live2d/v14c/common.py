"""Extract generated mouth pixels without drawing, scaling or relocating the mouth.

Run from any cwd with Python/Pillow/NumPy/SciPy. All writes stay inside v14c.
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
GEN = ROOT / 'assets/ciel/generated/v14c'
LAY = ROOT / 'assets/ciel/layers/v14c'
PROOF = GEN / 'proofs'
CROP = (318, 236, 1854, 1772)
SIZE = (2172, 2896)
ROI = (555, 780, 730, 905)  # Excludes nose, jaw, cheeks, eyes and hair.
SELECTED = {'small': 'small-03', 'large': 'large-01'}
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
