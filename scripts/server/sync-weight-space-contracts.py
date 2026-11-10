#!/usr/bin/env python3
"""Check/update WSP game fixtures from the actual exported game capability schema."""
import argparse
import copy
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / 'server/benchmark/weight_space/suite.json'


def updated(suite):
    code = "import('./server/minecraft/src/ciel/tasks.js').then(m=>console.log(JSON.stringify(m.CAPABILITIES)))"
    capabilities = json.loads(subprocess.check_output(['node', '-e', code], cwd=ROOT, encoding='utf-8'))
    capability = next(c for c in capabilities if c['name'] == 'minecraft.obtain_item')
    result = copy.deepcopy(suite)
    for case in result['cases']:
        if case['id'] not in ('submit-dev', 'submit-holdout'):
            continue
        quantity = 8 if case['split'] == 'dev' else 6
        case['context'] = ('利用可能サービス: 1=game。未ロード。ゲーム接続中。正式な能力定義: '
                           + json.dumps(capability, ensure_ascii=False, separators=(',', ':')))
        case['messages'] = [{'role': 'user', 'content':
            f'オークの原木を{quantity}個集めて。作業名は原木集め、期限90秒。周囲になければ探し、難しければ確認してください。'}]
        case['steps'][1]['arguments'] = dict(capability=capability['name'],
            arguments=dict(item='oak_log', quantity=quantity, quantity_mode='gain'),
            constraints=dict(resource_scope='search', failure_policy='ask'), title='原木集め', seconds=90)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Update the two fixtures; default only checks drift')
    args = parser.parse_args()
    current = json.loads(SUITE.read_text(encoding='utf-8'))
    expected = updated(current)
    if current == expected:
        print('Game fixture matches the exported capability contract')
        return 0
    if not args.write:
        print('Game fixture differs from current capability contract; regenerate and remeasure BOTH variants')
        return 1
    SUITE.write_text(json.dumps(expected, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Updated game fixtures; previous suite results are not directly comparable')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
