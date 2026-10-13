"""Extract generated artwork from solid keys and place it without painting/warping.

Only chroma/luminance matting, rectangular separation, uniform scaling and
translation are used on deliverable artwork. Drawing is confined to proof labels.
"""
from pathlib import Path
import json, hashlib
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont
from prepare import ROOT, OUT, CROP, flat, hashes

SIZE=(2172,2896)
FONT=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',18)
CURRENT=ROOT/'assets/ciel/current/layers'
MANIFEST=json.loads((ROOT/'assets/ciel/current/layers.json').read_text(encoding='utf-8'))

def key_extract(path, kind):
    rgb=np.asarray(Image.open(path).convert('RGB'),dtype=np.float32)/255
    if kind=='skin-black':
        # Opaque eye ink is enclosed by bright skin. Fill only holes in the
        # color-derived mask, so black eyelashes do not become transparent.
        bright=rgb.min(axis=2)>.93
        core=ndimage.binary_erosion(ndimage.binary_fill_holes(rgb.max(axis=2)>.70),iterations=2)
        _,indices=ndimage.distance_transform_edt(~bright,return_indices=True)
        foreground=rgb[indices[0],indices[1]]
        alpha=np.clip(np.sum(rgb*foreground,axis=2)/np.maximum(np.sum(foreground**2,axis=2),1e-6),0,1)
        alpha[core]=1
        alpha[alpha<3/255]=0
        fg=rgb/np.maximum(alpha[:,:,None],1e-6)
        key=[0,0,0]
    elif kind=='black':
        # Black-key unpremultiplication: alpha = max RGB. The drawn pigment's
        # chromatic ratios survive; faint pink retains faint alpha.
        alpha=rgb.max(axis=2)
        alpha[alpha<3/255]=0
        fg=rgb/np.maximum(alpha[:,:,None],1e-6)
        key=[0,0,0]
    else:
        pix=(rgb*255).astype(np.uint8).reshape(-1,3)
        colors,counts=np.unique(pix,axis=0,return_counts=True)
        key=colors[counts.argmax()].astype(float)/255
        excess=rgb[:,:,1]-np.maximum(rgb[:,:,0],rgb[:,:,2])
        alpha=np.clip(1-excess/(key[1]-max(key[0],key[2])),0,1)
        background=(rgb[:,:,1]>.55)&(rgb[:,:,0]<.14)&(rgb[:,:,2]<.14)
        alpha[background]=0
        alpha[alpha<.015]=0
        fg=(rgb-(1-alpha[:,:,None])*key)/np.maximum(alpha[:,:,None],1e-6)
        key=(key*255).tolist()
    rgba=np.dstack((np.clip(fg,0,1),alpha))
    rgba[alpha==0]=0
    return Image.fromarray(np.round(rgba*255).astype(np.uint8)),key

def place(im,half=None,dy=0,dx=0,happy=False,sweat=False):
    # Splitting through empty space only; no shaped or feathered masks.
    if half:
        box=(0,0,im.width//2,im.height) if half=='R' else (im.width//2,0,im.width,im.height)
        part=im.crop(box); clean=Image.new('RGBA',im.size); clean.paste(part,box[:2]); im=clean
    target=1176 if happy else (788 if sweat else 1050)
    offset=(513,573) if happy and half=='R' else ((430,564) if happy else ((767,708) if sweat else (550+dx,650+dy)))
    im=im.resize((target,target),Image.Resampling.LANCZOS)
    layer=Image.new('RGBA',SIZE); layer.paste(im,offset)
    return layer

def build_layers():
    result={}; metadata={}
    specs=[('blush','black',['Cheek_Blush']),('happy','skin-black',['Eye_R_Happy','Eye_L_Happy']),
           ('tears','green',['Tear_R','Tear_L']),('sweat','green',['Sweat']),
           ('sparkle','black',['Eye_R_Sparkle','Eye_L_Sparkle'])]
    for kind,key,names in specs:
        source=OUT/'keyed'/f'{kind}-key-{4 if kind=="happy" else 1:02d}.png'
        rgba,keycolor=key_extract(source,key)
        rgba.save(OUT/'qa'/f'{kind}-extracted-native.png')
        for name in names:
            side=('R' if name in ['Eye_R_Happy','Tear_R','Eye_R_Sparkle'] else 'L') if len(names)==2 else None
            dy=0
            layer=place(rgba,side,dy=dy,happy=kind=='happy',sweat=kind=='sweat')
            layer.save(OUT/'layers'/f'{name}.png'); result[name]=layer
            alpha=np.asarray(layer)[:,:,3]
            metadata[name]={'source':str(source.relative_to(OUT)).replace('\\','/'),'key':keycolor,
                'uniform_scale':(1176 if kind=='happy' else (788 if kind=='sweat' else 1050))/rgba.width,
                'translate':([513,573] if side=='R' else [430,564]) if kind=='happy' else ([767,708] if kind=='sweat' else [550,650+dy]),
                'side':side,'bbox':layer.getbbox(),'size':list(layer.size),'mode':layer.mode,
                'nonzero_alpha_pixels':int((alpha>0).sum()),'partial_alpha_pixels':int(((alpha>0)&(alpha<255)).sum()),
                'sha256':hashlib.sha256((OUT/'layers'/f'{name}.png').read_bytes()).hexdigest()}
    (OUT/'placement.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    return result

def assemble(new,names=(),large=False,hide_happy=True,with_new=True):
    selected=set(names); closed={s for s in ['R','L'] if f'Eye_{s}_Happy' in selected}
    im=Image.new('RGBA',SIZE)
    for entry in MANIFEST['layers']:
        n=entry['name']; visible=entry.get('visible',True)
        if large and n.startswith('Mouth_'): visible=n=='Mouth_Large'
        if hide_happy and any(n.startswith(f'Eye_{s}_') for s in closed): visible=False
        if visible: im.alpha_composite(Image.open(ROOT/entry['path']).convert('RGBA'))
        additions=[]
        if n=='Face_Shadow_Hair': additions=['Cheek_Blush']
        for s in ['R','L']:
            if n==f'Eye_{s}_Closed': additions=[f'Eye_{s}_Happy',f'Tear_{s}',f'Eye_{s}_Sparkle']
        if with_new:
            for add in additions:
                if add in selected: im.alpha_composite(new[add])
    if with_new and 'Sweat' in selected: im.alpha_composite(new['Sweat'])
    return im

def board(panels,path,size=525,bg=(224,227,234)):
    im=Image.new('RGB',(len(panels)*size,size+40),bg); d=ImageDraw.Draw(im)
    for i,(label,pic) in enumerate(panels):
        d.text((i*size+12,8),label,font=FONT,fill=(25,32,48))
        im.paste(flat(pic,bg).resize((size,size),Image.Resampling.LANCZOS),(i*size,40))
    im.save(path)

def proofs(new):
    for d in ['proofs/layers','proofs/expressions','proofs/details','assembled','qa/occlusion']:(OUT/d).mkdir(parents=True,exist_ok=True)
    base=assemble(new); source=Image.open(OUT/'inputs/assembled-current.png').convert('RGBA')
    exact=bool(np.array_equal(np.asarray(base),np.asarray(source)))
    base.save(OUT/'assembled/base.png')
    darksheet=Image.new('RGB',(1600,880),(34,40,56)); dd=ImageDraw.Draw(darksheet)
    scope={}
    for index,(name,layer) in enumerate(new.items()):
        after=assemble(new,[name]); after.save(OUT/'assembled'/f'{name}.png')
        board([('重ねる前',base.crop(CROP)),(name,after.crop(CROP))],OUT/'proofs/layers'/f'{name}.png')
        board([('素材 / 暗色背景',flat(layer.crop(CROP),(34,40,56))),('素材 / 白背景',flat(layer.crop(CROP),(255,255,255)))],OUT/'qa'/f'{name}-alpha.png')
        bbox=layer.getbbox(); span=max(bbox[2]-bbox[0],bbox[3]-bbox[1])+60
        cx=(bbox[0]+bbox[2])//2; cy=(bbox[1]+bbox[3])//2
        detail=(cx-span//2,cy-span//2,cx-span//2+span,cy-span//2+span)
        board([('重ねる前 / 拡大',base.crop(detail)),(name,after.crop(detail)),('素材単体',flat(layer.crop(detail),(34,40,56)))],OUT/'proofs/details'/f'{name}.png',size=420)
        px=(index%4)*400; py=(index//4)*440
        darksheet.paste(flat(layer.crop(detail),(34,40,56)).resize((400,400),Image.Resampling.LANCZOS),(px,py+40))
        dd.text((px+10,py+9),name,font=FONT,fill='white')
        delta=(np.asarray(after)!=np.asarray(base)).any(axis=2)
        delta[800:1350,700:1500]=False
        scope[name]={'changed_pixels_outside_face_work_area':int(delta.sum())}
    darksheet.save(OUT/'layers-dark-sheet.png')
    expressions={
        'happy':(['Cheek_Blush','Eye_R_Happy','Eye_L_Happy'],True,'嬉しい'),
        'embarrassed':(['Cheek_Blush'],False,'照れ'),
        'teary':(['Tear_R','Tear_L'],False,'半泣き'),
        'troubled':(['Sweat'],False,'困り'),
        'excited':(['Eye_R_Sparkle','Eye_L_Sparkle'],True,'わくわく')}
    sheet=Image.new('RGB',(1575,565*5),(224,227,234))
    front=Image.new('RGB',(434*6,620),(224,227,234)); fd=ImageDraw.Draw(front)
    front.paste(flat(base).resize((434,579),Image.Resampling.LANCZOS),(0,40)); fd.text((12,8),'元の組み上げ',font=FONT,fill='black')
    # References use a different head crop. Crop their face region for comparable
    # display only; this transform never enters the deliverable layers.
    for i,(name,(names,large,jp)) in enumerate(expressions.items()):
        after=assemble(new,names,large); after.save(OUT/'assembled'/f'{name}.png')
        front.paste(flat(after).resize((434,579),Image.Resampling.LANCZOS),((i+1)*434,40))
        fd.text(((i+1)*434+12,8),jp,font=FONT,fill='black')
        ref=Image.open(ROOT/'assets/ciel/generated/v22/expressions'/f'{name}.png').convert('RGBA')
        rx=ref.width/1664
        ref=ref.crop(tuple(round(v*rx) for v in (350,690,1320,1660)))
        dst=OUT/'proofs/expressions'/f'{name}.png'
        board([('元の組み上げ',base.crop(CROP)),(f'v23 {jp}',after.crop(CROP)),(f'v22 承認見本 / {jp}',ref)],dst)
        sheet.paste(Image.open(dst),(0,i*565))
    sheet.save(OUT/'expressions-comparison.png')
    front.save(OUT/'front-comparison.png')
    # The new happy skin should hide the existing eyes even if left enabled.
    off=assemble(new,['Eye_R_Happy','Eye_L_Happy'])
    on=assemble(new,['Eye_R_Happy','Eye_L_Happy'],hide_happy=False)
    diff=np.abs(np.asarray(on).astype(int)-np.asarray(off).astype(int))
    board([('開眼層 OFF + Happy',off.crop(CROP)),('開眼層 ON + Happy',on.crop(CROP))],OUT/'qa/occlusion/happy-open-eye-coverage.png')
    verification={'assembled_matches_supplied_input':exact,
                  'current_files_unchanged':json.loads((OUT/'current-before.json').read_text())==hashes(),
                  'layer_count':len(new),'all_rgba_2172_2896':all(v.mode=='RGBA' and v.size==SIZE for v in new.values()),
                  'all_layers_nonempty':all(v.getbbox() is not None for v in new.values()),
                  'scope_checks':scope,
                  'happy_open_eye_on_off_changed_pixels':int((diff.max(axis=2)>0).sum()),
                  'happy_open_eye_on_off_pixels_over_8':int((diff.max(axis=2)>8).sum()),
                  'happy_open_eye_on_off_max_difference':int(diff.max())}
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
    print(json.dumps(verification,indent=2))

def write_integration(new):
    inserts={'Face_Shadow_Hair':['Cheek_Blush'],
             'Eye_R_Closed':['Eye_R_Happy','Tear_R','Eye_R_Sparkle'],
             'Eye_L_Closed':['Eye_L_Happy','Tear_L','Eye_L_Sparkle'],
             'Brow_L':['Sweat']}
    layers=[]
    for entry in MANIFEST['layers']:
        layers.append(entry.copy())
        for name in inserts.get(entry['name'],[]):
            layers.append({'name':name,'path':f'assets/ciel/generated/v23/layers/{name}.png','visible':False})
    result={'canvas':list(SIZE),'out':'assets/ciel/generated/v23/ciel-expression-layers','layers':layers}
    (OUT/'layers.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    eye_off=[e['name'] for e in MANIFEST['layers'] if e['name'].startswith('Eye_')]
    mouth_off=[e['name'] for e in MANIFEST['layers'] if e['name'].startswith('Mouth_') and e['name']!='Mouth_Large']
    presets={'happy':{'show':['Eye_R_Happy','Eye_L_Happy','Cheek_Blush','Mouth_Large'],'hide':eye_off+mouth_off},
             'embarrassed':{'show':['Cheek_Blush'],'hide':[]},
             'teary':{'show':['Tear_R','Tear_L'],'hide':[]},
             'troubled':{'show':['Sweat'],'hide':[]},
             'excited':{'show':['Eye_R_Sparkle','Eye_L_Sparkle','Mouth_Large'],'hide':mouth_off}}
    (OUT/'expression-presets.json').write_text(json.dumps({'base':'current default visibility; reset all v23 layers to 0 before each preset','L':'viewer right','R':'viewer left','presets':presets},indent=2),encoding='utf-8')

if __name__=='__main__':
    layers=build_layers(); write_integration(layers); proofs(layers)
