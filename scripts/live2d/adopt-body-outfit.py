"""Adopt the approved v60 export, or verify the committed current package.

Run with --adopt once from the reviewed draft; the default is read-only.
Authoring PNGs have independent canvas sizes/offsets to retain off-canvas arms.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image
import cubism_core as cc

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / 'assets/ciel/current'
PROOF = ROOT / 'assets/ciel/rig/proofs/body-outfit-v60'
RUNTIME = ROOT / 'assets/ciel/runtime'
RIG = ROOT / 'assets/ciel/rig/ciel.cmo3'
SOURCE = ROOT / 'assets/ciel/generated/v60'
DRAFT = ROOT / 'assets/ciel/rig/drafts/body-outfit'
META = ROOT / 'assets/ciel/rig/body-outfit'
RETIRED = {'Body', 'Jacket_Front', 'Jacket_Back'}
EXPECTED_RIG = 'c47bec98801a07f322c3b3a14f0dec99c916a4940869569b2bb1e8716af4c88e'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def adopt():
    assert sha(DRAFT / 'body-outfit.cmo3') == EXPECTED_RIG
    for name in ['runtime-verification', 'master-runtime-verification', 'lighting-verification']:
        assert read(PROOF / (name + '.json'))['passed']
    previous = read(CURRENT / 'approved.json')
    assert sha(RIG) == previous['rig_sha256']
    backup = ROOT / '.local/body-outfit-adoption/before'
    assert not backup.exists(), 'Adoption backup already exists; use default verification instead'
    backup.mkdir(parents=True)
    shutil.copy2(RIG, backup / 'ciel.cmo3')
    shutil.copytree(CURRENT, backup / 'current')
    shutil.copytree(RUNTIME, backup / 'runtime')
    manifest = read(CURRENT / 'layers.json')
    new = read(SOURCE / 'layers.json')['layers']
    back = [e for e in new if e['name'] == 'Jacket48_Back' or e['name'].startswith('Jacket52_')]
    body = [e for e in new if e['name'].startswith('Body48_') and 'Hand' not in e['name']]
    front = [e for e in new if e not in back + body]
    groups = {'Jacket_Back': back, 'Body': body, 'Jacket_Front': front}
    layers = []
    for entry in manifest['layers']:
        if entry['name'] in RETIRED:
            for addition in groups[entry['name']]:
                item = dict(addition)
                item['path'] = 'assets/ciel/current/layers/' + item['name'] + '.png'
                item.update(canvas=[3000, 3800], offset=[0, 0])
                shutil.copy2(ROOT / addition['path'], ROOT / item['path'])
                layers.append(item)
        else:
            item = dict(entry)
            item.update(canvas=[2172, 2896], offset=[414, 0])
            layers.append(item)
    for name in RETIRED:
        (CURRENT / 'layers' / (name + '.png')).unlink()
    manifest.update(canvas=[3000, 3800], model_canvas=[2172, 2896],
                    model_origin_offset=[414, 0], layers=layers)
    write(CURRENT / 'layers.json', manifest)
    shutil.copy2(DRAFT / 'body-outfit.cmo3', RIG)
    META.mkdir(parents=True, exist_ok=True)
    for name in ['controls.json', 'hierarchy.json']:
        shutil.copy2(DRAFT / name, META / name)
    previous.update(approved_date='2026-10-15', rig_sha256=sha(RIG),
                    material_count=len(layers), body_outfit_revision='v60',
                    latest_proofs='assets/ciel/rig/proofs/body-outfit-v60',
                    latest_body_outfit_proofs='assets/ciel/rig/proofs/body-outfit-v60',
                    body_outfit_controls='assets/ciel/rig/body-outfit/controls.json')
    previous['export_files'] = [dict(path=p.relative_to(DRAFT / 'runtime').as_posix(), sha256=sha(p))
                                for p in sorted((DRAFT / 'runtime').rglob('*')) if p.is_file()]
    write(CURRENT / 'approved.json', previous)
    write(PROOF / 'adoption.json', dict(approved_date='2026-10-15', source_revision='v60',
          rig='assets/ciel/rig/ciel.cmo3', rig_sha256=sha(RIG),
          previous_rig_sha256=sha(backup / 'ciel.cmo3'), material_count=len(layers),
          new_material_count=22, retired_materials=sorted(RETIRED),
          sdk_package='assets/ciel/runtime', unity_applied=False))
    write(PROOF / 'verification.json', dict(reset_passed=True,
          evidence='runtime-verification.json', expression_count=11))
    subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/live2d/prepare-current-runtime.py'),
                    str(DRAFT / 'runtime')], check=True)


def verify():
    approved = read(CURRENT / 'approved.json')
    adoption = read(PROOF / 'adoption.json')
    manifest = read(RUNTIME / 'manifest.json')
    assert sha(RIG) == approved['rig_sha256'] == adoption['rig_sha256'] == manifest['source_rig_sha256'] == EXPECTED_RIG
    layers = read(CURRENT / 'layers.json')['layers']
    assert len(layers) == len({e['name'] for e in layers}) == approved['material_count'] == 111
    assert {Path(e['path']).name for e in layers} == {p.name for p in (CURRENT / 'layers').glob('*.png')}
    assert not RETIRED.intersection(e['name'] for e in layers)
    for entry in layers:
        with Image.open(ROOT / entry['path']) as image:
            assert image.size == tuple(entry['canvas']) and image.mode == 'RGBA'
    for entry in manifest['files']:
        assert sha(RUNTIME / entry['path']) == entry['sha256'], entry['path']
    for entry in manifest['materials']:
        assert sha(ROOT / entry['path']) == entry['sha256'], entry['path']
    unity = ROOT / 'unity/Assets/Characters/Ciel'
    if adoption['unity_applied']:
        assert sha(unity / 'runtime-manifest.json') == sha(RUNTIME / 'manifest.json')
        for entry in manifest['files']:
            assert sha(unity / entry['path']) == entry['sha256'], entry['path']
    for entry in read(SOURCE / 'layers.json')['layers']:
        assert sha(ROOT / entry['path']) == sha(CURRENT / 'layers' / (entry['name'] + '.png'))
    model = cc.Model(RUNTIME / 'Ciel.model3.json')
    if adoption['unity_applied']:
        prefab = (unity / 'Ciel.prefab').read_text(encoding='utf-8')
        names = set(re.findall(r'^  m_Name: (.+)$', prefab, re.MULTILINE))
        assert {d['id'] for d in model.drawables()} <= names
        assert set(model.param_ids) <= names
        serialized = (unity / 'Ciel.asset').read_text(encoding='utf-8')
        payload = serialized.split('  _bytes: ', 1)[1].splitlines()[0]
        # Unity 6 appends its byte-array scalar marker to the hexadecimal data.
        if payload.endswith('y'):
            payload = payload[:-1]
        assert hashlib.sha256(bytes.fromhex(payload)).hexdigest() == sha(RUNTIME / 'Ciel.moc3')
    controls = read(META / 'controls.json')
    for name, spec in controls.items():
        assert np.allclose(model.param_range[name], [spec['min'], spec['default'], spec['max']])
    poses = 0
    for coat in [0, 1]:
        for hand in [0, 1, 2]:
            model.reset()
            assert not model.set(dict(ParamCielJacketVisible=coat, ParamCielHandPoseL=hand, ParamCielHandPoseR=hand))
            model.update()
            draw = {d['id']: d for d in model.drawables()}
            assert len(draw) == 111 and all(np.isfinite(d['pos']).all() for d in draw.values())
            if not coat:
                assert all(d['opacity'] == 0 for key, d in draw.items() if key.startswith(('Jacket48', 'Jacket52')))
            for side in 'LR':
                values = [draw[f'Body48_Hand{kind}_{side}']['opacity'] for kind in ['Relaxed', 'Open', 'Fist']]
                assert np.allclose(values, np.eye(3)[hand])
            poses += 1
    expressions = read(RUNTIME / 'Ciel.model3.json')['FileReferences']['Expressions']
    assert len(expressions) == 11
    for entry in expressions:
        model.reset()
        assert not model.set({p['Id']: p['Value'] for p in read(RUNTIME / entry['File'])['Parameters']})
        model.update()
        assert all(np.isfinite(d['pos']).all() for d in model.drawables())
    model.reset()
    model.update()
    assert all(np.isclose(v, cc.lib().csmGetParameterValues(model.m)[model.param_ids.index(k)]) for k, (_, v, _) in model.param_range.items())
    return dict(passed=True, rig_sha256=sha(RIG), material_count=len(layers),
                sdk_file_count=len(manifest['files']), drawable_count=111,
                parameter_count=len(model.param_ids), garment_hand_poses=poses,
                expressions_checked=len(expressions), reset_passed=True,
                sources_and_package_checksums_match=True, unity_applied=adoption['unity_applied'])


if __name__ == '__main__':
    if '--adopt' in sys.argv:
        adopt()
    result = verify()
    if '--adopt' in sys.argv:
        write(PROOF / 'adoption-verification.json', result)
    print(json.dumps(result, indent=2))
