"""Compare actual 33-level mouth output against the prior 9-level atlas."""
import hashlib
import json
import os
from pathlib import Path
from gi.repository import Gimp, Gio, Gegl

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
old_path = ROOT / 'assets/private/ciel/live2d/gimp/face-remake-v2/mouth-atlas-before-33.png'
new_path = ROOT / 'docs/assets/ciel/production/ciel-face-remake-v2-mouth-atlas.png'
W, H = 280, 195

def frames(path, count):
    image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(path)))
    assert image.get_width() == W*count and image.get_height() == H
    buffer = image.get_layers()[0].get_buffer()
    result = [bytes(buffer.get(Gegl.Rectangle.new(n*W,0,W,H),1.0,
               "R'G'B'A u8",Gegl.AbyssPolicy.NONE)) for n in range(count)]
    image.delete()
    return result

old, new = frames(old_path,9), frames(new_path,33)
matches = [old[n] == new[n*4] for n in range(9)]
assert all(matches), 'Existing mouth key appearance changed'
region = {y*W+x for y in range(133,157) for x in range(116,166)}
outside = set(range(W*H))-region
assert all(all(frame[p*4:p*4+4] == old[0][p*4:p*4+4] for p in outside) for frame in new)

def intervals(sequence):
    result = []
    for n,(a,b) in enumerate(zip(sequence,sequence[1:])):
        deltas = [abs(a[p*4+c]-b[p*4+c]) for p in region for c in range(3)]
        result.append(dict(start=n,end=n+1,mean_channel_delta=sum(deltas)/len(deltas),
                           max_channel_delta=max(deltas)))
    return result

fine, coarse = intervals(new), intervals(old)
report = dict(status='existing_keys_preserved_continuity_measured',
    old_levels=9,new_levels=33,old_key_matches=matches,outside_mouth_unchanged=True,
    old_atlas_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest(),
    new_atlas_sha256=hashlib.sha256(new_path.read_bytes()).hexdigest(),
    fine_intervals=fine,coarse_intervals=coarse,
    worst_fine_mean_delta=max(v['mean_channel_delta'] for v in fine),
    worst_coarse_mean_delta=max(v['mean_channel_delta'] for v in coarse),
    limits=['Measures raster appearance changes, not anatomical correctness',
            'Does not validate Cubism mouth deformation or Unity playback'])
(ROOT/'docs/assets/ciel/production/ciel-mouth-continuity-report.json').write_text(
    json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('MOUTH_CONTINUITY_READY',report['worst_fine_mean_delta'],report['worst_coarse_mean_delta'],flush=True)
