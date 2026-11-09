"""Offline checks of benchmark scoring, reset guards and wire framing."""
import asyncio
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmark.run import Trace, evaluate, load_tasks, stop_ack, provenance
from benchmark.report import metrics, summarize, write_reports
from benchmark.world import MARKER, Rcon, World, achieved


class DisplayContractTest(unittest.TestCase):
    def test_old_display_is_an_environment_error_not_idle(self):
        from benchmark.drivers import ConversationDriver
        driver = ConversationDriver('agent', 'local', 'model', '.', lambda *a, **kw: None)
        driver._receive_goal_state({'v':1, 'type':'goal.state', 'goal':{'status':'done'}})
        with self.assertRaisesRegex(RuntimeError, 'protocol mismatch'):
            driver.events()

    def test_new_display_preserves_the_service_state(self):
        from benchmark.drivers import ConversationDriver
        driver = ConversationDriver('agent', 'local', 'model', '.', lambda *a, **kw: None)
        driver._receive_goal_state({'v':2, 'type':'goal.state', 'has_task':True, 'confirmed':True,
            'stream_id':'stream', 'revision':1, 'valid_for_ms':10000,
            'task':{'state':'cancelled', 'session':'server', 'task_id':'task', 'revision':1}})
        self.assertTrue(driver.stopped())


class CliExitTest(unittest.TestCase):
    def test_conversation_cli_exits_after_cleanup_with_the_actual_result_code(self):
        import benchmark.run as runner
        class ProcessExit(Exception):
            pass
        for code in (0,1,2):
            completed = []
            async def finished(args):
                completed.append('reports and cleanup finished')
                return code
            def exit_process(actual):
                self.assertEqual(completed,['reports and cleanup finished'])
                self.assertEqual(actual,code)
                raise ProcessExit()
            with self.subTest(code=code), patch.object(sys,'argv',['benchmark','--mode','conversation']), \
                    patch.object(runner,'run',finished), patch.object(runner.os,'_exit',side_effect=exit_process), \
                    self.assertRaises(ProcessExit):
                runner.main(native_exit=True)

    def test_conversation_cli_preserves_infrastructure_exception_exit(self):
        import benchmark.run as runner
        async def broken(args):
            raise RuntimeError('cleanup failed')
        with patch.object(sys,'argv',['benchmark','--mode','conversation']), \
                patch.object(runner,'run',broken), patch.object(runner.os,'_exit') as exit_process:
            self.assertEqual(runner.main(native_exit=True),2)
        exit_process.assert_called_once_with(2)


def state(count=0, x=0):
    return {'inventory':{'oak_log':count},'position':[x,64,0],'health':20}


class FakeWorld:
    def __init__(self, *states):
        self.states = iter(states)
        self.last = state()

    def snapshot(self, items):
        self.last = next(self.states,self.last)
        return copy.deepcopy(self.last)


class FakeDriver:
    def __init__(self, *, stopped=False, done=False, budget=False):
        self.goal_state = {'v':2, 'type':'goal.state', 'task':{'state':'succeeded' if done else 'running'}}
        self.ack, self.budget = stopped, budget
        self.sent = []
        self.rows = []

    async def submit(self, task):
        self.sent.append(task['prompt'])
        if self.budget:
            self.rows = [{'kind':'model_request','t':time.time()+1} for _ in range(3)]

    async def stop(self, task):
        self.sent.append('STOP')

    def events(self):
        rows,self.rows = self.rows,[]
        return rows

    def stopped(self):
        return self.ack


class EvaluationTest(unittest.IsolatedAsyncioTestCase):
    async def test_backend_error_is_not_counted_as_agent_task_failure(self):
        class BrokenDriver(FakeDriver):
            def events(self):
                return [{'kind':'model_error','error':'APIStatusError','t':time.time()}]
        with self.assertRaisesRegex(RuntimeError,'Inference backend failed'):
            await self.evaluate(FakeWorld(state()),BrokenDriver())

    async def evaluate(self, world, driver, task=None, **kw):
        task = task or load_tasks()[0]
        with tempfile.TemporaryDirectory() as tmp:
            trace = Trace(Path(tmp)/'trace.jsonl')
            now = [0]

            async def sleep(seconds):
                now[0] += max(seconds,0.1)

            result = await evaluate(task,world,driver,trace,state(),seconds=kw.pop('seconds',2),max_llm=2,max_calls=20,
                                    poll=0.1,stable_seconds=0.2,stop_grace=0.8,report_grace=kw.pop('report_grace',0),
                                    clock=lambda:now[0],sleep=sleep,**kw)
            return result,trace.events

    async def test_actual_inventory_is_sufficient_without_agent_claim(self):
        result,_ = await self.evaluate(FakeWorld(state(8)),FakeDriver())
        self.assertEqual(result['status'],'passed')

    async def test_completion_is_observed_after_the_item_condition(self):
        class ReportingDriver(FakeDriver):
            polls = 0
            def events(self):
                self.polls += 1
                return []
            def report_complete(self, after):
                return self.polls >= 3
        result,_ = await self.evaluate(FakeWorld(state(8)),ReportingDriver(),report_grace=1)
        self.assertEqual(result['time_to_goal_seconds'],0)
        self.assertTrue(result['completion_observed'])
        self.assertGreaterEqual(result['elapsed_seconds'],0.2)

    async def test_agent_done_cannot_override_missing_items(self):
        result,_ = await self.evaluate(FakeWorld(state()),FakeDriver(done=True))
        self.assertEqual(result['status'],'failed')
        self.assertTrue(result['false_goal_done'])

    async def test_over_budget_cannot_pass_even_if_target_exists(self):
        result,_ = await self.evaluate(FakeWorld(state(8)),FakeDriver(budget=True))
        self.assertEqual(result['reason'],'call_budget')

    async def test_item_first_observed_after_deadline_does_not_pass(self):
        result,_ = await self.evaluate(FakeWorld(state(),state(8)),FakeDriver(),seconds=0.1)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['reason'],'time_budget')

    async def test_stop_requires_ack_and_independent_stability(self):
        task = load_tasks()[-1]
        driver = FakeDriver(stopped=True)
        result,_ = await self.evaluate(FakeWorld(state(1)),driver,task)
        self.assertEqual(result['status'],'passed')
        self.assertIn('STOP',driver.sent)
        result,_ = await self.evaluate(FakeWorld(state(1)),FakeDriver(),task)
        self.assertEqual(result['reason'],'did_not_stop')

    async def test_resume_after_stop_fails(self):
        result,_ = await self.evaluate(FakeWorld(state(1),state(1),state(2)),FakeDriver(stopped=True),load_tasks()[-1])
        self.assertEqual(result['reason'],'resumed_after_stop')

    async def test_missed_stop_trigger_is_not_a_success(self):
        with self.assertRaisesRegex(RuntimeError,'trigger missed'):
            await self.evaluate(FakeWorld(state(64)),FakeDriver(stopped=True),load_tasks()[-1])

    async def test_disconnection_is_not_scored_as_zero_inventory(self):
        class BrokenWorld:
            def snapshot(self, items):
                raise ConnectionError('disconnected')
        with self.assertRaises(ConnectionError):
            await self.evaluate(BrokenWorld(),FakeDriver())


class ReportTest(unittest.TestCase):
    def test_async_task_failure_is_counted_once_separately_from_start_call(self):
        data = metrics([{'kind':'game_result','result':{'status':'started'}},
                        {'kind':'game_task_result','id':'task1','ok':False,'failed':False,'snapshot':True},
                        {'kind':'game_task_result','id':'task1','ok':False,'failed':True,'reason':'not_found'}])
        self.assertEqual(data['failed_game_calls'],0)
        self.assertEqual(data['failed_game_tasks'],1)
        self.assertEqual(data['task_failure_reasons'],{'not_found':1})

    def test_provenance_is_available_in_a_container_without_git(self):
        with patch('benchmark.run.subprocess.run',side_effect=FileNotFoundError):
            data = provenance()
        self.assertEqual(len(data['source_sha256']),64)
        self.assertEqual(len(data['suite_sha256']),64)

    def test_dispatch_contract_rejects_wrong_backend_model_and_version(self):
        import benchmark_contract as contract
        trial = 'a'*32
        raw = contract.metadata('local','checkpoint',trial)
        self.assertEqual(contract.validate(raw,'local','checkpoint'),trial)
        for backend,model in [('openai','checkpoint'),('local','other')]:
            with self.assertRaises(ValueError):
                contract.validate(raw,backend,model)
        for change in [{'v':0},{'v':True},{'trial':'wrong'},{'extra':'unsupported'}]:
            data = json.loads(raw)
            data.update(change)
            with self.assertRaises(ValueError):
                contract.validate(json.dumps(data),'local','checkpoint')
        with self.assertRaises(ValueError):
            contract.validate('','local','checkpoint')

    def test_infrastructure_errors_do_not_improve_success_rate(self):
        rows = [{'task':'a','status':s} for s in ('passed','failed','infrastructure_error')]
        self.assertEqual(summarize(rows)['a']['success_rate'],0.5)
        rows = [{'task':'a','status':'infrastructure_error'}]
        self.assertIsNone(summarize(rows)['a']['success_rate'])
        with tempfile.TemporaryDirectory() as tmp:
            write_reports(Path(tmp),{'mode':'body','backend':'none'},rows)
            self.assertIn('N/A',(Path(tmp)/'report.md').read_text())
            self.assertEqual(json.loads((Path(tmp)/'report.json').read_text())['trials'],rows)

    def test_metrics_count_calls_once_and_keep_unknown_cost_unknown(self):
        data = metrics([{'kind':'agent_event','event':{'kind':'model_request'}},
                        {'kind':'agent_event','event':{'kind':'game_call','name':'minecraft_goal_repair'}},
                        {'kind':'agent_event','event':{'kind':'game_result','result':{'ok':False,'reason':'not_found'}}}])
        self.assertEqual(data['llm_calls'],1)
        self.assertEqual(data['game_calls'],1)
        self.assertEqual(data['repair_calls'],1)
        self.assertEqual(data['failure_reasons'],{'not_found':1})
        self.assertIsNone(data['usd'])

    def test_failed_stop_tool_is_not_an_ack(self):
        driver = FakeDriver()
        events = [{'kind':'agent_event','event':{'kind':'tool','name':'stop_goal','output':'{"status":"unavailable"}'}}]
        self.assertFalse(stop_ack(driver,events))


class RecordingRcon:
    def __init__(self, marker=True):
        self.commands,self.marker = [],marker

    def command(self, command):
        self.commands.append(command)
        if command == 'data get storage ciel_benchmark:meta suite':
            return 'meta has: "'+MARKER+'"' if self.marker else 'Nothing found'
        return 'ok'


class FixtureTest(unittest.TestCase):
    def test_production_world_is_rejected_before_mutation(self):
        rcon = RecordingRcon(False)
        with self.assertRaisesRegex(RuntimeError,'Not a marked'):
            World(rcon).reset(load_tasks()[0],11)
        self.assertEqual(rcon.commands,['data get storage ciel_benchmark:meta suite'])

    def test_reset_requires_lease(self):
        rcon = RecordingRcon()
        with self.assertRaisesRegex(RuntimeError,'lease'):
            World(rcon).reset(load_tasks()[0],11)
        self.assertEqual(len(rcon.commands),1)

    def test_same_seed_restores_same_fixture_and_each_fill_is_bounded(self):
        layouts = []
        for seed in (11,11,29,47):
            rcon = RecordingRcon()
            world = World(rcon)
            world.lease = 'test'
            world.scalar = lambda *a,**kw:1
            fixture = world.reset(load_tasks()[0],seed)
            layouts.append(fixture['trees'])
            self.assertIn('clear Ciel_Debug',rcon.commands)
            for command in rcon.commands:
                if command.startswith('fill '):
                    xyz = list(map(int,command.split()[1:7]))
                    size = 1
                    for i in range(3):
                        size *= abs(xyz[i+3]-xyz[i])+1
                    self.assertLessEqual(size,32768)
        self.assertEqual(layouts[0],layouts[1])
        self.assertEqual(len({json.dumps(x) for x in layouts}),3)

    def test_query_parse_error_does_not_return_zero(self):
        with self.assertRaises(RuntimeError):
            World(RecordingRcon()).snapshot(['oak_log'])

    def test_initial_items_do_not_count_as_newly_obtained(self):
        self.assertFalse(achieved(load_tasks()[0],state(8),state(8)))


def packet(rid,kind,text):
    raw = struct.pack('<ii',rid,kind)+text.encode()+b'\0\0'
    return struct.pack('<i',len(raw))+raw


class FakeSocket:
    def __init__(self, denied=False):
        self.data,self.denied = b'',denied
        self.closed = False
        self.needs_read = False

    def sendall(self, data):
        if self.needs_read:
            raise ConnectionError('Two request frames sent before receiving any response')
        self.needs_read = True
        rid,kind = struct.unpack('<ii',data[4:12])
        if kind == 3:
            self.data += packet(-1 if self.denied else rid,2,'')
        elif data[12:-2]:
            self.data += packet(rid,0,'first ')+packet(rid,0,'second')
        else:
            self.data += packet(rid,0,'')

    def recv(self, count):
        self.needs_read = False
        data,self.data = self.data[:min(count,3)],self.data[min(count,3):]
        return data

    def close(self):
        self.closed = True


class RconWireTest(unittest.TestCase):
    def test_idle_connection_is_replaced_before_sending_a_mutation(self):
        first,second = FakeSocket(),FakeSocket()
        with patch('socket.create_connection',side_effect=[first,second]):
            rcon = Rcon('test')
            rcon.last_used -= 6
            self.assertEqual(rcon.command('give Ciel_Debug oak_log 1'),'first second')
            self.assertTrue(first.closed)
            rcon.close()

    def test_fragmented_multi_packet_response(self):
        sock = FakeSocket()
        with patch('socket.create_connection',return_value=sock):
            rcon = Rcon('test')
            self.assertEqual(rcon.command('test command'),'first second')
            self.assertEqual(rcon.command('next command'),'first second')
            rcon.close()
        self.assertTrue(sock.closed)

    def test_bad_auth_closes_socket(self):
        sock = FakeSocket(denied=True)
        with patch('socket.create_connection',return_value=sock), self.assertRaises(RuntimeError):
            Rcon('test')
        self.assertTrue(sock.closed)

    def test_default_production_port_is_rejected(self):
        with self.assertRaises(ValueError):
            Rcon('test',port=25575)
