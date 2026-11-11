"""Real-model intake guard probes; actions are recorded, never sent to Minecraft.

Run in benchmark-runner with --entrypoint python -m benchmark.target_intake.
This measures interpretation/argument binding, not physical completion or audio.
"""
import argparse
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'agent'))
os.environ['CIEL_LLM_BACKEND'] = 'local'
os.environ['CIEL_LOCAL_LLM_URL'] = os.environ.get('CIEL_BENCH_LLM_URL', 'http://127.0.0.1:8094/v1')
from game_env import GameEnv
from game_intake import GameIntake
from livekit.agents import llm

REFERENCE = {'selection_id': '11111111-1111-4111-8111-111111111111', 'source': 'owner_pointer',
             'points': [{'x': x, 'y': 63, 'z': z, 'face': [0, 1, 0], 'block': 'grass_block'}
                        for x, z in ((5, 0), (6, 1))]}
CASES = [
    ('explicit_over_old_pointer', 'X=5〜6、Y=64、Z=0〜1の土を取り除いてください。', True,
     ('minecraft_clear_region', dict(x1=5, x2=6, y1=64, y2=64, z1=0, z2=1))),
    ('floor_exact_height', 'X=5〜6、Y=64、Z=0〜1にオークの板材で床を敷いてください。', True,
     ('minecraft_build_region', dict(x1=5, x2=6, y1=64, y2=64, z1=0, z2=1, block='oak_planks'))),
    ('point_floor', '今選んだ地面の2つの角の間、その上にオークの板材で床を敷いてください。', True,
     ('minecraft_pointed_action', dict(selection_id=REFERENCE['selection_id'], action='floor', block='oak_planks'))),
    ('negative_coordinate', 'X=-12、Z=4の場所に行ってください。', True,
     ('minecraft_go_to_place', dict(x=-12, z=4))),
    ('missing_height', 'X=5〜6、Z=0〜1にオークの板材で床を敷いてください。', True, None),
    ('conflicting_correction', 'X=5〜6、Y=64、Z=0〜1、いやY=65に床を敷いてください。', True, None),
    ('missing_reference', 'この作業台を回収してください。', False, None),
    ('negation', '今選んだ範囲の土は取り除かないでください。', True, None),
]


async def run(args):
    catalog = GameEnv('minecraft', args.url)
    try:
        if not await catalog.prepare():
            raise RuntimeError('Dedicated body catalog unavailable')
        profile, tools, meta = copy.deepcopy(catalog.profile), list(catalog.tools), copy.deepcopy(catalog.meta)
        instructions = (Path(__file__).resolve().parents[1]/'agent/config/prompts/game_intake.md').read_text(encoding='utf-8')
        rows = []
        async with asyncio.timeout(180):
            for name, text, has_reference, expected in CASES:
                calls = []
                async def use(name, arguments):
                    calls.append((name, arguments))
                    return {'status': 'accepted'}
                async def start(name, arguments, **kwargs):
                    calls.append((name, arguments))
                    return {'task_id': 'recorded-only'}
                async def refresh():
                    return True
                env = SimpleNamespace(profile=profile, tools=tools, meta=meta, playing=lambda: True,
                    _connection_epoch=1, _body={}, state={'references': copy.deepcopy(REFERENCE) if has_reference else None},
                    _refresh=refresh, use=use)
                runner = SimpleNamespace(env=env, work=None, status=lambda: {}, body_step=lambda: None, start=start)
                intake = GameIntake(runner, instructions)
                began = time.monotonic()
                try:
                    reply = await intake.handle(llm.ChatMessage(id=name, role='user', content=[text]))
                    passed = calls == ([expected] if expected else [])
                    # Abstention probes require a resolved intake response, not a timeout/error.
                    operational_error = reply in ('依頼の操作を確認できませんでした。', '作業の依頼を確認できませんでした。')
                    rows.append(dict(case=name, passed=passed and not operational_error, calls=calls,
                                     reply=reply, seconds=round(time.monotonic()-began, 3)))
                finally:
                    await intake.close()
        source = Path(__file__).resolve().parents[1]/'agent'
        hashes = {name: hashlib.sha256((source/name).read_bytes()).hexdigest()
                  for name in ('game_intake.py', 'target_candidates.py', 'config/prompts/game_intake.md')}
        report = dict(scope='real_model_intake_recorded_actions_no_world_execution', cases=rows,
                      source=hashes, fixture_sha256=hashlib.sha256(json.dumps(CASES, ensure_ascii=False).encode()).hexdigest())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
        return 0 if all(row['passed'] for row in rows) else 1
    finally:
        await catalog.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8773/mcp')
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
