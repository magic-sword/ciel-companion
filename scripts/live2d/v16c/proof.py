"""Review only: uniform placement, composition, and viewport cropping of proofs."""
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / 'assets/ciel/generated/v16c'
PROOFS = GEN / 'proofs'
PROOFS.mkdir(exist_ok=True)
CONFIG = json.loads((ROOT / 'assets/ciel/layers/v16/placement.json').read_text(encoding='utf-8'))
BODY = ROOT / 'assets/ciel/layers/v16/dressed/Body.png'

def place(art):
    t = CONFIG['transforms']['Jacket']
    scaled = art.resize(tuple(round(d*t['uniform_scale']) for d in art.size), Image.Resampling.LANCZOS)
    placed = Image.new('RGBA', tuple(CONFIG['canvas']))
    placed.alpha_composite(scaled, tuple(t['translate']))
    return placed

def panel(items, path, width=720, viewport=None):
    tiles=[]
    for label,art in items:
        if viewport:
            art=art.crop(viewport)  # Proof viewport only, never delivered art.
        if width:
            art=art.resize((width,round(art.height*width/art.width)),Image.Resampling.LANCZOS)
        tile=Image.new('RGBA',(art.width,art.height+48),'#424966')
        tile.alpha_composite(art,(0,48))
        ImageDraw.Draw(tile).text((14,10),label,font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24),fill='white')
        tiles.append(tile)
    out=Image.new('RGB',(sum(t.width for t in tiles),max(t.height for t in tiles)))
    x=0
    for tile in tiles:
        out.paste(tile,(x,0))
        x+=tile.width
    out.save(path)

if __name__ == '__main__':
    candidate=int(sys.argv[1])
    front=Image.open(GEN/f'jacket-front-{candidate:02}.png').convert('RGBA')
    body=Image.open(BODY).convert('RGBA')
    placed=place(front)
    dressed=Image.alpha_composite(body,placed)
    panel([('Body only',body),(f'Body + v16c candidate {candidate:02}',dressed)],PROOFS/f'body-candidate-{candidate:02}.png',viewport=(250,1350,1920,2850))
