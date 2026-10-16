"""Combine the native tail export with existing expressions, motion and physics."""
from pathlib import Path
import copy
import json
import shutil

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'.local/tail-integration/draft/runtime'
BASE = ROOT/'assets/ciel/runtime'
META = ROOT/'.local/tail-integration/draft'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path, data):path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    old, new = read(BASE/'Ciel.model3.json'), read(OUT/'Ciel.model3.json')
    for key in ('Expressions', 'Motions', 'Physics'):
        if key in old['FileReferences']:new['FileReferences'][key] = old['FileReferences'][key]
    for key in ('Groups', 'HitAreas'):
        if key in old:new[key] = old[key]
    for folder in ('Expressions', 'Motions'):
        shutil.copytree(BASE/folder, OUT/folder, dirs_exist_ok=True)
    physics = read(BASE/'Ciel.physics3.json')
    prior_groups = [s for s in physics['PhysicsSettings'] if s['Id'] != 'PhysicsSettingCielTail']
    physics['PhysicsSettings'] = copy.deepcopy(prior_groups)
    physics['Meta']['PhysicsDictionary'] = [s for s in physics['Meta']['PhysicsDictionary'] if s['Id'] != 'PhysicsSettingCielTail']
    group = {
        'Id': 'PhysicsSettingCielTail',
        'Input': [{'Source': {'Target': 'Parameter', 'Id': 'ParamCielTailWag'},
                   'Weight': 100, 'Type': 'X', 'Reflect': False}],
        'Output': [{'Destination': {'Target': 'Parameter', 'Id': pid}, 'VertexIndex': index,
                    'Scale': scale, 'Weight': 100, 'Type': 'Angle', 'Reflect': False}
                   for pid, index, scale in [('ParamCielTailFollow', 1, .25), ('ParamCielTailTip', 2, .25)]],
        'Vertices': [
            {'Position': {'X': 0, 'Y': 0}, 'Mobility': 1, 'Delay': 1, 'Acceleration': 1, 'Radius': 0},
            {'Position': {'X': 0, 'Y': 8}, 'Mobility': .85, 'Delay': .8, 'Acceleration': 1.2, 'Radius': 8},
            {'Position': {'X': 0, 'Y': 16}, 'Mobility': .80, 'Delay': .9, 'Acceleration': 1.0, 'Radius': 8}],
        'Normalization': {'Position': {'Minimum': -8, 'Default': 0, 'Maximum': 8},
                          'Angle': {'Minimum': -18, 'Default': 0, 'Maximum': 18}}}
    physics['PhysicsSettings'].append(group)
    meta = physics['Meta']
    meta['PhysicsDictionary'].append({'Id': group['Id'], 'Name': '尻尾の追従'})
    meta.update(PhysicsSettingCount=len(physics['PhysicsSettings']),
                TotalInputCount=sum(len(s['Input']) for s in physics['PhysicsSettings']),
                TotalOutputCount=sum(len(s['Output']) for s in physics['PhysicsSettings']),
                VertexCount=sum(len(s['Vertices']) for s in physics['PhysicsSettings']))
    assert physics['PhysicsSettings'][:-1] == prior_groups
    write(META/'physics-group.json', group)
    write(OUT/'Ciel.physics3.json', physics)
    write(OUT/'Ciel.model3.json', new)
    print('TAIL_RUNTIME_PACKAGED', len(physics['PhysicsSettings']), 'physics groups')


if __name__ == '__main__':main()
