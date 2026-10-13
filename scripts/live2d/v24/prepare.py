from pathlib import Path
import hashlib,json
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'assets/ciel/generated/v24'
CURRENT=ROOT/'assets/ciel/current'
NAMES=[f'Ear_{s}_{p}' for s in ['R','L'] for p in ['Outer','Inner','Base']]+[f'Eye_{s}_{p}' for s in ['R','L'] for p in ['Sclera','Iris']]
def hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in CURRENT.rglob('*') if p.is_file()}
def flat(im,color=(40,43,57)):
    bg=Image.new('RGBA',im.size,(*color,255));bg.alpha_composite(im.convert('RGBA'));return bg.convert('RGB')
def main():
    for d in ['inputs','edits','layers','proofs','qa']: (OUT/d).mkdir(parents=True,exist_ok=True)
    baseline=OUT/'current-before.json'
    if not baseline.exists():baseline.write_text(json.dumps(hashes(),indent=2),encoding='utf-8')
    src=Image.open(ROOT/'assets/ciel/generated/v23/inputs/assembled-current.png').convert('RGBA')
    boxes={'head':(400,0,1800,1400),'eyes':(700,850,1500,1250)}
    for n,b in boxes.items(): flat(src.crop(b)).save(OUT/'inputs'/f'{n}-context.png')
    info={}; board=Image.new('RGB',(1500,1200),(40,43,57)); draw=ImageDraw.Draw(board)
    for i,n in enumerate(NAMES):
        im=Image.open(CURRENT/'layers'/f'{n}.png').convert('RGBA');b=im.getbbox();info[n]=b
        crop=im.crop((b[0]-30,b[1]-40,b[2]+30,b[3]+190))
        flat(crop,(0,255,0)).save(OUT/'inputs'/f'{n}-key.png')
        if n.endswith('_Base'):
            expanded=im.crop((b[0]-30,b[1]-190,b[2]+30,b[3]+190))
            flat(expanded,(0,255,0)).save(OUT/'inputs'/f'{n}-extended-key.png')
        pic=flat(crop);pic.thumbnail((290,550)); x=(i%5)*300;y=(i//5)*600
        board.paste(pic,(x,y+30));draw.text((x+10,y+10),n,fill='white')
    board.save(OUT/'inputs/layers-current.png')
    (OUT/'inputs/source-bounds.json').write_text(json.dumps(info,indent=2),encoding='utf-8');print(info)
if __name__=='__main__':main()
