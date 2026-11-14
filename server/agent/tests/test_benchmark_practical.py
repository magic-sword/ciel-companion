"""Practical stop conditions with a simulated clock, not minute-long sleeps."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from benchmark.policy import Progress, budget
from benchmark.run import Trace, evaluate, load_tasks, parser, run
from benchmark.report import summarize
from benchmark.world import World, MARKER

def state(logs=0,x=0):
    return {'inventory':{'oak_log':logs,'stone_pickaxe':0},'position':[x,64,0],'health':20,'deaths':0}

class Driver:
    def __init__(self,events=(),goal=None):
        self.rows=list(events)
        self.goal_state={'v':2, 'type':'goal.state', 'task':goal}
    async def submit(self,task):
        pass
    async def stop(self,task):
        pass
    def events(self):
        rows,self.rows=self.rows,[]
        return [dict(row,t=time.time()) for row in rows]
    def stopped(self):
        return False

class PracticalTest(unittest.IsolatedAsyncioTestCase):
    def test_body_core_events_have_timestamps_during_execution(self):
        from benchmark.drivers import BodyDriver
        with tempfile.TemporaryDirectory() as directory:
            trace=Trace(Path(directory)/'trace.jsonl')
            trace.started_at=time.time()-1
            trace.phase='execution'
            driver=BodyDriver('unused',trace)
            driver.record_core('core_request',id='request')
            driver.record_core('model_response',id='request',seconds=0.2)
            self.assertEqual([r['event']['kind'] for r in trace.execution()],['model_request','model_response'])
            self.assertTrue(all(r['event']['t']>=trace.started_at for r in trace.execution()))

    def test_natural_goal_handoff_and_queries_are_not_physical_actions(self):
        watch=Progress(state(),load_tasks()[0])
        watch.event({'kind':'work_action','id':'goal','skill':'pursue','arguments':{'request':'gather logs'}},2)
        watch.event({'kind':'work_activity','stage':'thinking'},4)
        watch.event({'kind':'work_activity','stage':'executing','command':'!getCraftingPlan'},5)
        self.assertIsNone(watch.first_action)
        self.assertEqual(watch.reason(30,budget(load_tasks()[0])),'first_action_timeout')
        watch.event({'kind':'work_activity','stage':'executing','command':'!collectBlocks'},6)
        self.assertEqual(watch.first_action,6)
        self.assertIn(('call','goal'),watch.pending)
        watch.event({'kind':'work_action_result','id':'goal','result':{'ok':True}},7)
        self.assertNotIn(('call','goal'),watch.pending)

    def test_pointing_action_counts_as_first_action_without_extending_progress(self):
        watch=Progress(state(),load_tasks()[0])
        watch.event({'kind':'game_call','id':'p','name':'minecraft_pointed_action',
                     'arguments':{'selection_id':'selected','action':'floor'}},2)
        self.assertEqual(watch.first_action,2)
        self.assertEqual(watch.reason(31,budget(load_tasks()[0])),'no_progress')

    async def evaluate(self,task=None,driver=None,states=None,**options):
        now=[0]
        async def sleep(seconds):
            now[0]+=seconds
        task=copy.deepcopy(task or load_tasks()[0])
        values=iter(states or [state()])
        last=[state()]
        def snapshot(items):
            last[0]=next(values,last[0])
            return last[0]
        world=MagicMock(snapshot=snapshot)
        with tempfile.TemporaryDirectory() as folder:
            trace=Trace(Path(folder)/'trace.jsonl')
            return await evaluate(task,world,driver or Driver(),trace,state(),seconds=options.pop('seconds',None),
                                  max_llm=100,max_calls=100,poll=1,clock=lambda:now[0],sleep=sleep,**options)

    async def test_no_action_stops_in_30_seconds_including_stop_task(self):
        for task in (load_tasks()[0],next(t for t in load_tasks() if t['id']=='stop_collecting')):
            result=await self.evaluate(task)
            self.assertEqual((result['reason'],result['elapsed_seconds']),('first_action_timeout',30))

    async def test_action_without_world_progress_does_not_extend_wait(self):
        events=[{'kind':'game_call','id':'a','name':'minecraft_find_blocks','arguments':{'block':'stone'}}]
        result=await self.evaluate(driver=Driver(events))
        self.assertEqual((result['reason'],result['elapsed_seconds']),('no_progress',30))

    async def test_blocked_goal_gets_bounded_time_to_report(self):
        result=await self.evaluate(driver=Driver(goal={'state':'needs_decision'}))
        self.assertEqual((result['reason'],result['elapsed_seconds']),('cannot_continue_without_report',10))

    async def test_false_goal_completion_ends_immediately(self):
        result=await self.evaluate(driver=Driver(goal={'state':'succeeded'}))
        self.assertEqual((result['reason'],result['elapsed_seconds']),('false_completion',0))

    async def test_correct_unavailable_report_is_not_item_success(self):
        task=next(t for t in load_tasks() if t['id']=='stone_pickaxe_unavailable')
        reply={'kind':'item','role':'assistant','text':'原木がありません。石のつるはしは作れません。作業を止めます。','interrupted':False}
        result=await self.evaluate(task,Driver([reply]))
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['outcome'],'appropriate_stop')
        self.assertFalse(result['objective_achieved'])
        self.assertEqual(result['elapsed_seconds'],5)
        result=await self.evaluate(load_tasks()[2],Driver([reply]))
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['reason'],'agent_declined_feasible_task')

    async def test_report_does_not_pass_while_a_body_task_is_pending(self):
        task=next(t for t in load_tasks() if t['id']=='stone_pickaxe_unavailable')
        events=[{'kind':'game_call','id':'a','name':'minecraft_find_blocks','arguments':{'block':'oak_log'}},
                {'kind':'game_result','id':'a','result':{'status':'accepted','session':'s','task':1}},
                {'kind':'item','role':'assistant','text':'原木がありません。作れません。'}]
        result=await self.evaluate(task,Driver(events))
        self.assertEqual(result['reason'],'no_progress')

    async def test_interrupted_and_hypothetical_reports_do_not_pass(self):
        task=next(t for t in load_tasks() if t['id']=='stone_pickaxe_unavailable')
        for text,interrupted in [('原木がありません。作れません。',True),('もし原木がない場合は作れません。',False)]:
            result=await self.evaluate(task,Driver([{'kind':'item','role':'assistant','text':text,'interrupted':interrupted}]))
            self.assertEqual(result['status'],'failed')

    async def test_stop_stability_can_finish_after_ack_deadline(self):
        class Ack(Driver):
            calls=0
            def stopped(self):
                self.calls+=1
                return self.calls>=3
        result=await self.evaluate(next(t for t in load_tasks() if t['id']=='stop_collecting'),Ack(),states=[state(1)])
        self.assertEqual(result['reason'],'stopped_and_stayed')
        self.assertEqual(result['stop_latency_seconds'],3)
        self.assertEqual(result['elapsed_seconds'],8)

class ProgressTest(unittest.TestCase):
    def test_unconfirmed_cancellation_is_not_idle_for_decline(self):
        watch = Progress(state(), load_tasks()[0])
        for phase in ('accepted', 'running', 'cancelling'):
            self.assertFalse(watch.idle({'state':phase}))
        self.assertTrue(watch.idle({'state':'cancelled'}))

    def test_unavailability_cannot_be_asserted_for_an_available_resource(self):
        task=copy.deepcopy(next(t for t in load_tasks() if t['id']=='stone_pickaxe_unavailable'))
        task['item']='sand'
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'tasks.json'
            p.write_text(json.dumps({'version':1,'tasks':[task]}),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'oracle'):
                load_tasks(p)

    def test_desert_fixture_contains_no_wood_or_starting_supplies(self):
        rcon=MagicMock()
        rcon.command.return_value='"'+MARKER+'"'
        world=World(rcon)
        world.lease='test'
        world.scalar=lambda *a,**kw:1
        task=next(t for t in load_tasks() if t['id']=='stone_pickaxe_unavailable')
        fixture=world.reset(task,11)
        commands=[c.args[0] for c in rcon.command.call_args_list]
        self.assertEqual(fixture['trees'],[])
        self.assertTrue(any(c.endswith('minecraft:sand') for c in commands))
        self.assertFalse(any('minecraft:oak_log' in c or c.startswith('give ') for c in commands))

    def test_walking_loops_and_more_requests_are_not_new_progress(self):
        watch=Progress(state(),load_tasks()[0])
        watch.observe(state(x=3),1)
        watch.observe(state(),20)
        watch.observe(state(x=3),29)
        self.assertEqual(watch.last_progress,1)
        self.assertEqual(watch.reason(31,budget(load_tasks()[0])),'first_action_timeout')

    def test_regathering_consumed_items_is_progress_but_consumption_is_not(self):
        def held(position=0, **inventory):
            return {'inventory':{'oak_log':0,'oak_planks':0,**inventory},'position':[position,64,0],'health':20}
        watch=Progress(held(),load_tasks()[0])
        watch.observe(held(oak_log=2),5)           # gathered
        watch.observe(held(oak_planks=8),10)       # crafted: planks are new
        watch.observe(held(),20)                   # consumed: not progress
        self.assertEqual(watch.last_progress,10)
        watch.observe(held(oak_log=1),25)          # the same log count as before, re-gathered
        self.assertEqual(watch.last_progress,25)
        watch.observe(held(oak_log=1),40)          # holding still is not progress
        self.assertEqual(watch.last_progress,25)

    def test_repeated_async_failure_counts_snapshot_once(self):
        watch=Progress(state(),load_tasks()[0])
        for n in range(2):
            for e in [{'kind':'game_call','id':str(n),'name':'minecraft_find_blocks','arguments':{'block':'oak_log'}},
                      {'kind':'game_result','id':str(n),'result':{'status':'accepted','session':'s','task':n}},
                      {'kind':'game_task_result','id':'s:'+str(n),'ok':False,'reason':'not_found'}]:
                watch.event(e,n)
            watch.event(e,n)
        self.assertEqual(watch.reason(2,budget(load_tasks()[0])),'repeated_failure')

    def test_large_cli_cap_never_extends_practical_deadline(self):
        self.assertEqual(budget(load_tasks()[2],900)['seconds'],120)
        self.assertEqual(budget(load_tasks()[2],40)['seconds'],40)
        args=parser().parse_args([])
        self.assertEqual(args.repeats,1)
        self.assertEqual(args.run_seconds,600)

    def test_skips_and_appropriate_stops_have_separate_denominators(self):
        rows=[{'task':'a','status':'passed','outcome':'appropriate_stop','objective_achieved':False,'reported_stop':True},
              {'task':'a','status':'failed'},{'task':'a','status':'skipped'}]
        data=summarize(rows)['a']
        self.assertEqual(data['success_rate'],0.5)
        self.assertEqual(data['objectives_achieved'],0)
        self.assertEqual(data['appropriate_stops'],1)
        self.assertEqual(data['skipped'],1)

class RunBudgetTest(unittest.IsolatedAsyncioTestCase):
    async def check_run(self,run_seconds,streak,tasks=('gather_logs',),env=None):
        now=[0]
        with tempfile.TemporaryDirectory() as folder:
            args=parser().parse_args(['--mode','body','--model-id','test-model',*[a for t in tasks for a in ('--task',t)],'--seed','11','--repeats','5',
                                      '--run-seconds',str(run_seconds),'--failure-streak',str(streak),'--output',folder+'/result'])
            async def assess(*a,**kw):
                now[0]+=kw['seconds']
                return {'status':'failed','reason':'time_budget','metrics':{}}
            driver=MagicMock(open=AsyncMock(),close=AsyncMock())
            world=MagicMock(snapshot=lambda items:{'inventory':{item:0 for item in items},'position':[0,64,0],'health':20},
                            reset=lambda task,seed:{'layout_seed':seed})
            with patch.dict(os.environ,{'CIEL_BENCH_RCON_PASSWORD':'test',**(env or {})}),patch('benchmark.run.Rcon'), \
                    patch('benchmark.run.World',return_value=world),patch('benchmark.run.BodyDriver',return_value=driver), \
                    patch('benchmark.run.wait_body_released',new=AsyncMock()),patch('benchmark.run.evaluate',new=assess), \
                    patch('benchmark.run.provenance',return_value={}):
                code=await run(args,clock=lambda:now[0])
            data=json.loads((Path(folder)/'result/report.json').read_text(encoding='utf-8'))
            return code,data

    async def test_whole_run_budget_marks_unstarted_trials_skipped(self):
        code,data=await self.check_run(130,0)
        self.assertEqual(code,1)
        self.assertEqual(data['manifest']['completion'],'budget_exhausted')
        self.assertEqual(data['manifest']['run_elapsed_seconds'],110)
        self.assertEqual(sum(r['status']=='skipped' for r in data['trials']),4)

    async def test_failure_circuit_breaker_prevents_more_repetitions(self):
        code,data=await self.check_run(600,3)
        self.assertEqual(code,1)
        self.assertEqual(data['manifest']['completion'],'stopped_early')
        self.assertEqual(sum(r['status']=='skipped' for r in data['trials']),2)

    async def test_long_tasks_record_their_policy_limits_and_the_body_variant(self):
        code,data=await self.check_run(3600,1,('mc_long_iron_pickaxe',),{'CIEL_BENCH_BLOCKED_ACTIONS':'!obtainItem'})
        manifest=data['manifest']
        self.assertEqual((manifest['policy'],manifest['body_blocked_actions']),('long-horizon-v1',['!obtainItem']))
        self.assertEqual((manifest['limits']['llm_calls'],manifest['limits']['game_calls']),(80,200))
        self.assertEqual(manifest['limits']['tasks']['mc_long_iron_pickaxe']['seconds'],480)
        code,data=await self.check_run(600,1)
        self.assertEqual((data['manifest']['policy'],data['manifest']['body_blocked_actions'],data['manifest']['limits']['llm_calls']),
                         ('practical-v1',[],30))

    async def test_long_and_practical_tasks_never_share_a_run(self):
        with self.assertRaisesRegex(ValueError,'separately'):
            await self.check_run(600,1,('gather_logs','mc_long_shield'))

    async def test_long_tasks_are_left_out_unless_named(self):
        tasks=[]
        world=MagicMock(snapshot=lambda items:{'inventory':{i:0 for i in items},'position':[0,64,0],'health':20},
                        reset=lambda task,seed:tasks.append(task['id']) or {'layout_seed':seed})
        async def assess(*a,**kw):
            return {'status':'passed','reason':'achieved','metrics':{}}
        with tempfile.TemporaryDirectory() as folder:
            args=parser().parse_args(['--mode','body','--model-id','m','--seed','11','--output',folder+'/result','--run-seconds','3600'])
            with patch.dict(os.environ,{'CIEL_BENCH_RCON_PASSWORD':'test'}),patch('benchmark.run.Rcon'),                     patch('benchmark.run.World',return_value=world),patch('benchmark.run.BodyDriver',return_value=MagicMock(open=AsyncMock(),close=AsyncMock())),                     patch('benchmark.run.wait_body_released',new=AsyncMock()),patch('benchmark.run.evaluate',new=assess),                     patch('benchmark.run.provenance',return_value={}):
                await run(args)
        self.assertTrue(tasks)
        self.assertFalse([t for t in tasks if t.startswith('mc_long_')])

if __name__=='__main__':
    unittest.main()
