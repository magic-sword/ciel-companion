"""GIMP inspection board: left column lash, right fold; top L, bottom R."""
import os,json
from pathlib import Path
from gi.repository import Gimp,Gio,Gegl
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
OUT=ROOT/os.environ.get('CIEL_LID_STUDY','assets/private/ciel/live2d/gimp/face-remake-v2')
CW,CH=90,70
FMT="R'G'B'A u8"
rect=Gegl.Rectangle.new(0,0,CW,CH)
doc=Gimp.Image.new(CW*2,CH*2,Gimp.ImageBaseType.RGB)
reclaimed=[(219,53),(225,59),(230,63)]
ownership_checks=[]
checker=bytes(v for y in range(CH) for x in range(CW)
              for v in ([180,180,180,255] if (x//5+y//5)%2 else [225,225,225,255]))
def add(name,rgba,col,row):
    item=Gimp.Layer.new(doc,name,CW,CH,Gimp.ImageType.RGBA_IMAGE,100,Gimp.LayerMode.NORMAL)
    doc.insert_layer(item,None,0);item.get_buffer().set(rect,FMT,rgba)
    item.set_offsets(col*CW,row*CH)
for row,(side,x) in enumerate([('L',160),('R',30)]):
    for col,part in enumerate(['UpperLash','UpperFold']):
        name=f'{side}_{part}'
        image=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(OUT/f'part-{name}.png')))
        rgba=bytes(image.get_layers()[0].get_buffer().get(Gegl.Rectangle.new(x,40,CW,CH),1.0,FMT,Gegl.AbyssPolicy.NONE))
        image.delete()
        if side=='L':
            for px,py in reclaimed:
                alpha=rgba[4*((py-40)*CW+px-x)+3]
                expected=255 if part=='UpperLash' else 0
                assert alpha==expected, f'{name}: incorrect ownership at {px},{py}'
                ownership_checks.append(dict(part=name,pixel=[px,py],alpha=alpha))
        add(name+'_checker',checker,col,row);add(name,rgba,col,row)
doc.scale(CW*12,CH*12)
proc=Gimp.get_pdb().lookup_procedure('file-png-export');cfg=proc.create_config()
cfg.set_property('run-mode',Gimp.RunMode.NONINTERACTIVE);cfg.set_property('image',doc)
cfg.set_property('file',Gio.File.new_for_path(str(OUT/'lid-material-inspection.png')))
assert proc.run(cfg).index(0)==Gimp.PDBStatusType.SUCCESS
doc.delete()
(OUT/'lid-material-inspection.json').write_text(json.dumps(dict(
    status='specific_misclassified_pixels_fixed_not_global_material_approval',
    layout=dict(rows=['L (screen right)','R (screen left)'],columns=['UpperLash','UpperFold']),
    ownership_checks=ownership_checks,
    limits=['Three known black lash pixels checked, not every source edge',
            'Pale antialiased fringes still require production-resolution material work']),indent=2),encoding='utf-8')
print('LID_MATERIAL_INSPECTION_READY',flush=True)
