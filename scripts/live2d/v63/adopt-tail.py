"""Verify the adopted tail materials, native model, SDK package and Unity copy."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
CURRENT = ROOT/'assets/ciel/current'
PROOF = ROOT/'assets/ciel/rig/proofs/tail-v63'
RIG = ROOT/'assets/ciel/rig/ciel.cmo3'

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path, value):path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def verify():
    manifest = read(ROOT/'assets/ciel/runtime/manifest.json')
    approved = read(CURRENT/'approved.json')
    adoption = read(PROOF/'adoption.json')
    assert sha(RIG) == approved['rig_sha256'] == manifest['source_rig_sha256'] == adoption['rig_sha256']
    assert approved['material_count'] == manifest['material_count'] == 113
    layers = read(CURRENT/'layers.json')['layers']
    assert len(layers) == len({e['name'] for e in layers}) == 113
    for item in manifest['files']:assert sha(ROOT/'assets/ciel/runtime'/item['path']) == item['sha256'], item['path']
    for item in manifest['materials']:assert sha(ROOT/item['path']) == item['sha256'], item['path']
    if '--mark-unity' in sys.argv or adoption['unity_applied']:
        unity = ROOT/'unity/Assets/Characters/Ciel'
        assert sha(unity/'runtime-manifest.json') == sha(ROOT/'assets/ciel/runtime/manifest.json')
        for item in manifest['files']:assert sha(unity/item['path']) == item['sha256'], item['path']
        prefab = (unity/'Ciel.prefab').read_text(encoding='utf-8')
        for name in ('Tail_Left', 'Tail_Right', 'ParamCielTailWag', 'ParamCielTailFollow', 'ParamCielTailTip'):
            assert 'm_Name: '+name+'\n' in prefab, name
        guid = (ROOT/'unity/Assets/Scripts/Conversation/CielTail.cs.meta').read_text().split('guid: ')[1].splitlines()[0]
        assert guid in prefab, 'Tail driver missing from prefab'
        payload = (unity/'Ciel.asset').read_text(encoding='utf-8').split('  _bytes: ', 1)[1].splitlines()[0].removesuffix('y')
        assert hashlib.sha256(bytes.fromhex(payload)).hexdigest() == sha(ROOT/'assets/ciel/runtime/Ciel.moc3')
        if '--mark-unity' in sys.argv:
            adoption['unity_applied'] = True;write(PROOF/'adoption.json', adoption)
    result = dict(passed=True, material_count=113, rig_sha256=sha(RIG), unity_applied=adoption['unity_applied'])
    write(PROOF/'adoption-verification.json', result)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    verify()
