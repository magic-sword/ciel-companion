"""Fault injection against the dedicated server auditor, before acceptance runs."""
import asyncio
import copy
import json
import os
from pathlib import Path
import time
import uuid
from . import audit
from .world import Rcon,World


async def run(directory):
    directory.mkdir(parents=True,exist_ok=False)
    rcon=Rcon(os.environ['CIEL_BENCH_RCON_PASSWORD']);world=World(rcon);world.acquire()
    base={'id':'audit_calibration','forest':'none','inventory':{},'milestones':[],
          'spatial':{'initial':[[5,64,0,'dirt']],'expected':[[0,64,0,'air']],'preserve':[[5,64,0,'dirt']]}}
    rows=[]
    identity=None
    try:
        for kind in ('restored_break','flow','gravity'):
            task=copy.deepcopy(base)
            if kind=='flow':task['spatial']['initial'] += [[10,64,0,'water']]+[[10+dx,64+dy,dz,'glass']for dx,dy,dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))]
            if kind=='gravity':task['spatial']['initial'] += [[10,65,0,'stone'],[10,66,0,'gravel']]
            await asyncio.to_thread(world.reset,task,11)
            await asyncio.sleep(.5)
            if kind=='restored_break':
                for command in ('gamemode creative Bench_Owner','tp Bench_Owner 4.5 64 3.5','clear Bench_Owner','give Bench_Owner dirt 1'):
                    await asyncio.to_thread(world._write,command)
                await asyncio.sleep(.5)
            identity=await asyncio.to_thread(audit.start,world)
            if kind=='restored_break':
                command_id=uuid.uuid4().hex
                folder=Path(__file__).parent/'data/observations'
                temp=folder/'point-command.tmp'
                temp.write_text(json.dumps({'id':command_id,'action':'break_restore','position':[5,64,0]}));temp.replace(folder/'point-command.json')
                async with asyncio.timeout(10):
                    while True:
                        try:ack=json.loads((folder/'point-ack.json').read_text())
                        except (FileNotFoundError,ValueError):ack={}
                        if ack.get('id')==command_id:break
                        await asyncio.sleep(.1)
            elif kind=='flow':await asyncio.to_thread(world._write,'setblock 9 64 0 air')
            else:await asyncio.to_thread(world._write,'setblock 10 65 0 air')
            await asyncio.sleep(1)
            result=await asyncio.to_thread(audit.finish,world,identity,task,directory)
            files=list(directory.glob(identity+'-events.jsonl'))
            events=[json.loads(s)for s in files[0].read_text().splitlines()]
            causes={e['cause']for e in events}
            expected={'restored_break':{'break','place'},'flow':{'flow'},'gravity':{'entity_change'}}[kind]
            passed=not result['passed'] and expected<=causes
            if kind=='restored_break':passed=passed and result['changed_cells']==0
            rows.append({'case':kind,'passed':passed,'causes':sorted(causes),'audit':result})
            identity=None
            print(kind,passed,sorted(causes),flush=True)
        report={'scope':'dedicated_server_audit_fault_injection','cases':rows}
        (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0 if all(r['passed']for r in rows)else 1
    finally:
        if identity:
            # An unclosed audit retains its lease for explicit recovery.
            await asyncio.to_thread(audit.finish,world,identity,task,directory)
        await asyncio.to_thread(world.reset,base,11)
        world.release();rcon.close()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    raise SystemExit(asyncio.run(run(parser.parse_args().output)))
