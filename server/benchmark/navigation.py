"""RCON distance is the navigation oracle; body snapshots attest lifecycle."""
import asyncio
import json
import math
from pathlib import Path
import time
from .policy import Progress, budget
from .report import metrics
from .world import stable

TOOLS = {'come': ('minecraft_come_here', 'come'), 'follow': ('minecraft_follow_me', 'follow'),
         'coordinates': ('minecraft_go_to_place', 'go_to')}


def task_items(task):
    return task.get('milestones', []) + ([task['item']] if 'item' in task else [])


def validate_navigation(task):
    nav = task['navigation']
    if nav.get('kind') not in TOOLS:
        raise ValueError('Unknown navigation kind')
    targets = nav.get('targets')
    if not isinstance(targets, list) or not 1 <= len(targets) <= 4:
        raise ValueError('Navigation needs bounded target stages')
    for p in targets:
        if not isinstance(p, list) or len(p) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in p):
            raise ValueError('Invalid navigation target')
        if not (-40 <= p[0] <= 400 and p[1] == 64 and -40 <= p[2] <= 40):
            raise ValueError('Target outside fixture')
    if nav['kind'] != 'follow' and len(targets) != 1:
        raise ValueError('Only following has moving targets')
    if nav.get('locator_only') and (nav['kind'] != 'come' or targets[0][0] < 200 or abs(targets[0][2]) > 10):
        raise ValueError('Locator-only fixture requires the long corridor')
    if nav.get('hint_source') not in (None, 'azimuth') or (nav.get('hint_source') and not nav.get('locator_only')):
        raise ValueError('Invalid required locator precision')
    expected_args = {'x': targets[0][0], 'z': targets[0][2]} if nav['kind'] == 'coordinates' else {}
    if task.get('body_call') != {'name': TOOLS[nav['kind']][0], 'arguments': expected_args}:
        raise ValueError('Body and conversation tasks must use the same public operation')
    if not 0 < nav.get('range', 3) <= 4 or not 0 < nav.get('hold_seconds', 2) <= 5:
        raise ValueError('Invalid navigation tolerance')
    if nav['kind'] == 'follow' and not task.get('stop_prompt'):
        raise ValueError('Following requires an explicit stop phase')


def read_body_observation():
    value = json.loads((Path(__file__).parent / 'data/observations/body-state.json').read_text())
    if abs(time.time() - value['t']) > 3:
        raise RuntimeError('Benchmark body observation is stale')
    return value


async def prepare_navigation(task, initial):
    """Wait for fixture teleports to reach the actual bot before starting the clock."""
    async with asyncio.timeout(5):
        while True:
            value = read_body_observation()
            p = value.get('target_entity_position')
            known = value['target_entity_known']
            target = initial['target_position']
            synced = p and math.dist([p['x'], p['y'], p['z']], target) < 0.1
            hint = value.get('hint')
            if task['navigation'].get('locator_only'):
                if not known and hint and (not task['navigation'].get('hint_source') or hint['source'] == task['navigation']['hint_source']):
                    return
            elif known and synced:
                return
            await asyncio.sleep(0.1)


async def evaluate_navigation(task, world, driver, trace, initial, *, seconds, max_llm, max_calls,
                              poll=0.5, stable_seconds=5, clock=time.monotonic, sleep=asyncio.sleep,
                              observe=read_body_observation):
    nav = task['navigation']
    limits = budget(task, seconds)
    opening = observe()
    if nav.get('locator_only') and (opening['target_entity_known'] or not opening.get('hint')
            or (nav.get('hint_source') and opening['hint']['source'] != nav['hint_source'])):
        raise RuntimeError('Locator fixture must start with direction data and no target entity')
    trace('navigation_precondition', observation=opening)
    started, wall_started = clock(), time.time()
    trace.phase, trace.started_at = 'execution', wall_started
    await driver.submit(task)
    watch = Progress(initial, task)
    stage = 0
    near_since = stopping = stable_since = None
    stable_snapshot = None
    seen = set()
    expected_skill = TOOLS[nav['kind']][1]
    stage_times = []
    while True:
        elapsed = clock() - started
        for event in driver.events():
            trace('agent_event', event=event)
            if event.get('kind') == 'model_error':
                raise RuntimeError('Inference backend failed')
        for row in trace.execution():
            if id(row) in seen:
                continue
            seen.add(id(row))
            watch.event(row.get('event', row), elapsed)
        current = await asyncio.to_thread(world.snapshot, task_items(task))
        observation = observe()
        body = observation['body']
        active = body.get('current')
        idle = not any(body.get(k) for k in ('current', 'pending', 'owner', 'blocked'))
        last = body.get('last') or {}
        own_last = last.get('skill') == expected_skill and last.get('since', 0) / 1000 >= wall_started
        if math.dist(current['target_position'], nav['targets'][stage]) > 1:
            raise RuntimeError('Fixture owner moved without the scorer')
        distance = math.dist(current['position'], current['target_position'])
        trace('navigation_observation', state=current, body=observation, stage=stage, distance=distance, elapsed=elapsed)
        watch.observe(current, elapsed)
        data = metrics(trace.execution())
        reason, passed = None, False
        if data['llm_calls'] > max_llm or data['game_calls'] > max_calls:
            reason = 'call_budget'
        elif current['health'] <= 0 or current.get('deaths', 0) > initial.get('deaths', 0):
            reason = 'died'
        elif elapsed >= limits['seconds']:
            reason = 'time_budget'
        elif own_last and last.get('phase') == 'failed':
            reason = 'body_' + str(last.get('result', {}).get('reason', 'failed'))
        elif nav['kind'] != 'follow' and own_last and last.get('phase') == 'succeeded' and distance > nav.get('range', 3):
            reason = 'false_completion'
        elif stopping is not None:
            ack = idle and own_last and last.get('result', {}).get('reason') == 'stopped'
            if stable_since is None:
                if ack:
                    stable_since, stable_snapshot = clock(), current
                elif clock() - stopping >= limits['stop_grace']:
                    reason = 'did_not_stop'
            elif not ack or not stable(stable_snapshot, current):
                reason = 'resumed_after_stop'
            elif clock() - stable_since >= stable_seconds:
                reason, passed = 'followed_stopped_and_stayed', True
        elif distance <= nav.get('range', 3):
            confirmed = (active and active.get('skill') == 'follow' and active.get('phase') == 'running') if nav['kind'] == 'follow' else (idle and own_last and last.get('phase') == 'succeeded')
            if confirmed:
                near_since = clock() if near_since is None else near_since
                if clock() - near_since >= nav.get('hold_seconds', 2):
                    stage_times.append(round(elapsed, 3))
                    trace('navigation_stage_verified', stage=stage, elapsed=elapsed)
                    if stage + 1 < len(nav['targets']):
                        stage += 1
                        near_since = None
                        await asyncio.to_thread(world.move_target, nav['targets'][stage])
                    elif nav['kind'] == 'follow':
                        stopping = clock()
                        trace('stop_requested')
                        await driver.stop(task)
                    else:
                        reason, passed = 'arrived_and_stayed', True
            else:
                near_since = None
        else:
            near_since = None
            reason = watch.reason(elapsed, limits)
        if reason is None and near_since is None and stopping is None:
            reason = watch.reason(elapsed, limits)
        if reason:
            return {'status': 'passed' if passed else 'failed', 'reason': reason,
                    'outcome': 'achieved' if passed else 'not_achieved', 'objective_achieved': passed,
                    'elapsed_seconds': round(clock() - started, 3), 'final': current, 'metrics': data,
                    'budget': limits, 'first_action_seconds': watch.first_action,
                    'time_to_goal_seconds': stage_times[-1] if stage_times else None,
                    'navigation_stages': stage_times, 'locator_precondition': opening,
                    'stop_latency_seconds': None if stable_since is None else round(stable_since - stopping, 3),
                    'body_completion_confirmed': passed,
                    'reply_observed': bool(driver.report_complete(wall_started)),
                    'completion_observed': None}  # A reply is not evidence of a completion report.
        await sleep(poll)
