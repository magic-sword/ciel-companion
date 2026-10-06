"""Pack original open parts and approved closed parts without altering the rig."""
import os
from pathlib import Path
ROOT=Path(os.environ['CIEL_PROJECT_ROOT'])
exec((ROOT/'scripts/gimp/eye_material_core.py').read_text(encoding='utf-8'))
OUT=ROOT/'assets/private/ciel/live2d/gimp/approved-eye-motion-v1'
paths=[ROOT/'assets/private/ciel/live2d/gimp/open-eye-materials/semantic-hair-parts.psd',OUT/'closed-materials.psd']
sources=[Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(p))) for p in paths]
doc=Gimp.Image.new(W,H,Gimp.ImageBaseType.RGB)
for item in reversed(sources[0].get_layers()):
    if item.get_name()!='Hair_Foreground':layer(doc,item.get_name(),pixels(item))
for item in reversed(sources[1].get_layers()):
    if '_Closed_' in item.get_name():layer(doc,item.get_name(),pixels(item)).set_opacity(0)
hair=next(item for item in sources[0].get_layers() if item.get_name()=='Hair_Foreground')
layer(doc,'Hair_Foreground',pixels(hair))
for item in doc.get_layers():
    item.set_blend_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
    item.set_composite_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
assert composite(doc)==reference
expected={item.get_name():pixels(item) for item in doc.get_layers()}
for suffix,proc in (('xcf','gimp-xcf-save'),('psd','file-psd-export')):
    path=OUT/f'open-closed-import-kit.{suffix}'
    run_proc(proc,image=doc,file=Gio.File.new_for_path(str(path)))
    loaded=Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,Gio.File.new_for_path(str(path)))
    assert composite(loaded)==reference
    assert {item.get_name():pixels(item) for item in loaded.get_layers()}==expected
    assert all(item.get_opacity()==0 for item in loaded.get_layers() if '_Closed_' in item.get_name())
    loaded.delete()
for item in doc.get_layers():
    if '_Closed_' in item.get_name():item.set_opacity(100)
    elif item.get_name() not in ('Context','Hair_Foreground'):item.set_visible(False)
assert composite(doc)==composite(sources[1])
for source in sources:source.delete()
doc.delete()
(OUT/'import-kit-report.json').write_text(json.dumps(dict(status='psd_import_kit_not_rigged',
    layer_count=len(expected),normal_equal=True,closed_equal=True,psd_xcf_all_parts_equal=True,
    initial_closed_layer_opacity=0,layer_names=list(expected),
    outputs={suffix:dict(file=f'open-closed-import-kit.{suffix}',
             sha256=hashlib.sha256((OUT/f'open-closed-import-kit.{suffix}').read_bytes()).hexdigest())
             for suffix in ('xcf','psd')},
    inputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths],
    limits=['Cubism import of this kit not verified','No meshes, keyforms or motion in this PSD',
            'Intermediate shapes require alignment before opacity blending']),indent=2)+'\n',encoding='utf-8')
print('APPROVED_EYE_IMPORT_KIT_READY',flush=True)
