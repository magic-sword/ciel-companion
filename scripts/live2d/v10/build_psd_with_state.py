"""GIMP 3 batch wrapper for the unchanged existing PSD builder.

Set CIEL_PROJECT_ROOT and CIEL_PSD_MANIFEST as for build_layers_psd.py.
The existing builder ignores visibility. This wrapper adds visibility immediately
after inserting each layer, then uses its existing PSD/XCF export and readback.
PSD writes are performed by the handoff operator, not by the v10 material build.
"""
import os,json
from pathlib import Path

root=Path(os.environ['CIEL_PROJECT_ROOT'])
states=json.loads((root/'assets/ciel/layers/v10/layer-state.json').read_text(encoding='utf-8'))
visibility={r['name']:r['visible'] for r in states['layers']}
source=root/'scripts/live2d/gimp/build_layers_psd.py'
code=source.read_text(encoding='utf-8-sig')
needle='    doc.insert_layer(item, None, 0)'
assert code.count(needle)==1,'Existing builder changed; review wrapper before proceeding.'
code=code.replace(needle,needle+'\n    item.set_visible(v10_visibility[name])')
# Verify visibility on the existing roundtrip, in addition to names and order.
needle2='    assert got == expect, got'
assert code.count(needle2)==1
code=code.replace(needle2,needle2+'\n    assert all(l.get_visible() == v10_visibility[l.get_name()] for l in loaded.get_layers()), "visibility roundtrip"')
exec(compile(code,str(source),'exec'),{'__name__':'__main__','v10_visibility':visibility})
