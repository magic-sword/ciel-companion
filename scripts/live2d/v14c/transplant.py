"""Transplant only v14's tiny fang; leave the v14b mouth pixels/alpha untouched elsewhere."""
import numpy as np
from PIL import Image, ImageDraw
from common import ROOT,GEN,LAY,PROOF,write,panel,flatten

DONOR_BOX=(1131,1231,1144,1238)
RIGHT_ORIGIN=(1140,1223)
MIRROR_SUM_X=2211  # pixel centers mirrored about x=1105.5 (v14b mouth center)

def main():
    donor=Image.open(ROOT/'assets/ciel/layers/v14/Mouth_Large.png').convert('RGBA')
    base=Image.open(ROOT/'assets/ciel/layers/v14b/Mouth_Large.png').convert('RGBA')
    patch=donor.crop(DONOR_BOX)
    rgb=np.asarray(patch)[:,:,:3].astype(float)
    # White-tooth coverage estimated from the donor's bright, low-chroma pixels.
    # The crop is below the skin/lip boundary, so no surrounding skin is selected.
    opacity=np.clip((rgb[:,:,1]-180)/55,0,1)
    opacity[rgb[:,:,0]-rgb[:,:,1]>45]=0
    a=np.rint(opacity*255).astype(np.uint8)
    patch.putalpha(Image.fromarray(a))
    patch.save(GEN/'extraction/donor-fang.png')
    donor.crop((1125,1224,1150,1243)).save(GEN/'inputs/donor-context.png')
    layer=Image.new('RGBA',base.size)
    layer.paste(patch,RIGHT_ORIGIN)
    left_origin=(MIRROR_SUM_X-(RIGHT_ORIGIN[0]+patch.width-1),RIGHT_ORIGIN[1])
    layer.paste(patch.transpose(Image.Transpose.FLIP_LEFT_RIGHT),left_origin)
    layer.save(GEN/'extraction/paired-fangs.png')
    # Overlay affects only enamel coverage; preserve the entire inherited alpha.
    output=Image.alpha_composite(base,layer)
    output.putalpha(base.getchannel('A'))
    output.save(LAY/'Mouth_Large.png')
    support=np.asarray(layer)[:,:,3]>0
    Image.fromarray(support.astype(np.uint8)*255).save(GEN/'extraction/tooth-support-mask.png')
    changed=np.any(np.asarray(base)!=np.asarray(output),axis=2)
    Image.fromarray(changed.astype(np.uint8)*255).save(GEN/'extraction/actual-change-mask.png')
    y,x=np.where(support)
    metrics={'method':'Python transplant of existing v14 fang; image generation not used',
      'generation_count':0,'generation_limit':3,'donor_layer':'assets/ciel/layers/v14/Mouth_Large.png',
      'donor_crop_xyxy':DONOR_BOX,'right_origin_canvas':RIGHT_ORIGIN,'left_origin_canvas':left_origin,
      'mirror_axis_canvas_x':MIRROR_SUM_X/2,'donor_patch_size':list(patch.size),
      'coverage_rule':'clip((G-180)/55,0,1), zero where R-G > 45; native donor pixels unchanged',
      'tooth_support_pixels':int(support.sum()),'changed_pixels':int(changed.sum()),
      'tooth_support_bbox':[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)],
      'alpha_identical_to_v14b':bool(np.array_equal(np.asarray(base)[:,:,3],np.asarray(output)[:,:,3])),
      'outside_teeth_identical':bool(np.array_equal(np.asarray(base)[~support],np.asarray(output)[~support]))}
    write(GEN/'extraction/transplant.json',metrics)
    panel([('v14 donor',flatten(donor.crop((1020,1205,1190,1325)))),
           ('v14b unchanged mouth',flatten(base.crop((1020,1205,1190,1325)))),
           ('v14c tiny paired fangs',flatten(output.crop((1020,1205,1190,1325))))],
          PROOF/'transplant-mouth-preview.png',cols=3,side=510,height=360)
    print(metrics)

if __name__=='__main__':main()
