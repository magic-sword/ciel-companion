"""GIMP 3 handoff: v14 layers, neutral visibility, PSD/XCF readback verification.

Set CIEL_PROJECT_ROOT to the repository root, then run in GIMP 3 python-fu-eval.
This wrapper writes assets/ciel/psd/ciel-v14.* and is NOT invoked by build.py.
The v14 material task allows no writes there; run only in a future PSD export task.
"""
import json
import os
from pathlib import Path

root = Path(os.environ['CIEL_PROJECT_ROOT']).resolve()
manifest_path = 'assets/ciel/layers/v14/psd-manifest.json'
os.environ['CIEL_PSD_MANIFEST'] = manifest_path
state = json.loads((root / 'assets/ciel/layers/v14/layer-state.json').read_text(encoding='utf-8'))
manifest = json.loads((root / manifest_path).read_text(encoding='utf-8'))
assert manifest['out'] == 'assets/ciel/psd/ciel-v14'
assert manifest['layers'] == [{k:r[k] for k in ('name','path')} for r in state['layers']]
visibility = {r['name']:r['visible'] for r in state['layers']}
source = root / 'scripts/live2d/gimp/build_layers_psd.py'
code = source.read_text(encoding='utf-8-sig')
needle = '    doc.insert_layer(item, None, 0)'
assert code.count(needle) == 1, 'PSD builder changed; review insertion hook.'
code = code.replace(needle, needle+'\n    item.set_visible(v14_visibility[name])')
needle = '    assert got == expect, got'
assert code.count(needle) == 1, 'PSD builder changed; review readback hook.'
code = code.replace(needle, needle+'\n    assert all(l.get_visible() == v14_visibility[l.get_name()] for l in loaded.get_layers()), "visibility roundtrip"')
exec(compile(code, str(source), 'exec'), {'__name__':'__main__', 'v14_visibility':visibility})
