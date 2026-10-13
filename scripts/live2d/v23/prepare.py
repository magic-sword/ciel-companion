"""Crop/compare only; never draw or warp character artwork."""
from pathlib import Path
import hashlib, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'assets/ciel/generated/v23'
CROP = (550, 650, 1600, 1700)
def hashes():
    return {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'assets/ciel/current').rglob('*')) if p.is_file()}
def flat(im, color=(224,227,234)):
    bg=Image.new('RGBA', im.size, color+(255,)); bg.alpha_composite(im.convert('RGBA')); return bg.convert('RGB')
def main():
    baseline=OUT/'current-before.json'
    if not baseline.exists(): baseline.write_text(json.dumps(hashes(),indent=2),encoding='utf-8')
    src=Image.open(OUT/'inputs/assembled-current.png').convert('RGBA').crop(CROP)
    src.save(OUT/'inputs/face-crop.png')
    metrics={}
    for p in sorted((OUT/'edits').glob('*-0*.png')):
        im=Image.open(p).convert('RGBA')
        assert im.width==im.height, 'Only uniform scale is allowed'
        im=im.resize(src.size,Image.Resampling.LANCZOS)
        im.save(OUT/'qa'/f'{p.stem}-normalized.png')
        overlay=Image.blend(flat(src),flat(im),.5)
        overlay.save(OUT/'qa'/f'{p.stem}-overlay.png')
        board=Image.new('RGB',(1575,555),(224,227,234)); draw=ImageDraw.Draw(board)
        for k,(label,pic) in enumerate([('Original',flat(src)),(p.stem,flat(im)),('50% overlay',overlay)]):
            board.paste(pic.resize((525,525),Image.Resampling.LANCZOS),(525*k,30)); draw.text((525*k+12,8),label,fill='black')
        board.save(OUT/'qa'/f'{p.stem}-compare.png')
        a=np.asarray(src).astype(float); b=np.asarray(im).astype(float)
        mask=np.ones((1050,1050),bool); mask[190:640,185:940]=False
        diff=np.abs(a-b)
        metrics[p.stem]={'outside_roi_mean_absolute_rgba_difference':float(diff[mask].mean()),
                        'pixel_identical_outside_roi':bool((diff[mask]==0).all()),
                        'note':'Raw model edit is not used as replacement face. Only keyed new artwork is extracted.'}
    (OUT/'qa/edit-metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    print(json.dumps(metrics,indent=2))
if __name__=='__main__': main()
