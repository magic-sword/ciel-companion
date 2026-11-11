"""Real pointer input fixture. RCON positions actor; only plugin publishes target IDs."""
import asyncio
import json
import time
import uuid
import hashlib
from pathlib import Path
from .navigation import read_body_observation


def validate_capture(actual,point,expected_face=None):
    if [actual[k]for k in ('x','y','z')]!=point:
        raise RuntimeError('Pointer hit the wrong fixture block')
    if expected_face and actual.get('face')!=expected_face:
        raise RuntimeError('Pointer hit the wrong fixture face')


async def prepare_pointing(task, world, trace):
    folder = Path(__file__).parent/'data/observations'
    selection = None
    world.guard()
    if not world.lease:raise RuntimeError('Point fixture requires a lease')
    await asyncio.to_thread(world._write,'gamemode creative Bench_Owner')
    flight=uuid.uuid4().hex
    temp=folder/'point-command.tmp'
    temp.write_text(json.dumps({'id':flight,'action':'flight'}));temp.replace(folder/'point-command.json')
    async with asyncio.timeout(5):
        while True:
            ack=folder/'point-ack.json'
            if ack.exists():
                confirmed=json.loads(ack.read_text())
                if confirmed.get('id')==flight:
                    expected=hashlib.sha256(Path(__file__).with_name('owner.js').read_bytes()).hexdigest()
                    if confirmed.get('source_sha256')!=expected:raise RuntimeError('Point fixture actor source mismatch')
                    trace('pointing_actor_ready',source_sha256=expected)
                    break
            await asyncio.sleep(.05)
    for index, point in enumerate(task['pointing']['points']):
        world.guard()
        if not world.lease:
            raise RuntimeError('Point fixture requires a lease')
        x,y,z = point
        # Only the privileged fixture actor flies. A vertical real ray from
        # above the target is independent of crouch eye-height differences.
        await asyncio.to_thread(world._write,f'tp Bench_Owner {x+.5} {y+5} {z+.5}')
        await asyncio.sleep(.4)
        previous = (read_body_observation().get('references') or {}).get('selection_id')
        identity=uuid.uuid4().hex
        cmd={'id':identity, 'look':[x+.5,y+.999,z+.5], 'append':index>0,
             'action':'gaze' if task['pointing'].get('mode')=='gaze' else 'point'}
        temp=folder/'point-command.tmp'
        temp.write_text(json.dumps(cmd)); temp.replace(folder/'point-command.json')
        started=time.monotonic()
        async with asyncio.timeout(8):
            while True:
                selection=read_body_observation().get('references')
                if selection and selection['selection_id']!=previous and len(selection['points'])==index+1:
                    actual=selection['points'][-1]
                    trace('pointing_attempt',wanted_point=point,wanted_face=task['pointing'].get('expected_face'),reference=selection)
                    validate_capture(actual,point,task['pointing'].get('expected_face'))
                    break
                await asyncio.sleep(.05)
        trace('pointing_capture', elapsed_seconds=round(time.monotonic()-started,3), reference=selection)
    if task['pointing'].get('mode')!='gaze':
        # Looking away must not retarget the accepted explicit selection.
        temp=folder/'point-command.tmp'
        temp.write_text(json.dumps({'id':uuid.uuid4().hex,'action':'look_away'}))
        temp.replace(folder/'point-command.json')
    if task['body_call']['name']=='minecraft_pointed_action':
        task['body_call']['arguments']['selection_id']=selection['selection_id']
    # Keep the actor from collecting the dropped workbench.
    if task['pointing'].get('mode')!='gaze':
        await asyncio.to_thread(world._write,'tp Bench_Owner 30.5 64 30.5')
