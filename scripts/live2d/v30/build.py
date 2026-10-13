"""Keep extracted face marks and contour together; proofs use one shared transform."""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'assets/ciel/generated/v30'
raw=Image.open(OUT/'edits/face-details-with-contour-02.png').convert('RGBA')
reference=Image.open(OUT/'inputs/happy-reference-face.png').convert('RGBA')
# Manually read landmarks. Every feature receives the SAME transform.
source_nose=(628,627);source_chin=(641,952)
reference_nose=(491,459);reference_chin=(504,697)
s=(reference_chin[1]-reference_nose[1])/(source_chin[1]-source_nose[1])
ox=reference_nose[0]-s*source_nose[0];oy=reference_nose[1]-s*source_nose[1]
registered=raw.transform(reference.size,Image.Transform.AFFINE,
    (1/s,0,-ox/s,0,1/s,-oy/s),Image.Resampling.BICUBIC)
registered.save(OUT/'face-details-with-contour.png')
font=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',21)
def flatten(im,color):
    bg=Image.new('RGBA',im.size,color+(255,));bg.alpha_composite(im);return bg.convert('RGB')
panels=[('承認見本',reference),('再抽出（輪郭を含む一体画像）',registered),('透明素材・暗い背景',registered)]
board=Image.new('RGB',(1455,525),(64,72,104));draw=ImageDraw.Draw(board)
for i,(label,im) in enumerate(panels):
    color=(250,247,247) if i==1 else (64,72,104)
    board.paste(flatten(im,color).resize((485,485),Image.Resampling.LANCZOS),(i*485,40))
    draw.text((i*485+8,8),label,font=font,fill='white')
board.save(OUT/'proofs/reference-extraction-comparison.png')
# Close comparison of the existing artwork and regenerated extraction.
boxes=[('笑い目',(130,280,850,425)),('赤み・口',(190,410,810,600)),('顎の輪郭',(185,560,810,715))]
board=Image.new('RGB',(1120,660),(250,247,247));draw=ImageDraw.Draw(board)
for row,(label,box) in enumerate(boxes):
    for col,im in enumerate((reference,registered)):
        patch=flatten(im,(250,247,247)).crop(box);patch.thumbnail((540,170),Image.Resampling.LANCZOS)
        board.paste(patch,(col*560+(560-patch.width)//2,row*220+40))
        draw.text((col*560+8,row*220+5),label+('：見本' if col==0 else '：再抽出'),font=font,fill=(35,40,60))
board.save(OUT/'proofs/details-comparison.png')
a=np.asarray(registered)
assert registered.mode=='RGBA' and registered.size==(970,970)
assert a[:,:,3].min()==0 and a[:,:,3].max()==255
(OUT/'placement.json').write_text(json.dumps({'raw_file':'edits/face-details-with-contour-02.png',
    'raw_canvas':raw.size,'registered_canvas':registered.size,'source_nose':source_nose,'source_chin':source_chin,
    'reference_nose':reference_nose,'reference_chin':reference_chin,'uniform_scale':s,'offset':[ox,oy],
    'all_parts_share_transform':True,'parts_separated':False},indent=2)+'\n',encoding='utf-8')
(OUT/'verification.json').write_text(json.dumps({'rgba':True,'true_transparency':True,'canvas':registered.size,
    'contains':['left_happy_eye','right_happy_eye','left_blush','right_blush','mouth','nose','cheek_jaw_contour'],
    'all_parts_share_transform':True,'reference_pixel_identical':False,'generation_count':2,'rig_imported':False,
    'sha256':hashlib.sha256((OUT/'face-details-with-contour.png').read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf-8')
print('V30_COMBINED_EXTRACTION_READY')
