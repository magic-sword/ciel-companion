"""Run repeatable Minecraft tasks against the body or the complete companion.

python -m benchmark.run --list
python -m benchmark.run --mode body --output /tmp/benchmark-run
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from .drivers import BodyDriver, ConversationDriver, wait_body_released
from .report import metrics, write_reports
from .world import Rcon, World, achieved, stable
from .policy import VERSION as POLICY_VERSION, Progress, budget
from .navigation import evaluate_navigation, validate_navigation, task_items, prepare_navigation
from .distractors import configuration as distractor_configuration
from .spatial import validate_spatial, evaluate_spatial, prepare_spatial
from .pointing import prepare_pointing
from .stage1 import fixture as stage1_fixture, migrate_task
from .mindcraft_tasks import expand as expand_mindcraft, progress as inventory_progress
from . import audit

ROOT = Path(__file__).resolve().parents[2]
SUITE = Path(__file__).with_name('tasks.json')
sys.path.insert(0, str(ROOT/'server'/'agent'))


class Trace:
    def __init__(self, path):
        self.path, self.events, self.phase = path, [], 'setup'
        self.started_at = None

    def __call__(self, kind, **data):
        phase = self.phase
        if kind == 'agent_event' and self.started_at and data['event']['t'] < self.started_at:
            phase = 'setup'
        event = {'t':time.time(), 'phase':phase, 'kind':kind, **data}
        self.events.append(event)
        with self.path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False)+'\n')

    def execution(self):
        return [e for e in self.events if e['phase'] == 'execution']


def load_tasks(path=SUITE):
    suite = json.loads(path.read_text(encoding='utf-8'))
    if suite['version'] != 1 or len({t['id'] for t in suite['tasks']}) != len(suite['tasks']):
        raise ValueError('Invalid task suite version or duplicate ids')
    suite['tasks'] = [stage1_fixture(t['stage1']) if t.get('stage1') else migrate_task(expand_mindcraft(t)) for t in suite['tasks']]
    for task in suite['tasks']:
        budget(task)
        if task.get('navigation'):
            validate_navigation(task)
        if task.get('spatial'):
            validate_spatial(task)
        if task['forest'] not in ('near','far','many','none') or task.get('surface','grass_block') not in ('grass_block','sand'):
            raise ValueError('Unknown fixture layout')
        if task.get('expected_outcome','achieve') not in ('achieve','report_unavailable'):
            raise ValueError('Unknown expected outcome')
        if task.get('expected_outcome') == 'report_unavailable' and (task['forest']!='none' or task['inventory'] or task['item']!='stone_pickaxe'):
            raise ValueError('Unavailable oracle requires stone_pickaxe with no wood resources or supplies')
    return suite['tasks']


def inference_server_info():
    """Record actual shared/dedicated capacity, without prompts or credentials."""
    url = os.environ['CIEL_BENCH_LLM_URL'].rstrip('/').removesuffix('/v1')
    with urllib.request.urlopen(url+'/props', timeout=5) as response:
        props = json.load(response)
    context = props['default_generation_settings']['n_ctx']
    if context < 32768:
        raise RuntimeError('Local inference context must be at least 32768')
    info = {'service':os.environ['CIEL_BENCH_LLM_SERVICE'], 'context':context,
            'parallel':props['total_slots'], 'model':Path(props['model_path']).name}
    control = os.environ.get('CIEL_BENCH_LLM_CONTROL','').rstrip('/')
    if control:
        with urllib.request.urlopen(control+'/mode', timeout=5) as response:
            status = json.load(response)
        info.update(mode=status['mode'], ready=status['ready'])
        if not status['ready']:
            raise RuntimeError('Local inference server is not ready')
    return info


def provenance():
    try:
        result = subprocess.run(['git','-c',f'safe.directory={ROOT.as_posix()}','-C',str(ROOT),'rev-parse','HEAD'],
                                capture_output=True,text=True)
        status = subprocess.run(['git','-c',f'safe.directory={ROOT.as_posix()}','-C',str(ROOT),'status','--porcelain'],
                                capture_output=True,text=True)
    except FileNotFoundError:
        result = status = subprocess.CompletedProcess('git',1,stdout='')
    digest = hashlib.sha256()
    files = list((ROOT/'server'/'agent').glob('*.py'))
    for base in ['agent/config','minecraft/src','minecraft-pointing','benchmark','local-llm']:
        files += [p for p in (ROOT/'server'/base).rglob('*') if p.is_file() and
                  (p.suffix in ('.py','.js','.md','.json','.toml','.java','.xml','.yml') or p.name=='Dockerfile') and 'data' not in p.relative_to(ROOT/'server'/base).parts
                  and p.name != 'staged-provenance.json'
                  and '__pycache__' not in p.parts]
    files += list((ROOT/'server').glob('compose*.yaml'))
    files += [ROOT/'server'/'agent'/'requirements.txt', ROOT/'server'/'minecraft'/'package-lock.json']
    for path in sorted(set(files)):
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    staged_path = Path(__file__).with_name('staged-provenance.json')
    staged = json.loads(staged_path.read_text()) if staged_path.exists() else {}
    return {'git_commit':result.stdout.strip() if result.returncode == 0 else staged.get('git_commit'),
            'git_dirty':bool(status.stdout.strip()) if status.returncode == 0 else staged.get('git_dirty'),
            'source_sha256':digest.hexdigest(), 'suite_sha256':hashlib.sha256(SUITE.read_bytes()).hexdigest()}


def stop_ack(driver, events):
    if driver.stopped():
        return True
    for row in events:
        e = row.get('event', row)
        if e['kind'] == 'tool' and e.get('name') in ('minecraft_stop_moving','stop_goal') and not e.get('is_error'):
            try:
                out = json.loads(e.get('output') or '{}')
            except (ValueError, TypeError):
                continue
            if out.get('status') in ('stopped','stopping'):
                return True
    return False


MOVING_TOOLS = {'minecraft_collect_blocks','minecraft_goal_step','minecraft_craft_item','minecraft_give_item',
                'minecraft_go_to_place','minecraft_follow_me','minecraft_come_here','minecraft_find_blocks','minecraft_dig_down'}


def restarted(events):
    return any(e.get('event',e).get('kind') == 'work_action' or
               (e.get('event',e).get('kind') == 'game_call' and e.get('event',e).get('name') in MOVING_TOOLS) for e in events)


async def evaluate(task, world, driver, trace, initial, *, seconds, max_llm, max_calls,
                   poll=0.5, stop_grace=None, stable_seconds=5, report_grace=5, clock=time.monotonic, sleep=asyncio.sleep):
    if task.get('spatial'):
        return await evaluate_spatial(task, world, driver, trace, initial, seconds=seconds,
                                      max_llm=max_llm, max_calls=max_calls, poll=poll, clock=clock, sleep=sleep)
    if task.get('navigation'):
        return await evaluate_navigation(task, world, driver, trace, initial, seconds=seconds,
            max_llm=max_llm, max_calls=max_calls, poll=poll, stable_seconds=stable_seconds,
            clock=clock, sleep=sleep)
    limits = budget(task,seconds)
    seconds = limits['seconds']
    stop_grace = limits['stop_grace'] if stop_grace is None else stop_grace
    started = clock()
    trace.phase, trace.started_at = 'execution', time.time()
    await driver.submit(task)
    stopping = stable_at = None
    stable_snapshot = None
    ack_index = None
    observed = set()
    false_done = False
    success_at = success_wall = None
    watch = Progress(initial,task)
    blocked_at = decline_stable_at = None
    decline_snapshot = None
    expected_decline = task.get('expected_outcome') == 'report_unavailable'
    seen_body = set()
    while True:
        before = clock()-started
        for e in driver.events():
            trace('agent_event', event=e)
            if e.get('kind') == 'model_error':
                raise RuntimeError('Inference backend failed; inspect the trial model_error event')
            watch.event(e,before)
        # BodyDriver writes directly into Trace, rather than returning agent events.
        if not hasattr(driver,'path'):
            for entry in trace.execution():
                if id(entry) in seen_body or entry['kind'] not in ('game_call','game_result','game_task_result','work_action','work_action_result','work_activity'):
                    continue
                seen_body.add(id(entry))
                watch.event(entry,before)
        current = await asyncio.to_thread(world.snapshot, task['milestones'] + [task['item']])
        now = clock()
        elapsed = now-started
        watch.observe(current,elapsed)
        trace('observation', state=current, elapsed=round(now-started,3))
        observed.update(item for item, count in current['inventory'].items()
                        if count > initial['inventory'].get(item,0))
        data = metrics(trace.execution())
        goal = driver.goal_state.get('task') or {}
        done = achieved(task, initial, current)
        if done and success_at is None and not task.get('stop_after_gain') and not expected_decline and elapsed < seconds:
            success_at, success_wall = now, time.time()
            trace('goal_condition_verified',state=current,elapsed=round(now-started,3))
        if goal.get('state') == 'succeeded' and not done and success_at is None and not task.get('stop_after_gain'):
            false_done = True
        reason = None
        passed = False
        declined = False
        if data['llm_calls'] > max_llm or data['game_calls'] + data.get('work_actions', 0) > max_calls:
            reason = 'call_budget'
        elif current['health'] <= 0 or current.get('deaths',0) > initial.get('deaths',0):
            reason = 'died'
        elif false_done:
            reason = 'false_completion'
        elif elapsed >= seconds:
            reason,passed = ('inventory_verified',True) if success_at is not None else ('time_budget',False)
        elif task.get('stop_after_gain'):
            gained = current['inventory'].get(task['item'],0) - initial['inventory'].get(task['item'],0)
            if stopping is None and gained >= task['stop_after_gain']:
                if done:
                    raise RuntimeError('Cancellation trigger missed: collection already completed')
                trace('stop_requested', gained=gained)
                stopping = now
                await driver.stop(task)
                await sleep(poll)
                continue  # Observe again after stopping, rather than scoring the pre-stop sample.
            if stopping is not None:
                if done:
                    reason = 'finished_before_stop'
                elif stable_at is None and now-stopping >= stop_grace:
                    reason = 'did_not_stop'
                elif stop_ack(driver, trace.execution()):
                    if ack_index is None:
                        ack_index = len(trace.execution())
                        stable_snapshot, stable_at = current, now
                    elif restarted(trace.execution()[ack_index:]) or not stable(stable_snapshot,current):
                        reason = 'resumed_after_stop'
                    elif now-stable_at >= stable_seconds:
                        reason, passed = 'stopped_and_stayed', True
        elif success_at is not None:
            if now-success_at >= report_grace or getattr(driver,'report_complete',lambda after:False)(success_wall):
                reason, passed = 'inventory_verified', True
        elif watch.resumed_after_decline:
            reason = 'resumed_after_decline'
        elif watch.decline is not None and watch.idle(goal):
            if decline_stable_at is None or not stable(decline_snapshot,current):
                decline_stable_at,decline_snapshot = now,current
            elif now-decline_stable_at >= stable_seconds:
                declined = True
                passed = expected_decline
                reason = 'reported_unavailable_and_stayed' if passed else 'agent_declined_feasible_task'
        elif getattr(driver,'failure_reason',lambda:None)():
            reason = driver.failure_reason()
        else:
            decline_stable_at = None
            if goal.get('state') in ('needs_decision','failed','cancelled'):
                if blocked_at is None:
                    blocked_at = now
                elif now-blocked_at >= limits['blocked_grace']:
                    reason = 'cannot_continue_without_report'
            else:
                blocked_at = None
            reason = reason or watch.reason(elapsed,limits)
        if reason is None and success_at is None and stopping is None and decline_stable_at is None:
            reason = watch.reason(elapsed,limits)
        if reason:
            return {'status':'passed' if passed else 'failed', 'reason':reason,
                    'outcome':'appropriate_stop' if passed and declined else 'achieved' if passed else 'not_achieved',
                    'objective_achieved':passed and not declined, 'reported_stop':declined,
                    'decision_evidence':watch.decline,
                    'first_action_seconds':watch.first_action,'last_progress_seconds':round(watch.last_progress,3),
                    'budget':limits,
                    'elapsed_seconds':round(now-started,3), 'final':current,
                    'observed_milestones':sorted(observed & set(task['milestones'])),
                    'progress':inventory_progress(task,observed,initial,current),
                    'false_goal_done':false_done, 'metrics':data,
                    'time_to_goal_seconds':None if success_at is None else round(success_at-started,3),
                    'completion_observed':None if success_at is None else getattr(driver,'report_complete',lambda after:False)(success_wall),
                    'stop_latency_seconds':None if stable_at is None else round(stable_at-stopping,3)}
        await sleep(poll)


async def run(args, *, clock=time.monotonic):
    run_started = clock()
    deadline = run_started+args.run_seconds
    tasks = load_tasks()
    if args.list:
        for task in tasks:
            print(task['id'], task['prompt'])
        return 0
    from dotenv import load_dotenv
    load_dotenv(ROOT/'server'/'.env.benchmark')
    if args.mode in ('body','conversation'):
        load_dotenv(ROOT/'server'/'.env.shared')
        args.model_id = args.model_id or os.environ.get('CIEL_BENCH_MODEL_ID')
        if not args.model_id:
            raise ValueError('Set CIEL_BENCH_MODEL_ID or pass --model-id for execution evaluation')
    if args.task:
        selected = set(args.task)
        if selected - {t['id'] for t in tasks}:
            raise ValueError('Unknown task id')
        tasks = [t for t in tasks if t['id'] in selected]
    if args.task and any(args.mode not in task.get('modes',['body','conversation']) for task in tasks):
        raise ValueError('Selected task does not support this mode')
    tasks = [t for t in tasks if args.mode in t.get('modes',['body','conversation'])]
    if args.agent != 'ciel-task-bench':
        raise ValueError('Use the dedicated ciel-task-bench agent')
    if args.url != 'http://127.0.0.1:8773/mcp':
        raise ValueError('Use the dedicated benchmark MCP on port 8773')
    if args.mode == 'conversation' and args.backend == 'openai' and not args.allow_paid:
        raise ValueError('OpenAI conversation trials require --allow-paid; use local for free LLM trials')
    password = os.environ.get('CIEL_BENCH_RCON_PASSWORD')
    if not password:
        raise ValueError('Set CIEL_BENCH_RCON_PASSWORD in the environment')
    directory = Path(args.output)
    directory.mkdir(parents=True, exist_ok=False)
    plan = [(task,seed,repeat) for task in tasks for seed in args.seed for repeat in range(args.repeats)]
    manifest = {'format':2, 'policy':'spatial-v1' if any(t.get('stage1') for t in tasks) else POLICY_VERSION, 'completion':'running', 'created_at':datetime.now(timezone.utc).isoformat(), 'mode':args.mode,
                'backend':args.backend if args.mode == 'conversation' else 'local',
                'model_id':args.model_id,
                'minecraft_version':'1.21.11', 'seeds':args.seed, 'repeats':args.repeats,
                'planned_trials':len(plan),
                'distractors':distractor_configuration() if args.mode == 'conversation' else None,
                'limits':{'seconds_cap':args.seconds,'run_seconds':args.run_seconds,'failure_streak':args.failure_streak,
                          'setup_seconds':args.setup_seconds,'llm_calls':args.max_llm,'game_calls':args.max_calls,'report_grace':args.report_grace,
                          'tasks':{t['id']:budget(t,args.seconds) for t in tasks}},
                'task_ids':[t['id'] for t in tasks], 'note':'Seeds select arena layouts; no cross-trial learning.',
                **provenance()}
    if any(t.get('stage1')for t in tasks):
        manifest.update(gate='G2',gate_complete=False,report_review='pending'if args.mode=='conversation'else 'not_applicable',
                        scope='automatic_physical_checks; final gate also requires the complete matrix and report review')
    rows = []
    def skip_remaining(reason, completion):
        manifest.update(completion=completion,stop_reason=reason)
        for task,seed,repeat in plan[len(rows):]:
            rows.append({'task':task['id'],'seed':seed,'repeat':repeat,'status':'skipped','reason':reason})
    write_reports(directory,manifest,rows)
    rcon = world = None
    safe_release = True
    try:
        if (args.mode == 'body' or args.backend == 'local') and os.environ.get('CIEL_BENCH_LLM_SERVICE'):
            manifest['inference_server'] = await asyncio.to_thread(inference_server_info)
        rcon = Rcon(password)
        world = World(rcon)
        world.acquire()
        await wait_body_released(args.url,timeout=10)
        for task in tasks:
            for seed in args.seed:
                for repeat in range(args.repeats):
                    if task.get('stage1'):
                        task = stage1_fixture(task['stage1'], seed)
                    available = deadline-clock()-20  # Reserve bounded cleanup.
                    if available <= 0:
                        skip_remaining('run_time_budget','budget_exhausted')
                        return 1
                    trial = directory/f"{task['id']}-s{seed}-r{repeat}"
                    trial.mkdir()
                    trace = Trace(trial/'trace.jsonl')
                    driver = None
                    audit_id = None
                    result = {'task':task['id'],'seed':seed,'repeat':repeat,'budget':budget(task,args.seconds),
                              'fixture_sha256':hashlib.sha256(json.dumps(task,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
                              'expected_outcome':task.get('expected_outcome','achieve'),
                              **({'upstream':task['upstream']} if task.get('upstream') else {})}
                    try:
                        safe_release = False
                        async with asyncio.timeout(min(args.setup_seconds,available)):
                            fixture = await asyncio.to_thread(world.reset, task, seed)
                            items = task_items(task)
                            initial = await asyncio.to_thread(world.snapshot, items)
                            expected = {item:task['inventory'].get(item,0) for item in initial['inventory']}
                            if initial['inventory'] != expected:
                                raise RuntimeError('Fixture inventory was not reset correctly')
                            trace('fixture', fixture=fixture, initial=initial)
                            driver_type = BodyDriver if args.mode == 'body' else ConversationDriver
                            driver = driver_type(url=args.url,agent=args.agent,backend=args.backend,model_id=args.model_id,
                                                 debug_dir=args.debug_dir,trace=trace)
                            await driver.open()
                            # Startup preparation happens while binding, before the task clock starts.
                            bound = [e for e in trace.events if e['kind']=='game_result' and e.get('name')=='minecraft_bind_core']
                            if bound:
                                result['preparation'] = bound[-1].get('result',{}).get('prepared')
                            if task.get('navigation'):
                                await prepare_navigation(task, initial)
                            if task.get('spatial'):
                                await prepare_spatial(task, trace)
                            if task.get('pointing'):
                                await prepare_pointing(task, world, trace)
                            if task.get('spatial',{}).get('audit'):
                                audit_id = await asyncio.to_thread(audit.start, world)
                        result.update(fixture=fixture,initial=initial)
                        available = max(0.01,deadline-clock()-20)
                        limit = min(budget(task,args.seconds)['seconds'],available)
                        async with asyncio.timeout(min(available,limit+1)):
                            result.update(await evaluate(task,world,driver,trace,initial,seconds=limit,
                                                         max_llm=args.max_llm,max_calls=args.max_calls,report_grace=args.report_grace))
                        if result['reason']=='time_budget' and limit<budget(task,args.seconds)['seconds']:
                            result.update(status='skipped',reason='run_time_budget',outcome='unmeasured')
                    except TimeoutError:
                        global_timeout = deadline-clock() <= 20.5 and trace.phase=='execution'
                        result.update(status='skipped' if global_timeout else 'infrastructure_error',
                                      reason='run_time_budget' if global_timeout else 'setup_timeout' if trace.phase=='setup' else 'observation_timeout',
                                      metrics=metrics(trace.execution()))
                    except Exception as exc:
                        # Keep credentials and arbitrary network exception bodies out of reports.
                        result.update(status='infrastructure_error',reason=type(exc).__name__,metrics=metrics(trace.execution()),
                                      backend_errors=[e['event'] for e in trace.execution()
                                                      if e['kind']=='agent_event' and e['event'].get('kind')=='model_error'])
                        print(f"{task['id']}: infrastructure error ({type(exc).__name__})", file=sys.stderr)
                    finally:
                        trace.phase = 'cleanup'
                        if driver:
                            try:
                                await asyncio.wait_for(driver.close(),10)
                                await wait_body_released(args.url,timeout=10)
                                safe_release = True
                            except Exception as exc:
                                result.update(status='infrastructure_error',reason='cleanup_'+type(exc).__name__)
                        if audit_id:
                            try:
                                result['audit'] = await asyncio.to_thread(audit.finish,world,audit_id,task,trial)
                                violations=result['audit']['violations']
                                safety_failure=any(v['reason']!='objective_not_complete' for v in violations)
                                if (safety_failure or (violations and result.get('status')=='passed')) and result.get('status') not in ('skipped','infrastructure_error'):
                                    result['prior_reason']=result.get('reason')
                                    result.update(status='failed',reason='block_audit_violation',outcome='not_achieved',objective_achieved=False)
                            except Exception as exc:
                                safe_release = False
                                result.update(status='infrastructure_error',reason='audit_'+type(exc).__name__)
                    dummy_calls = [e['event'] for e in trace.execution() if e['kind'] == 'agent_event'
                                   and e['event'].get('kind') == 'benchmark_distractor_call']
                    result['distractor_calls'] = len(dummy_calls)
                    if dummy_calls and result['status'] not in ('infrastructure_error', 'skipped'):
                        result.update(status='failed', reason='distractor_selected', outcome='failed')
                    rows.append(result)
                    (trial/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                    write_reports(directory,manifest,rows)
                    print(task['id'],seed,repeat,result['status'],result['reason'])
                    if result['status'] == 'infrastructure_error':
                        skip_remaining('infrastructure_stop','infrastructure_error')
                        return 2  # Do not reset the next fixture if cleanup or observation failed.
                    if result['reason']=='run_time_budget':
                        skip_remaining('run_time_budget','budget_exhausted')
                        return 1
                    if args.failure_streak and len(rows)<len(plan) and len(rows)>=args.failure_streak and all(r['status']=='failed' for r in rows[-args.failure_streak:]):
                        skip_remaining('consecutive_failures','stopped_early')
                        return 1
        manifest['completion'] = 'complete'
    except Exception as exc:
        manifest.update(completion='infrastructure_error',run_error=type(exc).__name__)
        raise
    finally:
        try:
            if world and safe_release:
                world.release()
        except Exception as exc:
            manifest.update(completion='infrastructure_error',run_error='release_'+type(exc).__name__)
            raise
        finally:
            if rcon:
                rcon.close()
            manifest['run_elapsed_seconds'] = round(clock()-run_started,3)
            write_reports(directory,manifest,rows)
    return 0 if all(r['status'] == 'passed' for r in rows) else 1


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--list',action='store_true')
    ap.add_argument('--mode',choices=['body','conversation'],default='body')
    ap.add_argument('--backend',choices=['local','openai'],default='local')
    ap.add_argument('--model-id',help='Exact checkpoint / model label; must match agent CIEL_BENCH_MODEL_ID')
    ap.add_argument('--allow-paid',action='store_true')
    ap.add_argument('--agent',default='ciel-task-bench')
    ap.add_argument('--url',default='http://127.0.0.1:8773/mcp')
    ap.add_argument('--task',action='append')
    ap.add_argument('--seed',action='append',type=int)
    ap.add_argument('--repeats',type=int,default=1)
    ap.add_argument('--seconds',type=float,help='Optional stricter cap; never extends a task deadline')
    ap.add_argument('--run-seconds',type=float,default=600,help='Whole-run wall budget, including setup and cleanup (max 3600)')
    ap.add_argument('--setup-seconds',type=float,default=45)
    ap.add_argument('--failure-streak',type=int,default=3,help='Stop after consecutive failures; 0 disables this guard')
    ap.add_argument('--max-llm',type=int,default=30)
    ap.add_argument('--max-calls',type=int,default=80)
    ap.add_argument('--report-grace',type=float,default=5,help='Observe completion/reply after the item condition is verified')
    ap.add_argument('--debug-dir',default=str(Path(__file__).parent/'data'/'debug'))
    ap.add_argument('--output',default=str(Path(__file__).parent/'data'/'results'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
    return ap


def main(*, native_exit=False):
    ap = parser()
    args = ap.parse_args()
    args.seed = args.seed or [11]
    import math
    values = [args.run_seconds,args.setup_seconds,args.report_grace]+([args.seconds] if args.seconds is not None else [])
    if any(not math.isfinite(v) for v in values) or min(args.repeats,args.run_seconds,args.setup_seconds,args.max_calls) <= 0 or (args.seconds is not None and args.seconds<=0) or args.run_seconds>3600 or min(args.max_llm,args.report_grace,args.failure_streak) < 0 or len(set(args.seed)) != len(args.seed):
        ap.error('Budgets and repeats must be positive, max-llm nonnegative, and seeds unique')
    try:
        code = asyncio.run(run(args))
    except (ValueError,RuntimeError,ConnectionError,OSError) as exc:
        print(f'Benchmark could not run: {type(exc).__name__}: {exc}',file=sys.stderr)
        code = 2
    if native_exit and args.mode == 'conversation':
        # run() has already disconnected rooms, closed clients, released the
        # world lease (or recorded its failure) and closed all report files.
        # Avoid LiveKit's interpreter-finalization race after that cleanup:
        # https://github.com/livekit/python-sdks/issues/833
        # Keep the real result code, including task / infrastructure failures.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    return code


if __name__ == '__main__':
    raise SystemExit(main(native_exit=True))
