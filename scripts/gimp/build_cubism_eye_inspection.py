"""Build an inspection sheet from verified Cubism screenshots, without retouching."""
import os,json,hashlib
from pathlib import Path
from gi.repository import Gimp,Gio,Gegl
root=Path(os.environ['CIEL_PROJECT_ROOT'])
out=root/'docs/assets/ciel/production'
model=root/'assets/private/ciel/live2d/gimp/face-remake-v2/semantic-parts-import-check.cmo3'
expected='47feeb4826741444eb352da452d2cdcf49aa359cf28117b8b7ac462a6dadc753'
assert hashlib.sha256(model.read_bytes()).hexdigest()==expected
cw,ch=300,220
doc=Gimp.Image.new(cw*3,ch*2,Gimp.ImageBaseType.RGB)
files={
 'minus':['latest-minus-top.png','latest-minus-half.png','latest-minus-closed.png'],
 'plus':['latest-plus-open-corrected.png','latest-plus-half-corrected.png','latest-plus-controls-corrected.png']}
closed_crops=[]
evidence=[]
for row,direction in enumerate(['minus','plus']):
    for col,state in enumerate(['open','half','closed']):
        p=root/'.local'/files[direction][col]
        image=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(p)))
        assert image.get_width()==1800 and image.get_height()==1000
        rgba=bytes(image.get_layers()[0].get_buffer().get(Gegl.Rectangle.new(1340,350,cw,ch),1.0,"R'G'B'A u8",Gegl.AbyssPolicy.NONE))
        image.delete()
        if state=='closed':closed_crops.append(rgba)
        layer=Gimp.Layer.new(doc,f'{direction}_{state}',cw,ch,Gimp.ImageType.RGBA_IMAGE,100,Gimp.LayerMode.NORMAL)
        doc.insert_layer(layer,None,0)
        layer.get_buffer().set(Gegl.Rectangle.new(0,0,cw,ch),"R'G'B'A u8",rgba)
        layer.set_offsets(col*cw,row*ch)
        evidence.append(dict(file=str(p.relative_to(root)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),gaze=-1 if row==0 else 1,eye_open=[1,.5,0][col]))
assert closed_crops[0]==closed_crops[1], 'Closed eye differs across gaze extremes'
proc=Gimp.get_pdb().lookup_procedure('file-png-export');cfg=proc.create_config()
cfg.set_property('run-mode',Gimp.RunMode.NONINTERACTIVE);cfg.set_property('image',doc)
cfg.set_property('file',Gio.File.new_for_path(str(out/'ciel-cubism-eye-reload-inspection.png')))
assert proc.run(cfg).index(0)==Gimp.PDBStatusType.SUCCESS
doc.delete()
(out/'ciel-cubism-eye-reload-inspection-report.json').write_text(json.dumps(dict(
    status='visual_motion_check_not_final_appearance_approval',model_sha256=expected,
    rows=['gaze -1','gaze +1'],columns=['open 1','open 0.5','open 0'],
    closed_crops_equal=True,
    observation='Stationary contours retained after reload. Iris perimeter serration remains visible at gaze extremes.',
    eye='character left, screen right',crop=[1340,350,cw,ch],screenshots=evidence,
    limits=['Editor screenshot crops, not exported runtime textures','Only the left eye rig is tested','Edges and hair remain unfinished']),indent=2)+'\n',encoding='utf-8')
print('CUBISM_EYE_INSPECTION_READY',flush=True)
