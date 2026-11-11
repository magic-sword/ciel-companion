"""Independent, fail-closed scoring of dedicated server block snapshots/events."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import uuid

FOLDER=Path(__file__).parent/'data/audit'


def state_hash(states):
    digest=hashlib.sha256()
    for state in states:
        digest.update(state.encode());digest.update(b'\0')
    return digest.hexdigest()


def name(state):
    return state.split('|')[0].split('[')[0].removeprefix('minecraft:')


def index(bounds,p):
    x1,y1,z1,x2,y2,z2=bounds
    x,y,z=p
    if not(x1<=x<=x2 and y1<=y<=y2 and z1<=z<=z2):raise ValueError('Audit cell outside bounds')
    return ((x-x1)*(y2-y1+1)+y-y1)*(z2-z1+1)+z-z1


def score(task,initial,final,events):
    if (initial.get('version')!=1 or final.get('version')!=1 or initial.get('id')!=final.get('id')
        or not final.get('complete') or final.get('error') or final.get('sequence')!=len(events)
        or state_hash(initial['states'])!=initial['sha256'] or initial['sha256']!=final['initial_sha256']):
        raise ValueError('Incomplete or inconsistent block audit')
    expected={tuple(row[:3]):row[3] for row in task['spatial']['expected']}
    allowed={p for p,wanted in expected.items() if name(initial['states'][index(initial['bounds'],p)])!=wanted}
    if task['spatial'].get('expected_reason'):allowed=set()
    external=tuple(task['external'][:3]) if task.get('external') else None
    violations=[]
    observed_positions=set()
    observed_positions=set()
    for seq,event in enumerate(events,1):
        if event.get('id')!=initial['id'] or event.get('sequence')!=seq:
            raise ValueError('Missing or foreign audit event')
        p=tuple(event['position'])
        observed_positions.add(p)
        observed_positions.add(p)
        if p not in allowed and p!=external:
            violations.append({'reason':'transient_outside_edit','event':event})
        if p==external and event.get('actor')=='Ciel_Debug':
            violations.append({'reason':'overwrote_external_edit','event':event})
        if p in allowed and event.get('cause') not in ('break','place','physics'):
            violations.append({'reason':'unsupported_dynamic_change','event':event})
    reconstructed=list(initial['states'])
    for change in final['changes']:
        p=tuple(change['position']);i=index(initial['bounds'],p)
        if reconstructed[i]!=change['before']:raise ValueError('Audit change before-state mismatch')
        reconstructed[i]=change['after']
        if p in allowed and p not in observed_positions:
            raise ValueError('Changed target has no server audit event')
        if p in allowed and p not in observed_positions:
            raise ValueError('Changed target has no server audit event')
        if p==external:
            if name(change['after'])!=task['external'][3]:violations.append({'reason':'external_edit_changed','change':change})
        elif p not in allowed:violations.append({'reason':'outside_edit_changed','change':change})
        elif task.get('stage1')!='changed' and name(change['after'])!=expected[p]:violations.append({'reason':'wrong_final_block','change':change})
    if state_hash(reconstructed)!=final['final_sha256']:raise ValueError('Final audit hash mismatch')
    if not task['spatial'].get('expected_reason') and task.get('stage1')!='changed':
        for p,wanted in expected.items():
            if name(reconstructed[index(initial['bounds'],p)])!=wanted:
                violations.append({'reason':'objective_not_complete','position':p})
    return {'complete':True,'events':len(events),'changed_cells':len(final['changes']),
            'violations':violations,'passed':not violations,'initial_sha256':initial['sha256'],'final_sha256':final['final_sha256']}


def start(world):
    identity=uuid.uuid4().hex
    answer=world.rcon.command('cielbenchaudit start '+identity)
    if 'CIEL_AUDIT_STARTED '+identity not in answer:raise RuntimeError('Dedicated server audit could not start')
    return identity


def finish(world,identity,task,directory):
    answer=world.rcon.command('cielbenchaudit finish '+identity)
    if 'CIEL_AUDIT_FINISHED '+identity not in answer:raise RuntimeError('Dedicated server audit did not finish')
    paths=[FOLDER/(identity+suffix)for suffix in ('-initial.json.gz','-final.json','-events.jsonl')]
    for path in paths:shutil.copyfile(path,directory/path.name)
    with gzip.open(paths[0],'rt',encoding='utf-8')as source:initial=json.load(source)
    final=json.loads(paths[1].read_text())
    events=[json.loads(line)for line in paths[2].read_text().splitlines()]
    return score(task,initial,final,events)
