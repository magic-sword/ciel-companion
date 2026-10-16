"""Verify native SDK tail controls and regressions, then render real-model proofs."""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts/live2d'))
import cubism_core as cc
spec = importlib.util.spec_from_file_location('renderer', ROOT/'scripts/live2d/render-moc.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
OUT = ROOT/'assets/ciel/rig/proofs/tail-v63'
SDK = ROOT/'assets/ciel/runtime'


def write(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def snapshot(model, values):
    model.reset(); assert not model.set(values); model.update()
    return {d['id']: d for d in model.drawables()}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    backup = ROOT/'.local/tail-adoption/before/runtime/Ciel.model3.json'
    assert backup.exists(), 'Restore the pre-tail SDK under .local/tail-adoption/before/runtime for regression comparison'
    old = cc.Model(backup)
    new = cc.Model(SDK/'Ciel.model3.json')
    assert all(p in new.param_range for p in ('ParamCielTailWag', 'ParamCielTailFollow', 'ParamCielTailTip'))
    original = snapshot(old, {})
    current = snapshot(new, {})
    assert set(current)-set(original) == {'Tail_Left', 'Tail_Right'}
    assert len(original) == 111 and len(current) == 113
    assert current['Tail_Left']['opacity'] == current['Tail_Right']['opacity'] == 0
    for name in ('Tail_Left', 'Tail_Right'):
        d = current[name]
        assert len(d['pos']) == len(d['uv']) == 441
        assert d['tri'].min() >= 0 and d['tri'].max() < len(d['pos'])
        assert d['double_sided'], 'Mirrored views need double-sided rendering'
    poses = [{}, {'ParamBreath': 1}, {'ParamAngleX': -30}, {'ParamAngleX': 30},
             {'ParamAngleY': -30}, {'ParamAngleY': 30}, {'ParamBodyAngleZ': -10},
             {'ParamBodyAngleZ': 10}, {'ParamCielJacketVisible': 0},
             {'ParamCielHandPoseL': 1, 'ParamCielHandPoseR': 1},
             {'ParamCielHandPoseL': 2, 'ParamCielHandPoseR': 2}]
    expression_poses = []
    for path in sorted((SDK/'Expressions').glob('*.exp3.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        expression_poses.append((path.stem, {p['Id']: p['Value'] for p in data['Parameters']}))
    max_delta = 0.
    for values in poses+[v for _, v in expression_poses]:
        a, b = snapshot(old, values), snapshot(new, values)
        for ident in original:
            assert ident in b
            delta = float(np.max(np.abs(a[ident]['pos']-b[ident]['pos'])))
            max_delta = max(max_delta, delta)
            assert delta < .005, (ident, values, delta)
            assert abs(a[ident]['opacity']-b[ident]['opacity']) < 1e-6, ident
            assert np.array_equal(a[ident]['tri'], b[ident]['tri']), ident
    physics = json.loads((SDK/'Ciel.physics3.json').read_text(encoding='utf-8'))
    for group in physics['PhysicsSettings']:
        for value in group['Input']:assert value['Source']['Id'] in new.param_range
        for value in group['Output']:assert value['Destination']['Id'] in new.param_range
    grid_checks = []
    for wag in np.linspace(-1, 1, 41):
        for follow, tip in [(-1, -1), (0, 0), (1, 1)]:
            ds = snapshot(new, {'ParamCielTailWag': float(wag), 'ParamCielTailFollow': follow, 'ParamCielTailTip': tip})
            tails = [ds[n] for n in ('Tail_Left', 'Tail_Right')]
            assert all(np.isfinite(d['pos']).all() for d in tails)
            assert not (tails[0]['opacity'] > 1e-5 and tails[1]['opacity'] > 1e-5)
            grid_checks.append(float(wag))
    follow_checks = {}
    for side, wag in [('Left', -1), ('Right', 1)]:
        ident = 'Tail_'+side
        base = snapshot(new, {'ParamCielTailWag': wag})[ident]['pos']
        assert np.ptp(base[:, 0]) > 1500 and np.ptp(base[:, 1]) > 1500
        for pid in ('ParamCielTailFollow', 'ParamCielTailTip'):
            moved = snapshot(new, {'ParamCielTailWag': wag, pid: 1})[ident]['pos']
            delta = float(np.abs(moved-base).max())
            assert delta > .5, (ident, pid, delta)
            follow_checks[side+'_'+pid] = delta
    tex = r.load_textures(new)
    crop = (-650, -100, 2850, 3600)
    font = ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc', 20)
    tiles = []
    for label, wag in [('左へ振る', -1), ('中央・通常', 0), ('右へ振る', 1)]:
        snapshot(new, {'ParamCielTailWag': wag})
        pic = r.render(new, tex, .18, crop)
        tile = Image.new('RGB', (pic.width, pic.height+36), (64, 72, 104))
        tile.paste(pic, (0, 36));ImageDraw.Draw(tile).text((10, 6), label, font=font, fill='white')
        tiles.append(tile)
    sheet = Image.new('RGB', (tiles[0].width*3, tiles[0].height), (64, 72, 104))
    for i, tile in enumerate(tiles):sheet.paste(tile, (i*tile.width, 0))
    sheet.save(OUT/'sdk-poses.png')
    snapshot(new, {})
    neutral = r.render(new, tex, .18, crop)
    snapshot(old, {})
    old_pic = r.render(old, r.load_textures(old), .18, crop)
    # SDK bleed RGB under fully transparent pixels may differ, but neutral
    # output must be indistinguishable when the new tail meshes are hidden.
    neutral_delta = int(np.abs(np.asarray(neutral, int)-np.asarray(old_pic, int)).max())
    assert neutral_delta <= 1, neutral_delta
    snapshot(new, {'ParamCielTailWag': 1, 'ParamCielJacketVisible': 0})
    r.render(new, tex, .18, crop).save(OUT/'sdk-jacket-off.png')
    frames = []
    for i in range(32):
        phase = 2*math.pi*i/32
        snapshot(new, {'ParamCielTailWag': math.sin(phase),
                       'ParamCielTailFollow': .5*math.sin(phase-.5),
                       'ParamCielTailTip': .6*math.sin(phase-1)})
        frames.append(r.render(new, tex, .14, crop))
        if i % 8 == 0:print('SDK_PROOF_FRAME', i, flush=True)
    frames[0].save(OUT/'sdk-wag.gif', save_all=True, append_images=frames[1:],
                   duration=[60, 60, 60, 70]*8, loop=0, disposal=2)
    write('runtime-verification.json', {'passed': True, 'old_drawables': 111, 'new_drawables': 113,
        'existing_mesh_max_delta_px': max_delta, 'neutral_pixel_max_delta': neutral_delta,
        'regression_poses': len(poses)+len(expression_poses), 'tail_parameter_checks': len(grid_checks),
        'tail_views_mutually_exclusive': True, 'physics_groups': len(physics['PhysicsSettings']),
        'follow_through_max_displacement_px': follow_checks,
        'physics_parameter_ids_valid': True,
        'gif_is_parameter_demonstration_not_physics_simulation': True,
        'moc_sha256': hashlib.sha256((SDK/'Ciel.moc3').read_bytes()).hexdigest()})
    print('NATIVE_TAIL_RUNTIME_VERIFIED', max_delta, flush=True)


if __name__ == '__main__':main()
