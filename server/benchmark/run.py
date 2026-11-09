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

from .drivers import BodyDriver, ConversationDriver, wait_body_released
from .report import metrics, write_reports
from .world import Rcon, World, achieved, stable

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
    return suite['tasks']


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
    for base in ['agent/config','minecraft/src','benchmark','local-llm']:
        files += [p for p in (ROOT/'server'/base).rglob('*') if p.is_file() and
                  p.suffix in ('.py','.js','.md','.json','.toml') and 'data' not in p.relative_to(ROOT/'server'/base).parts
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
    return any(e.get('event',e).get('kind') == 'game_call' and e.get('event',e).get('name') in MOVING_TOOLS for e in events)


async def evaluate(task, world, driver, trace, initial, *, seconds, max_llm, max_calls,
                   poll=0.5, stop_grace=180, stable_seconds=10, report_grace=30, clock=time.monotonic, sleep=asyncio.sleep):
    started = clock()
    trace.phase, trace.started_at = 'execution', time.time()
    await driver.submit(task)
    stopping = stable_at = None
    stable_snapshot = None
    ack_index = None
    observed = set()
    false_done = False
    success_at = success_wall = None
    while True:
        for e in driver.events():
            trace('agent_event', event=e)
            if e.get('kind') == 'model_error':
                raise RuntimeError('Inference backend failed; inspect the trial model_error event')
        current = await asyncio.to_thread(world.snapshot, task['milestones'] + [task['item']])
        now = clock()
        trace('observation', state=current, elapsed=round(now-started,3))
        observed.update(item for item, count in current['inventory'].items()
                        if count > initial['inventory'].get(item,0))
        data = metrics(trace.execution())
        goal = driver.goal_state.get('goal') or {}
        done = achieved(task, initial, current)
        if done and success_at is None and not task.get('stop_after_gain') and now-started < seconds:
            success_at, success_wall = now, time.time()
            trace('goal_condition_verified',state=current,elapsed=round(now-started,3))
        if goal.get('status') == 'done' and not done and success_at is None and not task.get('stop_after_gain'):
            false_done = True
        reason = None
        passed = False
        if data['llm_calls'] > max_llm or data['game_calls'] > max_calls:
            reason = 'call_budget'
        elif current['health'] <= 0 or current.get('deaths',0) > initial.get('deaths',0):
            reason = 'died'
        elif now-started >= seconds:
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
                elif now-stopping >= stop_grace:
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
        elif getattr(driver,'failure_reason',lambda:None)():
            reason = driver.failure_reason()
        if reason:
            return {'status':'passed' if passed else 'failed', 'reason':reason,
                    'elapsed_seconds':round(now-started,3), 'final':current,
                    'observed_milestones':sorted(observed & set(task['milestones'])),
                    'false_goal_done':false_done, 'metrics':data,
                    'time_to_goal_seconds':None if success_at is None else round(success_at-started,3),
                    'completion_observed':None if success_at is None else getattr(driver,'report_complete',lambda after:False)(success_wall),
                    'stop_latency_seconds':None if stable_at is None else round(stable_at-stopping,3)}
        await sleep(poll)


async def run(args):
    tasks = load_tasks()
    if args.list:
        for task in tasks:
            print(task['id'], task['prompt'])
        return 0
    from dotenv import load_dotenv
    load_dotenv(ROOT/'server'/'.env.benchmark')
    if args.mode == 'conversation':
        load_dotenv(ROOT/'server'/'agent'/'.env')
        args.model_id = args.model_id or os.environ.get('CIEL_BENCH_MODEL_ID')
        if not args.model_id:
            raise ValueError('Set CIEL_BENCH_MODEL_ID or pass --model-id for conversation evaluation')
    if args.task:
        selected = set(args.task)
        if selected - {t['id'] for t in tasks}:
            raise ValueError('Unknown task id')
        tasks = [t for t in tasks if t['id'] in selected]
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
    manifest = {'format':1, 'completion':'running', 'created_at':datetime.now(timezone.utc).isoformat(), 'mode':args.mode,
                'backend':args.backend if args.mode == 'conversation' else 'none',
                'model_id':args.model_id if args.mode == 'conversation' else None,
                'minecraft_version':'1.21.11', 'seeds':args.seed, 'repeats':args.repeats,
                'limits':{'seconds':args.seconds,'llm_calls':args.max_llm,'game_calls':args.max_calls,'report_grace':args.report_grace},
                'task_ids':[t['id'] for t in tasks], 'note':'Seeds select arena layouts; no cross-trial learning.',
                **provenance()}
    rows = []
    write_reports(directory,manifest,rows)
    rcon = world = None
    safe_release = True
    try:
        rcon = Rcon(password)
        world = World(rcon)
        world.acquire()
        await wait_body_released(args.url)
        for task in tasks:
            for seed in args.seed:
                for repeat in range(args.repeats):
                    trial = directory/f"{task['id']}-s{seed}-r{repeat}"
                    trial.mkdir()
                    trace = Trace(trial/'trace.jsonl')
                    driver = None
                    result = {'task':task['id'],'seed':seed,'repeat':repeat}
                    try:
                        fixture = await asyncio.to_thread(world.reset, task, seed)
                        items = task['milestones'] + [task['item']]
                        initial = await asyncio.to_thread(world.snapshot, items)
                        expected = {item:task['inventory'].get(item,0) for item in initial['inventory']}
                        if initial['inventory'] != expected:
                            raise RuntimeError('Fixture inventory was not reset correctly')
                        trace('fixture', fixture=fixture, initial=initial)
                        driver_type = BodyDriver if args.mode == 'body' else ConversationDriver
                        driver = driver_type(url=args.url,agent=args.agent,backend=args.backend,model_id=args.model_id,
                                             debug_dir=args.debug_dir,trace=trace)
                        safe_release = False
                        await driver.open()
                        result.update(fixture=fixture,initial=initial)
                        result.update(await evaluate(task,world,driver,trace,initial,seconds=args.seconds,
                                                     max_llm=args.max_llm,max_calls=args.max_calls,report_grace=args.report_grace))
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
                                await asyncio.wait_for(driver.close(),30)
                                await wait_body_released(args.url)
                                safe_release = True
                            except Exception as exc:
                                result.update(status='infrastructure_error',reason='cleanup_'+type(exc).__name__)
                    rows.append(result)
                    (trial/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                    write_reports(directory,manifest,rows)
                    print(task['id'],seed,repeat,result['status'],result['reason'])
                    if result['status'] == 'infrastructure_error':
                        manifest['completion'] = 'infrastructure_error'
                        return 2  # Do not reset the next fixture if cleanup or observation failed.
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
    ap.add_argument('--repeats',type=int,default=3)
    ap.add_argument('--seconds',type=float,default=900)
    ap.add_argument('--max-llm',type=int,default=30)
    ap.add_argument('--max-calls',type=int,default=80)
    ap.add_argument('--report-grace',type=float,default=30,help='Observe completion/reply after the item condition is verified')
    ap.add_argument('--debug-dir',default=str(Path(__file__).parent/'data'/'debug'))
    ap.add_argument('--output',default=str(Path(__file__).parent/'data'/'results'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
    return ap


def main():
    ap = parser()
    args = ap.parse_args()
    args.seed = args.seed or [11,29,47]
    if min(args.repeats,args.seconds,args.max_calls) <= 0 or min(args.max_llm,args.report_grace) < 0 or len(set(args.seed)) != len(args.seed):
        ap.error('Budgets and repeats must be positive, max-llm nonnegative, and seeds unique')
    try:
        return asyncio.run(run(args))
    except (ValueError,RuntimeError,ConnectionError,OSError) as exc:
        print(f'Benchmark could not run: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
