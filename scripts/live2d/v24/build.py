"""Key extraction, uniform scale/translation, masks for cutting, and proof composition.
No artwork painting, inpainting, color grading, mesh warping, or generated gradients.
"""
from pathlib import Path
import json,hashlib
import numpy as np
from scipy import ndimage,optimize
from PIL import Image,ImageDraw,ImageFont,ImageChops
from prepare import ROOT,OUT,CURRENT,NAMES,flat,hashes

SIZE=(2172,2896)
MANIFEST=json.loads((CURRENT/'layers.json').read_text(encoding='utf-8'))
FONT=ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc',16)
SELECT={'Ear_L_Outer':2,'Ear_R_Base':2}

def original_context_before(n):
    context=Image.new('RGBA',SIZE)
    for e in MANIFEST['layers']:
        if e['name']==n:break
        if e.get('visible',True):context.alpha_composite(Image.open(ROOT/e['path']).convert('RGBA'))
    return context

def retain_visible_ear(n,old,generated):
    # This is cut-and-composite of existing artwork, not painted extension.
    # Only use generated continuation where later existing layers fully cover it.
    cover=Image.new('L',SIZE)
    found=False
    for e in MANIFEST['layers']:
        if e['name']==n:found=True;continue
        if found and e.get('visible',True):
            alpha=Image.open(ROOT/e['path']).convert('RGBA').getchannel('A')
            cover=ImageChops.screen(cover,alpha)
    # Fill enclosed alpha pinholes in the covering artwork; otherwise its texture
    # noise would punch holes into the newly extracted root.
    mask=Image.fromarray(ndimage.binary_fill_holes(np.asarray(cover)>=250).astype('uint8')*255)
    piece=generated.copy();piece.putalpha(ImageChops.multiply(piece.getchannel('A'),mask))
    side=n.split('_')[1]
    if n.endswith('_Inner'):
        # Keep the complete generated lower tufts: cropping them to the hair's
        # outline would introduce new notches. Upper original artwork stays intact.
        cut=old.getbbox()[3]-80
        piece=Image.new('RGBA',SIZE)
        piece.paste(generated.crop((0,cut,SIZE[0],SIZE[1])),(0,cut))
        context=original_context_before(n)
        exposed=ImageChops.multiply(piece.getchannel('A'),ImageChops.invert(mask))
        opaque=Image.fromarray((np.asarray(context.getchannel('A'))==255).astype('uint8')*255)
        context.putalpha(ImageChops.multiply(opaque,exposed))
        piece.alpha_composite(context)
        piece.putalpha(ImageChops.multiply(piece.getchannel('A'),ImageChops.lighter(mask,opaque)))
    if n.endswith('_Outer'):
        # Existing matching root fur closes the old straight cut without inventing pixels.
        base=Image.open(CURRENT/'layers'/f'Ear_{side}_Base.png').convert('RGBA')
        base.putalpha(Image.fromarray((np.asarray(base.getchannel('A'))==255).astype('uint8')*255))
        piece.alpha_composite(base)
    if n.endswith('_Base'):
        # The generated upper root overlaps the existing ear: cut its visible
        # texture from that same original ear, so no extra fur marks appear.
        ear=original_context_before(n)
        upper=Image.new('L',SIZE)
        cut=old.getbbox()[1]
        piece.paste(generated.crop((0,0,SIZE[0],cut)),(0,0))
        upper.paste(generated.getchannel('A').crop((0,0,SIZE[0],cut)),(0,0))
        opaque=Image.fromarray((np.asarray(ear.getchannel('A'))==255).astype('uint8')*255)
        ear.putalpha(ImageChops.multiply(opaque,upper))
        piece.alpha_composite(ear)
        piece.putalpha(ImageChops.multiply(piece.getchannel('A'),ImageChops.lighter(mask,opaque)))
    piece.alpha_composite(old)
    return piece

def retain_iris_core(n,old,generated):
    # Rectangular separation at the dark upper band; preserve all original lower art.
    cut=old.getbbox()[1]+18
    out=Image.new('RGBA',SIZE)
    out.paste(generated.crop((0,0,SIZE[0],cut)),(0,0))
    out.paste(old.crop((0,cut,SIZE[0],SIZE[1])),(0,cut))
    return out,cut

def extract(path):
    rgb=np.asarray(Image.open(path).convert('RGB'),dtype=np.float32)/255
    excess=rgb[:,:,1]-np.maximum(rgb[:,:,0],rgb[:,:,2])
    a=np.clip(1-excess,0,1)
    green=(rgb[:,:,1]>.65)&(rgb[:,:,0]<.25)&(rgb[:,:,2]<.25)
    a[green]=0
    solid=ndimage.binary_fill_holes(~green)
    a[ndimage.binary_erosion(solid,iterations=2)]=1
    a[a<.02]=0
    fg=(rgb-(1-a[:,:,None])*np.array([0,1,0]))/np.maximum(a[:,:,None],1e-6)
    out=np.dstack([np.clip(fg,0,1),a]);out[a==0]=0
    return Image.fromarray(np.round(out*255).astype('uint8'))

def fit(n,original,keyed,origin):
    """Fit 3 DOF only; registration looks at unchanged portions."""
    w,h=original.size
    native_scale=w/keyed.width
    gen=keyed.resize((w,round(keyed.height*native_scale)),Image.Resampling.LANCZOS)
    ref=np.asarray(flat(original,(0,255,0)),dtype=float)/255
    arr=np.asarray(flat(gen,(0,255,0)),dtype=float)/255
    yy,xx=np.mgrid[:h:2,:w:2]; mask=np.ones(xx.shape,bool)
    if 'Outer' in n:mask &= (yy< h-250)&(yy>20)
    if 'Inner' in n:mask &= (yy< (h-230)*.65+40)&(yy>20)
    if 'Base' in n:mask &= (yy>200)&(yy<h-180)
    if 'Iris' in n:mask &= (yy>65)&(yy<h-205)
    xx=xx[mask];yy=yy[mask]; target=ref[yy,xx]
    def loss(v):
        s,dx,dy=v
        xy=np.array([(yy-dy)/s,(xx-dx)/s])
        pred=np.stack([ndimage.map_coordinates(arr[:,:,c],xy,order=1,mode='constant',cval=[0,1,0][c]) for c in range(3)],axis=-1)
        return np.mean(np.minimum((pred-target)**2,.25))
    result=optimize.differential_evolution(loss,[(.92,1.08),(-18,18),(-18,18)],popsize=8,maxiter=40,tol=.0001,seed=24,polish=True)
    s,dx,dy=result.x
    scale=native_scale*s
    resized=keyed.resize((round(keyed.width*scale),round(keyed.height*scale)),Image.Resampling.LANCZOS)
    layer=Image.new('RGBA',SIZE);layer.paste(resized,(round(origin[0]+dx),round(origin[1]+dy)))
    return layer,{'uniform_scale':scale,'translate':[round(origin[0]+dx),round(origin[1]+dy)],'fit_loss':float(result.fun)}

def sclera(n,old,keyed):
    # Generated smooth paint is cut with the original alpha silhouette.
    # Overscan ensures the original silhouette is wholly within drawn foreground.
    b=old.getbbox();gb=keyed.getbbox(); gw=gb[2]-gb[0];gh=gb[3]-gb[1]
    scale=max((b[2]-b[0])/gw,(b[3]-b[1])/gh)*1.09
    crop=keyed.crop(gb)
    for attempt in range(15):
        piece=crop.resize((round(gw*scale),round(gh*scale)),Image.Resampling.LANCZOS)
        xy=(round((b[0]+b[2]-piece.width)/2),round((b[1]+b[3]-piece.height)/2))
        im=Image.new('RGBA',SIZE);im.paste(piece,xy)
        a=np.asarray(im.getchannel('A'));oa=np.asarray(old.getchannel('A'))
        if np.all(a[oa>0]>=250):break
        scale*=1.025
    else:raise RuntimeError('Sclera generated paint does not cover original silhouette')
    # Only removing pixels: retain exact existing alpha for outside contour.
    im.putalpha(old.getchannel('A'))
    z=np.asarray(im).copy();z[z[:,:,3]==0]=0;im=Image.fromarray(z)
    return im,{'uniform_scale':scale,'source_crop':gb,'translate':xy,'cut_mask':'unchanged original sclera alpha','alpha_identical':bool(np.array_equal(np.asarray(im)[:,:,3],oa))}

def assemble(layers,clip=False,gaze=(0,0)):
    result=Image.new('RGBA',SIZE)
    for e in MANIFEST['layers']:
        if not e.get('visible',True):continue
        n=e['name'];im=layers.get(n)
        if im is None:im=Image.open(ROOT/e['path']).convert('RGBA')
        if clip and (n.endswith('_Iris') or n.endswith('_Highlight')):
            shifted=Image.new('RGBA',SIZE);shifted.paste(im,gaze);im=shifted
            sn='_'.join(n.split('_')[:2])+'_Sclera';sc=layers.get(sn)
            if sc is None:sc=Image.open(CURRENT/'layers'/f'{sn}.png').convert('RGBA')
            im.putalpha(ImageChops.multiply(im.getchannel('A'),sc.getchannel('A')))
        result.alpha_composite(im)
    return result

def board(pics,path,thumb=None):
    if thumb:
        pics=[(label,im.resize(thumb,Image.Resampling.LANCZOS)) for label,im in pics]
    w=max(im.width for _,im in pics);h=max(im.height for _,im in pics)
    out=Image.new('RGB',(len(pics)*w,h+35),(40,43,57));draw=ImageDraw.Draw(out)
    for i,(label,im) in enumerate(pics):out.paste(flat(im),(i*w,35));draw.text((i*w+10,6),label,font=FONT,fill='white')
    out.save(path)

def main():
    layers={};meta={}
    prior=json.loads((OUT/'placement.json').read_text(encoding='utf-8')) if (OUT/'placement.json').exists() else {}
    for n in NAMES:
        old=Image.open(CURRENT/'layers'/f'{n}.png').convert('RGBA'); b=old.getbbox()
        source=OUT/'edits'/f'{n}-{SELECT.get(n,1):02}.png'; keyed=extract(source)
        keyed.save(OUT/'qa'/f'{source.stem}-extracted.png')
        if 'Sclera' in n:new,m=sclera(n,old,keyed)
        else:
            origin=(b[0]-30,b[1]-(190 if 'Base' in n else 40))
            original=old.crop((*origin,b[2]+30,b[3]+190))
            if n in prior and prior[n]['source']==str(source.relative_to(OUT)):
                m={k:prior[n][k] for k in ['uniform_scale','translate','fit_loss']}
                scale=m['uniform_scale'];piece=keyed.resize((round(keyed.width*scale),round(keyed.height*scale)),Image.Resampling.LANCZOS)
                m['translate']=m['translate'][:2]
                new=Image.new('RGBA',SIZE);new.paste(piece,tuple(m['translate']))
            else:new,m=fit(n,original,keyed,origin)
        new.save(OUT/'qa'/f'{n}-generated-placed.png')
        if n.startswith('Ear_'):
            new=retain_visible_ear(n,old,new)
            m['assembly']='cut/composite original ear artwork and generated hidden continuation; Outer also includes existing same-side Base; Base upper overlap is cut from existing full ear'
        if 'Iris' in n:
            new,cut=retain_iris_core(n,old,new)
            m['original_core_from_y']=cut
        layers[n]=new;new.save(OUT/'layers'/f'{n}.png')
        m.update(source=str(source.relative_to(OUT)),original_bbox=b,new_bbox=new.getbbox(),size=new.size,mode=new.mode)
        meta[n]=m
        bb=new.getbbox();box=(min(b[0],bb[0])-20,min(b[1],bb[1])-20,max(b[2],bb[2])+20,max(b[3],bb[3])+20)
        a=old.crop(box);c=new.crop(box);overlay=Image.blend(flat(a),flat(c),.5).convert('RGBA')
        board([('current',a),('v24',c),('50% overlay',overlay)],OUT/'proofs'/f'{n}-compare.png')
        print(n,m,flush=True)
    (OUT/'placement.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    before=assemble({});after=assemble(layers)
    ear_only=assemble({n:im for n,im in layers.items() if n.startswith('Ear_')})
    ear_delta=np.abs(np.asarray(before,dtype=np.int16)-np.asarray(ear_only,dtype=np.int16))
    before.save(OUT/'proofs/assembled-current.png');after.save(OUT/'proofs/assembled-v24.png')
    board([('current',before),('v24',after)],OUT/'front-comparison.png',(651,869))
    head=(430,0,1780,1410)
    board([('current',before.crop(head)),('v24',after.crop(head)),('50% overlay',Image.blend(before.crop(head),after.crop(head),.5))],OUT/'proofs/head-comparison.png',(675,705))
    eyes=(740,915,1460,1160)
    pics=[]
    for xy in [(0,0),(28,0),(-28,0),(0,30)]:
        a=assemble({},True,xy).crop(eyes);b=assemble(layers,True,xy).crop(eyes)
        board([('current '+str(xy),a),('v24 '+str(xy),b)],OUT/'proofs'/f'gaze-{xy[0]}-{xy[1]}.png')
    initial=json.loads((OUT/'current-before.json').read_text(encoding='utf-8'))
    verify={'current_unchanged':initial==hashes(),'layer_count':len(layers),'canvas_and_rgba_ok':all(im.size==SIZE and im.mode=='RGBA' for im in layers.values()),'sclera_alpha_identical':all(meta[n]['alpha_identical'] for n in NAMES if 'Sclera' in n),'ears_front_max_rgba_difference':int(ear_delta.max()),'ears_front_changed_pixels':int(np.any(ear_delta,axis=2).sum()),'registration':'uniform scale + translation only','runtime_live2d_test':False}
    (OUT/'verification.json').write_text(json.dumps(verify,indent=2),encoding='utf-8');print(verify)
if __name__=='__main__':main()
