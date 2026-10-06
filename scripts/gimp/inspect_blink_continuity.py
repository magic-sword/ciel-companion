"""Inspect rendered blink intervals inside GIMP; metrics are not visual approval."""
import os,json,hashlib
from pathlib import Path
from gi.repository import Gimp,Gio,Gegl
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
OUT=ROOT/'assets/private/ciel/live2d/gimp/face-remake-v2'
W,H=280,195
manifest=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
levels=manifest['expression_atlas']['blink_levels']
gazes=manifest['expression_atlas']['gaze_frames']
assert levels==33 and gazes==17
eyes=manifest['browser_masks']['eye_pixels']
image=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(OUT/'blink-atlas.png')))
buffer=image.get_layers()[0].get_buffer()
frames=[bytes(buffer.get(Gegl.Rectangle.new(W*8,H*n,W,H),1.0,"R'G'B'A u8",Gegl.AbyssPolicy.NONE)) for n in range(levels)]
image.delete()
def difference(a,b):
    values=[abs(a[p*4+c]-b[p*4+c]) for p in eyes for c in range(3)]
    return dict(mean_eye_channel_delta=sum(values)/len(values),max_channel_delta=max(values),
                pixels_with_channel_delta_over_24=sum(max(abs(a[p*4+c]-b[p*4+c]) for c in range(3))>24 for p in eyes))
fine=[dict(start=n,end=n+1,**difference(frames[n],frames[n+1])) for n in range(levels-1)]
coarse=[dict(start=n,end=n+4,**difference(frames[n],frames[n+4])) for n in range(0,levels-1,4)]
worst=max(fine,key=lambda v:v['mean_eye_channel_delta'])
doc=Gimp.Image.new(W*2,H,Gimp.ImageBaseType.RGB)
for col,n in enumerate([worst['start'],worst['end']]):
    layer=Gimp.Layer.new(doc,f'Closure_{n}_of_32',W,H,Gimp.ImageType.RGBA_IMAGE,100,Gimp.LayerMode.NORMAL)
    doc.insert_layer(layer,None,0)
    layer.get_buffer().set(Gegl.Rectangle.new(0,0,W,H),"R'G'B'A u8",frames[n])
    layer.set_offsets(col*W,0)
doc.scale(W*6,H*3)
proc=Gimp.get_pdb().lookup_procedure('file-png-export');cfg=proc.create_config()
cfg.set_property('run-mode',Gimp.RunMode.NONINTERACTIVE);cfg.set_property('image',doc)
cfg.set_property('file',Gio.File.new_for_path(str(OUT/'blink-largest-step.png')))
assert proc.run(cfg).index(0)==Gimp.PDBStatusType.SUCCESS
doc.delete()
report=dict(status='measurement_not_visual_approval',blink_levels=levels,gaze_px=0,
    atlas_sha256=hashlib.sha256((OUT/'blink-atlas.png').read_bytes()).hexdigest(),
    fine_intervals=fine,coarse_9_level_equivalent=coarse,worst_fine_interval=worst,
    worst_coarse_mean_delta=max(v['mean_eye_channel_delta'] for v in coarse),
    limits=['Metrics cover central gaze only', 'Pixel deltas include intended moving edges',
            'Smaller frame intervals do not prove correct geometry or hair compositing'])
(OUT/'blink-continuity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('BLINK_CONTINUITY_READY',json.dumps(worst),flush=True)
