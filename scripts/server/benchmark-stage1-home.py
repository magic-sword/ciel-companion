#!/usr/bin/env python3
"""Stage-1 benchmark orchestration on the existing dedicated home environment."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex

spec = importlib.util.spec_from_file_location('benchmark_home', Path(__file__).with_name('benchmark-home.py'))
home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot', 'run', 'intake', 'diagnose', 'calibrate', 'matrix','status'])
    parser.add_argument('--scope',choices=['pilot','intake','intake-fresh','regression','basic','world'],default='pilot')
    parser.add_argument('--variant', choices=['baseline', 'candidate','paired'], default='candidate')
    parser.add_argument('--mode', choices=['body', 'conversation'], default='body')
    parser.add_argument('--only-mode',choices=['body','conversation'],help='Select one mode for the regression, basic or world matrix')
    parser.add_argument('--task', action='append', default=[])
    parser.add_argument('--seed', type=int, choices=[11, 29,47,65], default=11)
    parser.add_argument('--repeat', type=int, choices=[1, 2], default=1)
    parser.add_argument('--group', type=int, choices=range(16))
    parser.add_argument('--case',action='append',default=[])
    args = parser.parse_args()
    if args.variant=='paired'and not(args.action=='matrix'and args.scope in('world','basic')):
        parser.error('paired requires matrix --scope world or basic')
    if args.only_mode and not(args.action=='matrix'and args.scope in('regression','basic','world')):
        parser.error('--only-mode requires matrix --scope regression, basic or world')
    if args.action=='status':
        home.remote('''
from pathlib import Path
import json,collections
root=Path.home()/'work/ciel-companion-benchmark/server/benchmark/data/results'
paths=list(root.glob('stage1-*/matrix.json'))
if not paths:raise SystemExit('No stage-1 matrix found')
path=max(paths,key=lambda p:p.stat().st_mtime);matrix=json.loads(path.read_text())
counts=collections.Counter();by_variant={};failures=[]
for report in path.parent.glob('shard-*/report.json'):
    data=json.loads(report.read_text())
    index=int(report.parent.name.removeprefix('shard-'))
    variant=matrix['planned_jobs'][index].get('variant',matrix['variant'])
    for row in data.get('trials',data.get('cases',[])):
        status=row.get('status')or('passed'if row.get('passed')else'failed')
        counts[status]+=1
        by_variant.setdefault(variant,collections.Counter())[status]+=1
        if status!='passed':failures.append({'variant':variant,**{k:row.get(k)for k in ('task','id','reason','error')if k in row}})
print(json.dumps({'matrix':path.parent.name,'variant':matrix['variant'],'scope':matrix['scope'],'state':matrix['state'],
    'completed_shards':len(matrix['completed']),'planned_shards':len(matrix['planned_jobs']),
    'results':dict(counts),'by_variant':by_variant,'failure_count':len(failures),'recent_failures':failures[-8:]},ensure_ascii=False,indent=2))
''')
        return
    if args.action=='diagnose':
        home.remote('''
from pathlib import Path
import json
p=Path.home()/'work/ciel-companion-benchmark/server/benchmark/data/observations/body-state.json'
s=json.loads(p.read_text())
print(json.dumps({k:s.get(k)for k in ('t','body','motion','path_probe')},ensure_ascii=False,indent=2))
''')
        return
    if any(not name.replace('_', '').isalnum() for name in args.task):
        parser.error('Invalid task ID')
    if len(args.task)*args.repeat > 3:
        parser.error('At most three trials per run')
    if args.action=='run' and not args.task:
        parser.error('Select one to three explicit trials')
    if args.action=='intake' and args.group is None and not 1<=len(args.case)<=3:
        parser.error('Select a group of at most three intake cases')
    if args.action == 'snapshot':
        home.remote('''
from pathlib import Path
import subprocess,tarfile,json,hashlib
root=Path.home()/'work/ciel-companion-benchmark/server'
dest=root/'stage1-baseline'
dest.mkdir(parents=True,exist_ok=True)
archive=dest/'source.tar.gz'
if archive.exists(): raise SystemExit('Baseline snapshot already exists; refusing overwrite')
with tarfile.open(archive,'x:gz') as out:
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if p.is_file() and not p.is_symlink() and not any(k in ('stage1-baseline','data','node_modules','__pycache__','.venv') for k in rel.parts) and not p.name.startswith('.env'):
            out.add(p,arcname=str(rel),recursive=False)
images={}
for service in ('agent-bench','body-bench','owner-bench'):
    image='ciel-minecraft-benchmark-'+service
    identity=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
    subprocess.run(['docker','tag',identity,image+':stage1-baseline'],check=True)
    images[service]=identity
(dest/'manifest.json').write_text(json.dumps({'images':images,'source_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},indent=2))
print(json.dumps({'snapshot':str(dest),'images':images}))
''')
        return
    fresh=None
    if args.scope=='intake-fresh':
        if args.action!='matrix':parser.error('intake-fresh requires matrix')
        fixture_path=Path(__file__).with_name('minecraft-stage1-fresh.py')
        fixture_spec=importlib.util.spec_from_file_location('stage1_fresh',fixture_path)
        fixture_module=importlib.util.module_from_spec(fixture_spec);fixture_spec.loader.exec_module(fixture_module)
        if home.provenance()['source_sha256']!=fixture_module.FROZEN_LOCAL_SOURCE_SHA256:
            parser.error('Application/evaluator differs from the fresh-input freeze; do not tune against these inputs')
        fresh=dict(cases=fixture_module.fresh_cases(),generator=fixture_path.read_text(encoding='utf-8'),
            orchestrator=Path(__file__).read_text(encoding='utf-8'),frozen_source=fixture_module.FROZEN_SOURCE_SHA256,
            local_source=fixture_module.FROZEN_LOCAL_SOURCE_SHA256)
    # The evaluator/fixtures are always current; baseline worker images and its
    # prompt mount remain pinned independently of staging candidate source.
    parameters = dict(variant=args.variant, mode=args.mode, tasks=args.task,
                      seed=args.seed, repeat=args.repeat, group=args.group, action=args.action,cases=args.case,scope=args.scope,only_mode=args.only_mode,fresh=fresh,
                      orchestrator_source=Path(__file__).read_text(encoding='utf-8'))
    home.remote('PARAMS=' + repr(parameters) + '\n' + r'''
from pathlib import Path
import subprocess,json,time,tarfile,os,fcntl
root=Path.home()/'work/ciel-companion-benchmark/server'
lock=(root/'.stage1-orchestrator.lock').open('a')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit('Another benchmark orchestrator is active')
active=subprocess.check_output(['docker','ps','-q','--filter','label=com.docker.compose.project=ciel-minecraft-benchmark','--filter','label=com.docker.compose.service=benchmark-runner'],text=True).strip()
if active:raise SystemExit('A dedicated benchmark runner is active')
source=root/'stage1-baseline/source'
if not (source/'agent/game_intake.py').exists():
    source.mkdir(parents=True,exist_ok=True)
    with tarfile.open(root/'stage1-baseline/source.tar.gz') as archive: archive.extractall(source)
base=['docker','compose','--env-file','.env.benchmark','-f','compose.benchmark.yaml','--profile','runner','--profile','conversation']
candidate_base=list(base)
baseline_base=None
def run(*args): return subprocess.run(base+list(args),cwd=root,check=True)
def archive_source(destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not os.access(destination.parent,os.W_OK):
        relative=destination.parent.resolve().relative_to(root/'benchmark/data/results')
        run('run','--rm','--no-deps','-T','--entrypoint','chown','benchmark-runner',
            str(os.getuid())+':'+str(os.getgid()),'/workspace/server/benchmark/data/results/'+str(relative))
    with tarfile.open(destination,'x:gz')as archive:
        for file in sorted(root.rglob('*')):
            rel=file.relative_to(root)
            if file.is_file()and not file.is_symlink()and not any(k in ('data','stage1-baseline','node_modules','__pycache__','.venv')for k in rel.parts)and not file.name.startswith('.env'):
                archive.add(file,arcname=str(rel),recursive=False)
run('build','benchmark-runner','minecraft-bench')
run('build','owner-bench')
if PARAMS['variant']in('baseline','paired'):
    override=root/'stage1-baseline/compose.json'
    override.write_text(json.dumps({'services':{
      name:{'image':'ciel-minecraft-benchmark-'+name+':stage1-baseline',**({'volumes':[str(source/'agent/config')+':/app/config:ro']} if name=='agent-bench' else {})}
      for name in ('agent-bench','body-bench')}}))
    baseline_base=base+['-f',str(override)]
if PARAMS['variant']=='baseline':base=baseline_base
else: run('build','agent-bench','body-bench','owner-bench')
run('up','-d','--no-build','minecraft-bench','body-bench','owner-bench',*(['agent-bench'] if PARAMS['mode']=='conversation' or PARAMS['action']=='matrix' else []))
for filename in ('point-command.json','point-ack.json'):
    (root/'benchmark/data/observations'/filename).unlink(missing_ok=True)
# Paper throttles rapid logins from the shared Docker source address. Allow
# the up/recreate login to settle before the explicit source-reloading restart.
time.sleep(5)
run('restart','owner-bench')

def actors_ready():
    until=time.monotonic()+60
    while True:
        listing=subprocess.check_output(base+['exec','-T','minecraft-bench','rcon-cli','list'],cwd=root,text=True)
        if 'Ciel_Debug' in listing and 'Bench_Owner' in listing:return
        if time.monotonic()>=until:raise SystemExit('Dedicated fixture actors did not spawn')
        time.sleep(.5)
actors_ready()
name='stage1-'+PARAMS['variant']+'-'+PARAMS['action']+'-'+PARAMS['mode']+'-'+str(time.time_ns())
output='/workspace/server/benchmark/data/results/'+name
if PARAMS['action']=='matrix':
    kinds=['clear','level','floor','wall','backfill','already_done','shortage','protected','hazard','no_stance','stop_continue','changed']
    jobs=[]
    if PARAMS['scope']in('intake','intake-fresh'):
        jobs=[dict(action='intake',group=g)for g in range(16)]
    elif PARAMS['scope']=='pilot':
        jobs=[dict(action='run',mode=PARAMS['mode'],seed=11,tasks=['s1_'+k for k in kinds[i:i+3]])for i in range(0,12,3)]
    elif PARAMS['scope']=='basic':
        tasks=['gather_logs','stone_pickaxe','come_here_locator','follow_owner','go_to_coordinates','stop_collecting']
        jobs=[dict(action='run',mode=mode,seed=11,tasks=tasks[i:i+3])for mode in ([PARAMS['only_mode']]if PARAMS['only_mode']else ('body','conversation'))for i in range(0,len(tasks),3)]
    elif PARAMS['scope']=='regression':
        tasks=['clear_small_area','build_floor','build_wall','build_missing_materials','clear_protected',
            'clear_small_area_holdout','build_floor_holdout','build_wall_holdout','point_move','point_recover',
            'point_clear','point_floor','point_move_coordinates','point_clear_coordinates','point_floor_coordinates','gaze_move']
        jobs=[dict(action='run',mode=mode,seed=11,tasks=tasks[i:i+3])for mode in ([PARAMS['only_mode']]if PARAMS['only_mode']else ('body','conversation'))for i in range(0,len(tasks),3)]
    else:
        for mode in ([PARAMS['only_mode']]if PARAMS['only_mode']else ('body','conversation')):
            for condition,seed in (('A1',11),('A2',11),('B3',65)):
                jobs.extend(dict(action='run',mode=mode,seed=seed,condition=condition,tasks=['s1_'+k for k in kinds[i:i+3]])for i in range(0,12,3))
            regressions=['gather_logs','stone_pickaxe','come_here_locator','follow_owner','go_to_coordinates','stop_collecting']
            jobs.extend(dict(action='run',mode=mode,seed=11,tasks=regressions[i:i+3])for i in range(0,6,3))
    if PARAMS['variant']=='paired':
        paired=[]
        for index,job in enumerate(jobs):
            candidate_first=(index+int(job.get('condition')=='A2')+int(job['mode']=='conversation'))%2==0
            paired.extend({**job,'variant':variant}for variant in (('candidate','baseline')if candidate_first else('baseline','candidate')))
        jobs=paired
        expected_shards=(4 if PARAMS['scope']=='basic'else 28)*(1 if PARAMS['only_mode']else 2)
        expected_trials=(6 if PARAMS['scope']=='basic'else 42)*(1 if PARAMS['only_mode']else 2)
        assert len(jobs)==expected_shards
        assert all(sum(len(j['tasks'])for j in jobs if j['variant']==v)==expected_trials for v in ('candidate','baseline'))
    evidence=root/'benchmark/data/results'/name;evidence.mkdir()
    images={service:subprocess.check_output(['docker','image','inspect','ciel-minecraft-benchmark-'+service,'--format','{{.Id}}'],text=True).strip()for service in ('body-bench','agent-bench','owner-bench','benchmark-runner','minecraft-bench')}
    manifest={'variant':PARAMS['variant'],'scope':PARAMS['scope'],'planned_jobs':jobs,'completed':[],'state':'running',
        'run_seconds':600,'total_budget_seconds':600*len(jobs),'worker_images':images}
    if PARAMS['variant']=='paired':
        manifest['baseline_snapshot']=json.loads((root/'stage1-baseline/manifest.json').read_text())
        manifest['baseline_override_services']=['agent-bench','body-bench']
        for service in manifest['baseline_override_services']:
            actual=subprocess.check_output(['docker','image','inspect','ciel-minecraft-benchmark-'+service+':stage1-baseline','--format','{{.Id}}'],text=True).strip()
            assert actual==manifest['baseline_snapshot']['images'][service], 'Baseline image changed'
        manifest['order']='preassigned alternating three-trial blocks; A2 reverses A1; conversation reverses body'
    archive_source(evidence/'source.tar.gz')
    (evidence/'orchestrator.py').write_text(PARAMS['orchestrator_source'])
    if PARAMS['fresh']:
        (evidence/'fresh-cases.json').write_text(json.dumps(PARAMS['fresh']['cases'],ensure_ascii=False,indent=2))
        (evidence/'fixture-generator.py').write_text(PARAMS['fresh']['generator'])
        (evidence/'freeze.json').write_text(json.dumps({'source_sha256':PARAMS['fresh']['frozen_source'],'local_source_sha256':PARAMS['fresh']['local_source']}))
    path=evidence/'matrix.json';path.write_text(json.dumps(manifest,indent=2))
    for i,job in enumerate(jobs):
        variant=job.get('variant',PARAMS['variant'])
        if PARAMS['variant']=='paired':
            base=baseline_base if variant=='baseline'else candidate_base
            run('up','-d','--no-build','minecraft-bench','body-bench','owner-bench','agent-bench')
            actors_ready()
        dest=output+'/shard-'+str(i)
        if job['action']=='intake':
            command=['run','--rm','--no-deps','-T','--entrypoint','python','benchmark-runner','-m','benchmark.stage1_intake','--variant',PARAMS['variant'],'--group',str(job['group']),'--output',dest+'/report.json']
            if PARAMS['fresh']:
                wrapper="""import asyncio,copy,json,sys
from pathlib import Path
from types import SimpleNamespace
from benchmark import stage1_intake as evaluation
root=Path(sys.argv[1]);fresh=json.loads((root/'fresh-cases.json').read_text())
original=[c for c in evaluation.scenarios()if c['split']=='development']
cohort=[c for group in range(6)for c in [*original,*fresh]if c['group']==group]
assert len(cohort)==48 and len({c['id']for c in cohort})==48
evaluation.scenarios=lambda **kwargs:copy.deepcopy(cohort)
output=Path(sys.argv[2]);variant=sys.argv[3]
result=asyncio.run(evaluation.run(SimpleNamespace(variant=variant,group=int(sys.argv[4]),case=[],output=output)))
report=json.loads(output.read_text());report.update(suite='spatial-stage1-intake-v3-fresh',
    holdout_policy='24 development + 24 fresh; no worker feedback from fresh inputs; source frozen before this run',
    frozen_source=json.loads((root/'freeze.json').read_text())['source_sha256'])
output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
if report['evaluator']['source_sha256']!=report['frozen_source']:raise SystemExit(2)
raise SystemExit(result)
"""
                command=['run','--rm','--no-deps','-T','--entrypoint','python','benchmark-runner','-c',wrapper,
                    output,dest+'/report.json',PARAMS['variant'],str(job['group'])]
        else:
            command=['run','--rm','--no-deps','-T','benchmark-runner','--mode',job['mode'],'--seed',str(job['seed']),'--repeats','1','--run-seconds','600','--failure-streak','0','--output',dest]
            for task in job['tasks']:command+=['--task',task]
        result=subprocess.run(base+command,cwd=root)
        manifest['completed'].append({'shard':i,'variant':variant,'exit_code':result.returncode})
        path.write_text(json.dumps(manifest,indent=2))
        print(json.dumps({'matrix':name,'shard':i,'exit_code':result.returncode}),flush=True)
        if result.returncode==2 or(result.returncode and PARAMS['scope']!='pilot'and variant=='candidate'):break
    manifest['state']='complete'if len(manifest['completed'])==len(jobs)else 'stopped_for_diagnosis'
    path.write_text(json.dumps(manifest,indent=2))
    raise SystemExit(0 if all(j['exit_code']==0 for j in manifest['completed'])and manifest['state']=='complete'else 1)
if PARAMS['action']=='calibrate':
    command=['run','--rm','--no-deps','-T','--entrypoint','python','benchmark-runner','-m','benchmark.stage1_calibration','--output',output]
elif PARAMS['action']=='intake':
    command=['run','--rm','--no-deps','-T','--entrypoint','python','benchmark-runner','-m','benchmark.stage1_intake','--output',output+'/report.json','--variant',PARAMS['variant']]
    if PARAMS['group'] is not None: command+=['--group',str(PARAMS['group'])]
    for case in PARAMS['cases']:command+=['--case',case]
else:
    command=['run','--rm','--no-deps','-T','benchmark-runner','--mode',PARAMS['mode'],'--seed',str(PARAMS['seed']),'--repeats',str(PARAMS['repeat']),
      '--run-seconds','600','--failure-streak','0','--output',output]
    for task in PARAMS['tasks']: command+=['--task',task]
result=subprocess.run(base+command,cwd=root)
archive_source(root/'benchmark/data/results'/name/'source.tar.gz')
(root/'benchmark/data/results'/name/'orchestrator.py').write_text(PARAMS['orchestrator_source'])
print(json.dumps({'result':name,'exit_code':result.returncode}))
raise SystemExit(result.returncode)
''')


if __name__ == '__main__':
    main()
