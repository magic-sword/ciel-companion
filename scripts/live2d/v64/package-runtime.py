"""ほっぺを組み込んで書き出したモデルに、今の表情・モーション・物理演算を合わせ、ほっぺの揺れ（ぷるん）の物理演算を足す（v64）。

書き出し先：.local/cheek-integration/draft/runtime（Cubism の「moc3 ファイル書き出し」で、ここへ書き出しておく）。
ほっぺの揺れ：押す量（ParamCielCheekPoke{L,R}）を入力に、短くて硬い振り子を揺らし、その角度を ParamCielCheekJiggle{L,R} へ出す。
押した瞬間と、離した瞬間（押す量が急に 0 へ戻る）に振り子が振れ、数回揺れて止まる。揺れはワープの押す量に足される
（integrate-cheek.py：押す量 + 0.6 × 揺れ）ので、離したあと、ほっぺが小さくふくらんだり戻ったりする。
"""
from pathlib import Path
import copy
import json
import shutil

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'.local/cheek-integration/draft/runtime'
BASE = ROOT/'assets/ciel/runtime'
META = ROOT/'.local/cheek-integration/draft'
NAMES = {'L': 'ほっぺの揺れ（左）', 'R': 'ほっぺの揺れ（右）'}


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path, data):path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def cheek_group(side):
    return {
        'Id': f'PhysicsSettingCielCheek{side}',
        'Input': [{'Source': {'Target': 'Parameter', 'Id': f'ParamCielCheekPoke{side}'},
                   'Weight': 100, 'Type': 'X', 'Reflect': False}],
        'Output': [{'Destination': {'Target': 'Parameter', 'Id': f'ParamCielCheekJiggle{side}'}, 'VertexIndex': 1,
                    'Scale': 1.6, 'Weight': 100, 'Type': 'Angle', 'Reflect': False}],
        # 短い 1 本の振り子。離すと揺れが −0.5 → +0.6 → −0.3 と振れ、約 0.6 秒で収まる（押す量に 0.6 倍で足すので、以前の試し描きのばねと同じくらいのふくらみ）（Unity の物理演算と同じ式で試算）
        'Vertices': [
            {'Position': {'X': 0, 'Y': 0}, 'Mobility': 1, 'Delay': 1, 'Acceleration': 1, 'Radius': 0},
            {'Position': {'X': 0, 'Y': 3}, 'Mobility': .95, 'Delay': .9, 'Acceleration': 2.0, 'Radius': 3}],
        'Normalization': {'Position': {'Minimum': -1.5, 'Default': 0, 'Maximum': 1.5},
                          'Angle': {'Minimum': -25, 'Default': 0, 'Maximum': 25}}}


def main():
    old, new = read(BASE/'Ciel.model3.json'), read(OUT/'Ciel.model3.json')
    for key in ('Expressions', 'Motions', 'Physics'):
        if key in old['FileReferences']:new['FileReferences'][key] = old['FileReferences'][key]
    for key in ('Groups', 'HitAreas'):
        if key in old:new[key] = old[key]
    for folder in ('Expressions', 'Motions'):
        shutil.copytree(BASE/folder, OUT/folder, dirs_exist_ok=True)
    physics = read(BASE/'Ciel.physics3.json')
    ids = {cheek_group(s)['Id'] for s in NAMES}
    prior_groups = [s for s in physics['PhysicsSettings'] if s['Id'] not in ids]
    physics['PhysicsSettings'] = copy.deepcopy(prior_groups)
    meta = physics['Meta']
    meta['PhysicsDictionary'] = [s for s in meta['PhysicsDictionary'] if s['Id'] not in ids]
    groups = [cheek_group(s) for s in NAMES]
    for side, group in zip(NAMES, groups):
        physics['PhysicsSettings'].append(group)
        meta['PhysicsDictionary'].append({'Id': group['Id'], 'Name': NAMES[side]})
    meta.update(PhysicsSettingCount=len(physics['PhysicsSettings']),
                TotalInputCount=sum(len(s['Input']) for s in physics['PhysicsSettings']),
                TotalOutputCount=sum(len(s['Output']) for s in physics['PhysicsSettings']),
                VertexCount=sum(len(s['Vertices']) for s in physics['PhysicsSettings']))
    assert physics['PhysicsSettings'][:len(prior_groups)] == prior_groups
    write(META/'physics-groups.json', groups)
    write(OUT/'Ciel.physics3.json', physics)
    write(OUT/'Ciel.model3.json', new)
    print('CHEEK_RUNTIME_PACKAGED', len(physics['PhysicsSettings']), 'physics groups')


if __name__ == '__main__':main()
