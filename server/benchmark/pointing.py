"""Real pointer input fixture. RCON positions actor; only plugin publishes target IDs."""
import asyncio
import json
import time
import uuid
from pathlib import Path
from .navigation import read_body_observation


async def prepare_pointing(task, world, trace):
    folder = Path(__file__).parent/'data/observations'
    selection = None
    for index, point in enumerate(task['pointing']['points']):
        world.guard()
        if not world.lease:
            raise RuntimeError('Point fixture requires a lease')
        x,y,z = point
        # Real gaze ray from a fixed actor position, including points beyond vanilla reach.
        await asyncio.to_thread(world._write, 'tp Bench_Owner 0.5 64 3.5')
        await asyncio.sleep(.4)
        previous = (read_body_observation().get('references') or {}).get('selection_id')
        identity=uuid.uuid4().hex
        cmd={'id':identity, 'look':[x+.5,y+1.001,z+.5], 'append':index>0,
             'action':'gaze' if task['pointing'].get('mode')=='gaze' else 'point'}
        temp=folder/'point-command.tmp'
        temp.write_text(json.dumps(cmd)); temp.replace(folder/'point-command.json')
        started=time.monotonic()
        async with asyncio.timeout(8):
            while True:
                selection=read_body_observation().get('references')
                if selection and selection['selection_id']!=previous and len(selection['points'])==index+1:
                    actual=selection['points'][-1]
                    if [actual[k] for k in ('x','y','z')]!=point:
                        raise RuntimeError('Pointer hit the wrong fixture block')
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
