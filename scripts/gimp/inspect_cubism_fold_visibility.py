"""Compare the same Cubism half-blink with the upper-fold layer hidden/shown.

Run in GIMP. Screenshots are diagnostic input, not rendering golden files.
"""
import os, json, hashlib
from pathlib import Path
from gi.repository import Gimp, Gio, Gegl

root=Path(os.environ['CIEL_PROJECT_ROOT'])
out=root/'docs/assets/ciel/production'
sources=['.local/iris-alpha-half.png','.local/fold-preserved-half.png']
rect=Gegl.Rectangle.new(1340,330,300,230)
fmt="R'G'B'A u8"
doc=Gimp.Image.new(600,230,Gimp.ImageBaseType.RGB)
for col,source in enumerate(sources):
    im=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(root/source)))
    rgba=bytes(im.get_layers()[0].get_buffer().get(rect,1.0,fmt,Gegl.AbyssPolicy.NONE))
    im.delete()
    layer=Gimp.Layer.new(doc,['Fold opacity 0','Fold opacity 100'][col],300,230,Gimp.ImageType.RGBA_IMAGE,100,Gimp.LayerMode.NORMAL)
    doc.insert_layer(layer,None,0)
    layer.get_buffer().set(Gegl.Rectangle.new(0,0,300,230),fmt,rgba)
    layer.set_offsets(col*300,0)
proc=Gimp.get_pdb().lookup_procedure('file-png-export');cfg=proc.create_config()
cfg.set_property('run-mode',Gimp.RunMode.NONINTERACTIVE);cfg.set_property('image',doc)
cfg.set_property('file',Gio.File.new_for_path(str(out/'ciel-cubism-fold-visibility-comparison.png')))
assert proc.run(cfg).index(0)==Gimp.PDBStatusType.SUCCESS
doc.delete()
model=root/'assets/private/ciel/live2d/gimp/face-remake-v2/semantic-parts-import-check.cmo3'
assert hashlib.sha256(model.read_bytes()).hexdigest()=='9b967f017f2b7f91d9388851687856e8694e3726436e27694635b5176b0046d0'
report={
 'status':'diagnostic_only_temporary_change_undone',
 'layout':['Left: EyeLOpen 0.5, UpperFold opacity 0','Right: same state, UpperFold opacity 100'],
 'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
 'source_screenshots':[{'path':s,'sha256':hashlib.sha256((root/s).read_bytes()).hexdigest()} for s in sources],
 'observation':'Showing the fold restores pale hair-adjacent contours but also leaves dark isolated marks above the moving lash.',
 'conclusion':'Neither whole-layer fading nor whole-layer retention is accepted. Split stationary hair/skin from lash remnants before retesting.',
 'limits':['One half-blink at centered gaze only','No full animation approval','Dark marks are visually suspected lash remnants; anatomical tracing still required'],
 'next_action':'Trace the mixed UpperFold material and reassign stationary contours; do not tune opacity as a substitute for correct material separation.'}
(out/'ciel-cubism-fold-visibility-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('FOLD_VISIBILITY_DIAGNOSTIC_READY',flush=True)
