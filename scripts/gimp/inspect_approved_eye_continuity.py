"""Measure and expose consecutive textured-blink frames at the native size."""
import os,json,hashlib
from pathlib import Path
from gi.repository import Gimp,Gio,Gegl
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
OUT=ROOT/'assets/private/ciel/live2d/gimp/approved-eye-motion-v1'
W,H=280,195
FMT="R'G'B'A u8"
results=[]
board=Gimp.Image.new(W*4,H*2,Gimp.ImageBaseType.RGB)
for row,path in enumerate((ROOT/'docs/assets/ciel/production/ciel-face-remake-v2-blink-atlas.png',OUT/'blink-atlas.png')):
    doc=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(path)))
    src=doc.get_layers()[0].get_buffer()
    frames=[bytes(src.get(Gegl.Rectangle.new(W*8,H*b,W,H),1,FMT,Gegl.AbyssPolicy.NONE)) for b in range(33)]
    region=[4*(y*W+x)+c for y in range(40,111) for x in range(35,246) for c in range(3)]
    deltas=[sum(abs(a[i]-b[i]) for i in region)/len(region) for a,b in zip(frames,frames[1:])]
    worst=max(range(32),key=lambda i:deltas[i])
    for col,index in enumerate((0,1,worst,worst+1)):
        layer=Gimp.Layer.new(board,f'{row}_frame_{index}',W,H,Gimp.ImageType.RGBA_IMAGE,100,Gimp.LayerMode.NORMAL)
        board.insert_layer(layer,None,0)
        layer.get_buffer().set(Gegl.Rectangle.new(0,0,W,H),FMT,frames[index])
        layer.set_offsets(col*W,row*H)
    results.append(dict(atlas=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        mean_rgb_step=deltas,onset_mean_rgb_delta=deltas[0],worst_step=[worst,worst+1],
        worst_mean_rgb_delta=deltas[worst],board_frame_indices=[0,1,worst,worst+1]))
    doc.delete()
proc=Gimp.get_pdb().lookup_procedure('file-png-export');cfg=proc.create_config()
cfg.set_property('run-mode',Gimp.RunMode.NONINTERACTIVE);cfg.set_property('image',board)
cfg.set_property('file',Gio.File.new_for_path(str(OUT/'continuity-comparison.png')))
assert proc.run(cfg).index(0)==Gimp.PDBStatusType.SUCCESS
board.delete()
(OUT/'continuity-report.json').write_text(json.dumps(dict(results=results,
    note='Pixel differences measure change, not aesthetic quality; no automatic visual acceptance.',
    board_rows=['previous procedural closed lash','approved textured closed lash']),indent=2)+'\n',encoding='utf-8')
print('APPROVED_EYE_CONTINUITY_READY',flush=True)
