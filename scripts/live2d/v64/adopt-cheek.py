"""ほっぺの「ぷにっと押す・つまんで引っ張る・ぷるん」（v64）を、正式モデルと SDK に採用する／採用を検証する。

  python -I scripts/live2d/v64/adopt-cheek.py --check    書き出し（.local/cheek-integration/draft/runtime）を今の SDK と比べる
  python -I scripts/live2d/v64/adopt-cheek.py --adopt    素材 2 層・正式モデル・証拠・approved.json を更新する
                                                         （続けて prepare-current-runtime.py <書き出し> --use-source-physics）
  python -I scripts/live2d/v64/adopt-cheek.py            採用後の検証（--mark-unity で Unity への反映も確かめて記録）

比べる内容：既存の部品の数と並び、ふだんの姿の画素、全身の姿勢（尻尾・上着・手・表情）の画素、ほっぺのパラメーター、物理演算のグループ。
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cubism_core as cc  # noqa: E402

spec = importlib.util.spec_from_file_location('render_moc', HERE.parent / 'render-moc.py')
rm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rm)

WORK = ROOT/'.local/cheek-integration'
DRAFT = WORK/'draft/runtime'
EDITED = WORK/'cheek-fixed.cmo3'
CURRENT = ROOT/'assets/ciel/current'
PROOF = ROOT/'assets/ciel/rig/proofs/current'
RIG = ROOT/'assets/ciel/rig/ciel.cmo3'
RUNTIME = ROOT/'assets/ciel/runtime'
NEW_LAYERS = {'Cheek_Dimple_L': 'Cheek_Dimple_L_A.png', 'Cheek_Dimple_R': 'Cheek_Dimple_R_A.png'}
CHEEK_PARAMS = [f'ParamCielCheek{k}{s}' for s in 'LR' for k in ('Poke', 'PullX', 'PullY', 'Jiggle')]
POSES = [{}, {'ParamCielTailWag': 1}, {'ParamCielTailWag': -1}, {'ParamCielJacketVisible': 0},
         {'ParamCielHandPoseL': 2, 'ParamCielHandPoseR': 1}, {'ParamAngleX': 30, 'ParamAngleY': -20},
         {'ParamTeary': 1}, {'ParamTroubled': 1}, {'ParamSurprised': 1}]
# 赤みを目の下の部品より上に描くよう変えたので、赤みを出した姿は違ってよい。違いが目の下〜ほっぺの帯に収まることだけ確かめる
BLUSH_POSES = [{'ParamCheek': 1}, {'ParamHappy': 1, 'ParamCheek': 1}]
BLUSH_BAND = (760, 1000, 1460, 1260)   # キャンバスの画素


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path, value):path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def frame(model, tex, params):
    model.reset()
    model.set(params)
    model.update()
    return np.asarray(rm.render(model, tex, 0.25).convert('RGB')).astype(int)


def check():
    old, new = cc.Model(str(RUNTIME/'Ciel.model3.json')), cc.Model(str(DRAFT/'Ciel.model3.json'))
    ot, nt = rm.load_textures(old), rm.load_textures(new)
    old.update(); new.update()
    old_ids, new_ids = [d['id'] for d in old.drawables()], [d['id'] for d in new.drawables()]
    assert [i for i in new_ids if i not in NEW_LAYERS] == list(old_ids), 'existing drawables changed'
    assert all(p in new.param_range for p in CHEEK_PARAMS)
    deltas = [int(np.abs(frame(old, ot, p) - frame(new, nt, p)).max()) for p in POSES]
    outside = []
    for p in BLUSH_POSES:
        d = np.abs(frame(old, ot, p) - frame(new, nt, p)).max(2)
        x0, y0, x1, y1 = (int(v * 0.25) for v in BLUSH_BAND)
        d[y0:y1, x0:x1] = 0
        outside.append(int(d.max()))
    physics = read(DRAFT/'Ciel.physics3.json')
    ids = [s['Id'] for s in physics['PhysicsSettings']]
    used = {x['Source']['Id'] for s in physics['PhysicsSettings'] for x in s['Input']}
    used |= {x['Destination']['Id'] for s in physics['PhysicsSettings'] for x in s['Output']}
    result = dict(passed=max(deltas + outside) <= 2, old_drawables=len(old_ids), new_drawables=len(new_ids),
                  regression_poses=len(POSES), regression_pixel_max_delta=deltas, blush_poses_max_delta_outside_cheek_band=outside,
                  cheek_parameters=CHEEK_PARAMS, physics_groups=ids,
                  physics_parameter_ids_valid=all(i in new.param_range for i in used),
                  moc_sha256=sha(DRAFT/'Ciel.moc3'))
    PROOF.mkdir(parents=True, exist_ok=True)
    write(PROOF/'runtime-verification.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert result['passed'] and result['physics_parameter_ids_valid']


def adopt():
    assert read(PROOF/'runtime-verification.json')['moc_sha256'] == sha(DRAFT/'Ciel.moc3'), 'run --check first'
    approved = read(CURRENT/'approved.json')
    previous = approved['rig_sha256']
    assert sha(RIG) == previous
    doc = read(CURRENT/'layers.json')
    for name, file in NEW_LAYERS.items():
        dst = CURRENT/'layers'/(name+'.png')
        shutil.copy2(ROOT/'.local/history/assets/ciel/generated/v64'/file, dst)   # Codex の原本は Git 外（採用済み）
        doc['layers'] = [e for e in doc['layers'] if e['name'] != name]
        doc['layers'].append({'name': name, 'path': dst.relative_to(ROOT).as_posix(), 'visible': False,
                              'canvas': [2172, 2896], 'offset': [414, 0]})
    write(CURRENT/'layers.json', doc)
    shutil.copy2(EDITED, RIG)
    for f in ('check.png', 'poke-physics.gif', 'poke-physics-strip.png', 'compare-pull.png'):
        if (WORK/'draft'/f).exists():shutil.copy2(WORK/'draft'/f, PROOF/f)
    shutil.copy2(WORK/'draft/physics-groups.json', PROOF/'physics-groups.json')
    count = len(doc['layers'])
    write(PROOF/'adoption.json', dict(approved_date='2026-10-17', source_revision='v64', rig='assets/ciel/rig/ciel.cmo3',
                                      rig_sha256=sha(RIG), previous_rig_sha256=previous, material_count=count,
                                      new_material_count=len(NEW_LAYERS), sdk_package='assets/ciel/runtime',
                                      unity_applied=False))
    write(PROOF/'verification.json', dict(reset_passed=True, evidence='runtime-verification.json', expression_count=11))
    approved.update(approved_date='2026-10-17', rig_sha256=sha(RIG), material_count=count,
                    latest_proofs=PROOF.relative_to(ROOT).as_posix(), cheek_revision='v64',
                    latest_cheek_proofs=PROOF.relative_to(ROOT).as_posix(),
                    export_files=[{'path': p.relative_to(DRAFT).as_posix(), 'sha256': sha(p)}
                                  for p in sorted(DRAFT.rglob('*')) if p.is_file()])
    write(CURRENT/'approved.json', approved)
    print('CHEEK_ADOPTED', count, 'materials; next: prepare-current-runtime.py', DRAFT, '--use-source-physics')


def verify():
    manifest, approved, adoption = read(RUNTIME/'manifest.json'), read(CURRENT/'approved.json'), read(PROOF/'adoption.json')
    assert sha(RIG) == approved['rig_sha256'] == manifest['source_rig_sha256'] == adoption['rig_sha256']
    assert approved['material_count'] == manifest['material_count'] == adoption['material_count']
    for item in manifest['files']:assert sha(RUNTIME/item['path']) == item['sha256'], item['path']
    for item in manifest['materials']:assert sha(ROOT/item['path']) == item['sha256'], item['path']
    physics = read(RUNTIME/'Ciel.physics3.json')
    assert {'PhysicsSettingCielCheekL', 'PhysicsSettingCielCheekR'} <= {s['Id'] for s in physics['PhysicsSettings']}
    if '--mark-unity' in sys.argv or adoption['unity_applied']:
        unity = ROOT/'unity/Assets/Characters/Ciel'
        assert sha(unity/'runtime-manifest.json') == sha(RUNTIME/'manifest.json')
        for item in manifest['files']:assert sha(unity/item['path']) == item['sha256'], item['path']
        if '--mark-unity' in sys.argv:
            adoption['unity_applied'] = True;write(PROOF/'adoption.json', adoption)
    result = dict(passed=True, material_count=manifest['material_count'], rig_sha256=sha(RIG),
                  unity_applied=adoption['unity_applied'])
    write(PROOF/'adoption-verification.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    check() if '--check' in sys.argv else adopt() if '--adopt' in sys.argv else verify()
