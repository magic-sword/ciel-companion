"""Exact block oracle plus protected sentinels, independent of body claims."""
import asyncio
import time
import json
import uuid
import math
from pathlib import Path
from .navigation import read_body_observation, task_items
from .policy import Progress, budget
from .report import metrics


async def prepare_spatial(task, trace):
    spec=task['spatial']
    cells={tuple(row[:3]):'air' for row in spec['expected']}
    cells.update({tuple(row[:3]):row[3] for row in spec['initial']+spec['preserve']})
    identity=uuid.uuid4().hex
    path=Path(__file__).parent/'data/observations/spatial-watch.json'
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps({'id':identity,'cells':list(cells)}))
    temp.replace(path)
    async with asyncio.timeout(5):
        while True:
            value=read_body_observation().get('spatial',{})
            if value.get('id')==identity and value.get('blocks')==list(cells.values()):
                trace('spatial_precondition',observation=value)
                return
            await asyncio.sleep(.1)


def validate_spatial(task):
    spec = task['spatial']
    for group in ('initial', 'expected', 'preserve'):
        rows = spec.get(group)
        if not isinstance(rows, list) or len(rows) > 128 or (group == 'expected' and not rows):
            raise ValueError('Invalid spatial fixture cells')
        seen = set()
        for row in rows:
            if not isinstance(row, list) or len(row) != 4:
                raise ValueError('Invalid spatial fixture cell')
            x,y,z,name = row
            if any(type(v) is not int for v in (x,y,z)) or not (-40<=x<=40 and 61<=y<=78 and -40<=z<=40):
                raise ValueError('Spatial fixture outside arena')
            if name not in ('air','dirt','stone','cobblestone','oak_planks','glass','chest','grass_block','crafting_table'):
                raise ValueError('Unknown fixture block')
            if (x,y,z) in seen:
                raise ValueError('Duplicate fixture cell')
            seen.add((x,y,z))
    if task['body_call']['name'] not in ('minecraft_clear_region','minecraft_build_region','minecraft_pointed_action','minecraft_go_to_place'):
        raise ValueError('Invalid spatial body operation')
    if spec.get('expected_reason') not in (None,'missing_materials','protected_block'):
        raise ValueError('Unknown refusal oracle')
    if task.get('pointing'):
        points=task['pointing']['points']
        if not isinstance(points,list) or not 1<=len(points)<=2:
            raise ValueError('Invalid pointing fixture')
        for p in points:
            if len(p)!=3 or any(type(v) is not int for v in p) or not (-35<=p[0]<=35 and 63<=p[1]<=72 and -35<=p[2]<=35):
                raise ValueError('Pointing fixture outside arena')


def spatial_outcome(spec, current, body, started):
    last = body.get('last') or {}
    idle = not any(body.get(k) for k in ('current','pending','owner','blocked'))
    own = last.get('skill') == spec['skill'] and last.get('since',0)/1000 >= started
    if not all(current['spatial_preserved']):
        return 'failed', 'outside_or_protected_changed'
    if own and last.get('phase') in ('failed','succeeded') and idle:
        if spec.get('expected_reason'):
            good = (last.get('phase') == 'failed' and last.get('result',{}).get('reason') == spec['expected_reason']
                    and all(current['spatial_expected']))
            return ('passed','refused_without_changes') if good else ('failed','wrong_refusal_or_changes')
        if last.get('phase') == 'failed':
            return 'failed', 'body_' + str(last.get('result',{}).get('reason'))
        if spec.get('arrival') and math.dist(current['position'],spec['arrival'])>3:
            return 'failed', 'wrong_destination'
        if spec.get('recovered') and current['inventory'].get(spec['recovered'],0)<1:
            return 'failed', 'item_not_recovered'
        return ('passed','blocks_verified') if all(current['spatial_expected']) else ('failed','false_completion')
    return None


async def evaluate_spatial(task, world, driver, trace, initial, *, seconds, max_llm, max_calls,
                           poll=0.5, clock=time.monotonic, sleep=asyncio.sleep, observe=read_body_observation):
    limits=budget(task,seconds)
    started,wall_started=clock(),time.time()
    trace.phase,trace.started_at='execution',wall_started
    await driver.submit(task)
    watch=Progress(initial,task)
    seen=set()
    best=sum(initial['spatial_expected'])
    while True:
        for event in driver.events():
            trace('agent_event',event=event)
            if event.get('kind')=='model_error':
                raise RuntimeError('Inference backend failed')
        elapsed=clock()-started
        for row in trace.execution():
            if id(row) not in seen:
                seen.add(id(row)); watch.event(row.get('event',row),elapsed)
        current=await asyncio.to_thread(world.snapshot,task_items(task))
        observation=observe()
        trace('spatial_observation',state=current,body=observation,elapsed=elapsed)
        watch.observe(current,elapsed)
        count=sum(current['spatial_expected'])
        if count>best:
            best=count; watch.last_progress=elapsed
        data=metrics(trace.execution())
        outcome=spatial_outcome(task['spatial'],current,observation['body'],wall_started)
        if elapsed>=limits['seconds']:
            outcome=('failed','time_budget')
        elif current['deaths']>initial['deaths'] or current['health']<=0:
            outcome=('failed','died')
        elif data['llm_calls']>max_llm or data['game_calls']>max_calls:
            outcome=('failed','call_budget')
        elif not outcome and watch.reason(elapsed,limits):
            outcome=('failed',watch.reason(elapsed,limits))
        if outcome:
            status,reason=outcome
            passed=status=='passed'
            refusal=bool(task['spatial'].get('expected_reason'))
            return {'status':status,'reason':reason,'outcome':'appropriate_stop' if passed and refusal else 'achieved' if passed else 'not_achieved',
                    'objective_achieved':passed and not refusal,'elapsed_seconds':round(clock()-started,3),
                    'time_to_goal_seconds':round(elapsed,3) if passed and not refusal else None,
                    'first_action_seconds':watch.first_action,'final':current,'metrics':data,'budget':limits,
                    'body_completion_confirmed':passed,'completion_observed':None,
                    'reply_observed':bool(driver.report_complete(wall_started))}
        await sleep(poll)
