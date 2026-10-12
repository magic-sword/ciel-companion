"""Deliver image-generated sleeve art using inherited uniform placement only."""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
import shutil
import numpy as np
from PIL import Image
from proof import ROOT, GEN, PROOFS, CONFIG, BODY, place, panel

LAY = ROOT / 'assets/ciel/layers/v16c'
SOURCE = ROOT / 'assets/ciel/generated/v16/jacket.png'
SELECTED = GEN / 'jacket-front-03.png'
TOOL_DIR = 'C:/Users/prog/.codex/generated_images/01a12d7d-99ab-7452-b85d-57836a30c31e/'
TOOL_FILES = [
    'exec-34e85d3d-510a-4e02-b2b7-d80e409b4ed4.png',
    'exec-3ac264e4-caa7-4104-9d0b-124dbc06f377.png',
    'exec-fe1db5fe-76a3-450a-afbf-c8c7c87c6080.png',
    'exec-2cf679de-4451-4a9b-91ff-0ad41eade923.png',
]

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def main():
    expected = {
        'assets/ciel/generated/v16/jacket.png': '9bfeb9eabf54d1e6b5b3d23841cb99e997e2189129695541c6c414711ac6a40a',
        'assets/ciel/layers/v16/placement.json': 'dd21a1e611684dd7aefa6f81ce395488e0218124af8e43cdc5934409d0aa40a4',
        'assets/ciel/layers/v16/dressed/Body.png': '5d8ca00dd0fc193ac7618f4c0bdd1221cc6036d8b932700afb47baa0bf01d294',
    }
    assert all(sha(ROOT/p)==h for p,h in expected.items())
    original=Image.open(SOURCE).convert('RGBA')
    front=Image.open(SELECTED).convert('RGBA')
    assert front.size==original.size==(1441,1092)
    shutil.copyfile(SELECTED,GEN/'jacket-front.png')
    placed=place(front)
    placed.save(LAY/'Jacket_Front.png')
    body=Image.open(BODY).convert('RGBA')
    dressed=Image.alpha_composite(body,placed)
    dressed.save(PROOFS/'body-composite.png')
    panel([('v16 jacket.png',original),('v16c sleeves + shoulder fur (03)',front)],PROOFS/'comparison-side-by-side.png',width=None)
    overlay=Image.alpha_composite(original,front)
    overlay.save(PROOFS/'overlay.png')
    half=front.copy()
    # Opacity change is restricted to this disposable review copy.
    half.putalpha(half.getchannel('A').point(lambda a:round(a*.5)))
    panel([('Original + front at 50% opacity',Image.alpha_composite(original,half))],PROOFS/'overlay-half.png',width=None)
    panel([('Body only',body),('Body + v16c front',dressed)],PROOFS/'body-comparison.png',viewport=(250,1350,1920,2850))
    panel([('Body only',body),('Body + v16c front - chest detail',dressed)],PROOFS/'body-chest-detail.png',width=900,viewport=(650,1500,1550,2200))
    previous=Image.open(ROOT/'assets/ciel/layers/v16b/Jacket_Front.png').convert('RGBA')
    panel([('Body only',body),('Body + v16b front',Image.alpha_composite(body,previous)),('Body + v16c front',dressed)],PROOFS/'body-v16b-v16c.png',width=600,viewport=(250,1350,1920,2850))
    panel([('Jacket_Front - 2172 x 2896',placed)],PROOFS/'placed-front.png',width=750)
    candidates=[]
    calls=[]
    for n,tool_name in enumerate(TOOL_FILES,1):
        path=GEN/f'jacket-front-{n:02}.png'
        art=Image.open(path).convert('RGBA')
        assert art.size==original.size
        candidates.append((f'Candidate {n:02}'+(' - SELECTED' if n==3 else ''),art))
        call=json.loads((GEN/f'generation-{n:02}.json').read_text(encoding='utf-8'))
        call.update({'tool_original':TOOL_DIR+tool_name,'sha256':sha(path),'source_size':list(art.size)})
        assert sha(path)==sha(__import__('pathlib').Path(TOOL_DIR+tool_name))
        calls.append(call)
    panel(candidates[:2],PROOFS/'candidates-01-02.png')
    panel(candidates[2:],PROOFS/'candidates-03-04.png')
    t=CONFIG['transforms']['Jacket']
    write(LAY/'placement.json',{'canvas':CONFIG['canvas'],'source_size':list(front.size),
        'source':'assets/ciel/generated/v16c/jacket-front.png','uniform_scale':t['uniform_scale'],
        'translate':t['translate'],'resized_size':[round(d*t['uniform_scale']) for d in front.size],
        'resampling':'Pillow LANCZOS','rotation':0,
        'inherited_from':'assets/ciel/layers/v16/placement.json: transforms.Jacket',
        'coordinates':'Top-left of entire generated frame. No source crop, mask or local deformation.',
        'canvas_note':'Inherited placement extends outside left/right/bottom edges; original PNG retains complete cuffs.'})
    write(GEN/'generation-summary.json',{'generation_count':4,'limit':4,'selected':SELECTED.name,'calls':calls})
    # Read-only rectangular samples; these do not mask or modify any artwork.
    boxes={'upper_chest_center':(980,1680,1240,1990),
           'broad_chest':(780,2040,1460,2180),
           'lower_top':(860,2220,1360,2420),
           'abdomen_center':(880,2480,1340,2700)}
    arr=np.asarray(placed)
    body_array=np.asarray(body)
    dressed_array=np.asarray(dressed)
    samples={}
    for name,(x0,y0,x1,y1) in boxes.items():
        alpha=arr[y0:y1,x0:x1,3]
        samples[name]={'xyxy':[x0,y0,x1,y1],'jacket_alpha_max':int(alpha.max()),
            'jacket_nonzero_pixels':int(np.count_nonzero(alpha)),
            'body_pixels_unchanged':bool(np.array_equal(body_array[y0:y1,x0:x1],dressed_array[y0:y1,x0:x1]))}
    output=Image.open(LAY/'Jacket_Front.png')
    assert output.size==(2172,2896) and output.mode=='RGBA'
    assert np.array_equal(np.asarray(output),np.asarray(placed))
    assert sha(SELECTED)==sha(GEN/'jacket-front.png')
    assert all(sha(ROOT/p)==h for p,h in expected.items())
    write(LAY/'validation.json',{'generation_count':4,'selected':SELECTED.name,
        'source_size':list(front.size),'output_size':list(output.size),'mode':output.mode,
        'alpha_extrema':list(output.getchannel('A').getextrema()),
        'candidate_copies_match_tool_originals':True,'selected_copy_byte_identical':True,
        'placement_pixel_verified':True,'reference_hashes_unchanged':expected,
        'source_sha256':sha(GEN/'jacket-front.png'),'layer_sha256':sha(LAY/'Jacket_Front.png'),
        'read_only_body_samples':samples,
        'sample_limitation':'Rectangular interior samples do not prove the full top outline is unobstructed.',
        'strict_zero_top_overlap_achieved':False,
        'remaining_issues':['Small fur tips overlap the image-left outer edge of the top.',
            'Minor generation specks and edge residue remain.',
            'Generated fur and sleeve contours are not pixel-identical to v16.'],
        'prohibited_art_operations_used':[]})
    print(json.dumps({'selected':SELECTED.name,'read_only_samples':samples,'strict_zero_top_overlap_achieved':False},indent=2))

if __name__=='__main__':
    main()
