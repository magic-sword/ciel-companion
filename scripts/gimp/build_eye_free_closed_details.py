"""Reuse approved closed lashes over the persistent eye-free base, in GIMP 3.

This prepares additive details only: no closed-skin layer or replacement face.
It does not modify the manually rigged Cubism model or its source PSD.
"""
import os
from pathlib import Path

ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
exec((ROOT / 'scripts/gimp/eye_material_core.py').read_text(encoding='utf-8'))
OUT = ROOT / 'assets/private/ciel/live2d/gimp/eye-free-closed-details'
OUT.mkdir(parents=True, exist_ok=True)
base_path = ROOT / 'assets/private/ciel/live2d/gimp/eye-free-face/eye-free-face.psd'
detail_path = ROOT / 'assets/private/ciel/live2d/gimp/approved-eye-motion-v1/closed-materials.psd'
base_doc = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(base_path)))
base_parts = [(l.get_name(), pixels(l)) for l in reversed(base_doc.get_layers())]
assert composite(base_doc) == reference
base_doc.delete()
base_parts = [(name, bytearray(rgba)) for name, rgba in base_parts]
part_map = dict(base_parts)
# Material ownership candidate: the previous foreground contour followed the
# eye's outer arc and retained part of the eyelid crease in the hair. Transfer
# a narrow traced band into the open-lid detail, leaving known crossing strands.
# Keep this candidate separate from the source PSD and hand-rigged model.
ownership_changes = []
ownership_alpha = []
bright_tip_restored = []
white_rim_reassigned = []
for side in ('L',):
    g = data[side]['g']
    foreground = part_map[f'Hair_{side}']
    fixed = part_map['Periorbital_contours_REVIEW']
    lid = part_map[f'{side}_UpperLash']
    # Trace the vertical inner strand separately from the curved lid fold.
    # The previous narrow band left its outer ends and isolated dark pixels.
    inner_tip = [(180,20),(185,20),(190,43),(189,48),(185,46),(181,33)]
    for y in range(40, 79):
        for x in range(g['x'][0], g['x'][1] + 1):
            i = 4 * (y * W + x)
            outer = curve(g['outer'], x + .5)
            if not outer - 12 <= y + .5 < outer + 1:
                continue
            if not foreground[i + 3] and not fixed[i + 3]:
                continue
            if inside(x + .5, y + .5, inner_tip):
                continue
            if any(inside(x + .5, y + .5, poly)
                   and min(reference[i:i+3]) > (200 if n == 0 else 140)
                   for n, poly in enumerate(g['hair'])):
                continue
            foreground[i:i + 4] = bytes(4)
            fixed[i:i + 4] = bytes(4)
            # Retain only the fold's color contribution, not an opaque skin
            # tile that would move with the eyelid. Reconstruct the reference
            # exactly over the persistent face using encoded-RGB alpha.
            bg = part_map['Face_Base_eye_free_ESTIMATED'][i:i+3]
            if reference[i:i+3] == bg:
                lid[i:i+4] = bytes(4)
                aa = 0
            else:
                for aa in range(1,256):
                    alpha = aa / 255
                    color = [round((reference[i+k]-bg[k]*(1-alpha))/alpha)
                             for k in range(3)]
                    if (all(0 <= v <= 255 for v in color)
                        and all(round(color[k]*alpha+bg[k]*(1-alpha)) == reference[i+k]
                                for k in range(3))):
                        break
                lid[i:i+4] = bytes(color+[aa])
            ownership_alpha.append([x,y,aa])
            ownership_changes.append([x, y])
            # Isolated light tips above the fold are stationary foreground,
            # not moving lash highlights. Only consider the traced upper band;
            # never classify the full image by brightness alone.
            if aa and y + .5 < outer - 4 and min(lid[i:i+3]) > 180:
                foreground[i:i+4] = lid[i:i+4]
                lid[i:i+4] = bytes(4)
                bright_tip_restored.append([x,y])

    # The earlier geometrical lash boundary captured a narrow white wedge on
    # the outer underside. Keep that ocular surface with the white/iris layers.
    # The normal composite assertion below catches overlap ownership mistakes.
    for y in range(57,84):
        for x in range(204,233):
            i=4*(y*W+x)
            if not lid[i+3] or min(reference[i:i+3]) <= 170:
                continue
            if y + .5 < curve(g['upper'],x+.5)-5:
                continue
            target = (part_map[f'{side}_Highlight']
                      if part_map[f'{side}_Iris'][i+3]
                      else part_map[f'{side}_Sclera'])
            target[i:i+4] = reference[i:i+4]
            lid[i:i+4] = bytes(4)
            white_rim_reassigned.append([x,y])
detail_doc = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(detail_path)))
details = {l.get_name(): pixels(l) for l in detail_doc.get_layers() if l.get_name().endswith('_Closed_lash')}
assert set(details) == {'L_Closed_lash', 'R_Closed_lash'}
detail_doc.delete()

def configure(doc):
    for item in doc.get_layers():
        item.set_blend_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)
        item.set_composite_space(Gimp.LayerColorSpace.RGB_NON_LINEAR)

# Keep the existing 17-layer stack intact for Cubism replacement. GIMP's
# regenerated 19-layer PSD reuses numeric layer IDs for different names;
# Cubism consequently linked existing meshes to the wrong artwork in testing.
# Import the two closed lashes separately using the additive kit below.
replacement = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
for name, rgba in base_parts:
    layer(replacement, name, rgba)
configure(replacement)
assert composite(replacement) == reference
replacement_path = OUT / 'eye-free-face-replacement.psd'
run_proc('file-psd-export', image=replacement,
         file=Gio.File.new_for_path(str(replacement_path)))
replacement.delete()
replacement_check = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE,
                                  Gio.File.new_for_path(str(replacement_path)))
assert composite(replacement_check) == reference
assert {l.get_name(): pixels(l) for l in replacement_check.get_layers()} == dict(base_parts)
replacement_check.delete()

# Only the two transparent lash details are exported for additive import.
kit = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
for name, rgba in details.items():
    assert any(rgba[i] == 0 for i in range(3, len(rgba), 4))
    layer(kit, name, rgba)
configure(kit)
run_proc('file-psd-export', image=kit, file=Gio.File.new_for_path(str(OUT / 'closed-eye-details.psd')))
kit.delete()
reloaded = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(OUT / 'closed-eye-details.psd')))
assert {l.get_name(): pixels(l) for l in reloaded.get_layers()} == details
reloaded.delete()

doc = Gimp.Image.new(W, H, Gimp.ImageBaseType.RGB)
inserted = False
for name, rgba in base_parts:
    if name.startswith('Hair_') and not inserted:
        for detail_name, detail_rgba in details.items():
            layer(doc, detail_name, detail_rgba).set_visible(False)
        inserted = True
    layer(doc, name, rgba)
assert inserted
configure(doc)
normal = composite(doc)
assert normal == reference
original_bytes = {l.get_name(): pixels(l) for l in doc.get_layers()}
eye_names = ('Sclera', 'Iris', 'Pupil', 'Highlight', 'UpperLash', 'LowerRim')

def set_closed(sides):
    for item in doc.get_layers():
        name = item.get_name()
        for side in ('L', 'R'):
            if name == f'{side}_Closed_lash':
                item.set_visible(side in sides)
            elif name in {f'{side}_{n}' for n in eye_names}:
                item.set_visible(side not in sides)

set_closed({'L'})
left_closed = composite(doc)
set_closed({'L', 'R'})
both_closed = composite(doc)
assert {l.get_name(): pixels(l) for l in doc.get_layers()} == original_bytes
run_proc('gimp-xcf-save', image=doc, file=Gio.File.new_for_path(str(OUT / 'closed-endpoint-review.xcf')))
set_closed(set())
assert composite(doc) == reference
run_proc('gimp-xcf-save', image=doc, file=Gio.File.new_for_path(str(OUT / 'eye-free-face-with-closed-details.xcf')))
full_psd = OUT / 'eye-free-face-with-closed-details.psd'
run_proc('file-psd-export', image=doc, file=Gio.File.new_for_path(str(full_psd)))
roundtrip = {}
for suffix in ('xcf', 'psd'):
    path = OUT / f'eye-free-face-with-closed-details.{suffix}'
    check = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(path)))
    assert composite(check) == reference
    assert {l.get_name(): pixels(l) for l in check.get_layers()} == original_bytes
    roundtrip[suffix] = dict(neutral_equal=True,all_layer_pixels_equal=True)
    check.delete()
doc.delete()

board = Gimp.Image.new(W * 3, H, Gimp.ImageBaseType.RGB)
for col, (name, rgba) in enumerate([('Normal', normal), ('Left_closed', left_closed), ('Both_closed', both_closed)]):
    layer(board, name, rgba, col * W, 0)
run_proc('file-png-export', image=board, file=Gio.File.new_for_path(str(OUT / 'comparison.png')))
board.delete()
report = dict(
    status='closed_detail_candidate_requires_hair_boundary_and_transition_review',
    architecture='Persistent face base and fixed hair; independent transparent closed lashes',
    base_source_sha256=hashlib.sha256(base_path.read_bytes()).hexdigest(),
    detail_source_sha256=hashlib.sha256(detail_path.read_bytes()).hexdigest(),
    detail_layers=list(details), detail_psd_roundtrip_equal=True,
    shared_base_and_hair_unchanged=True, neutral_equal=True,
    skin_cover_layers_added=0, cubism_import_verified=False,
    limitations=['Hair/eyelid ownership at the original upper-eye arc remains unresolved',
                 'Closed endpoint only; no transition or Cubism key verification',
                 'Source resolution remains 280x195; not a final high-resolution asset'])
report['shared_base_and_hair_unchanged'] = False
report['shared_base_unchanged'] = True
report['hair_and_open_lid_ownership_candidate'] = ownership_changes
report['transferred_fold_alpha'] = ownership_alpha
report['bright_tips_restored_to_hair'] = bright_tip_restored
report['white_underside_reassigned_to_ocular_parts'] = white_rim_reassigned
report['transferred_fold_contains_opaque_skin_tiles'] = False
report['hair_fixed_between_open_and_closed'] = True
report['full_material_layer_count'] = len(original_bytes)
report['full_material_roundtrip'] = roundtrip
report['full_psd_sha256'] = hashlib.sha256(full_psd.read_bytes()).hexdigest()
report['replacement_psd'] = replacement_path.name
report['replacement_layer_count'] = len(base_parts)
report['replacement_roundtrip_equal'] = True
report['replacement_psd_sha256'] = hashlib.sha256(replacement_path.read_bytes()).hexdigest()
report['cubism_import_strategy'] = 'Replace with 17-layer PSD, then add the two-layer lash kit separately; verify links in Editor'
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('EYE_FREE_CLOSED_DETAILS_READY', flush=True)
