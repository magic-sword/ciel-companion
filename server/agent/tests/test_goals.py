"""Common work client tests with a game that has no crafting or recipe vocabulary."""
import asyncio
import copy
import types
import unittest
from unittest.mock import AsyncMock
import goals

class WorkTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.remote = {'version': 1, 'session': 'server', 'task_id': 'task', 'request_id': 'request',
                       'revision': 1, 'state': 'running', 'evidence': {}, 'message': ''}
        self.env = types.SimpleNamespace(game='puzzle', label='Puzzle', linked=True,
            profile={'work': {'version': 1, 'submit': 'submit', 'status': 'status', 'cancel': 'cancel', 'answer': 'answer'}},
            _call=AsyncMock(side_effect=self.call))
        self.lines, self.states = [], []
        self.runner = goals.GoalRunner(lambda why, **kw: self.lines.append(kw), self.states.append, env=self.env)

    async def call(self, name, args, **kw):
        if name == 'cancel':
            self.remote.update(state='cancelled', revision=self.remote['revision'] + 1, message='Stopped')
        return copy.deepcopy(self.remote)

    async def asyncTearDown(self):
        await self.runner.close()

    async def test_requests_an_opaque_capability_without_steps(self):
        r = await self.runner.start('puzzle.solve', {'board': 'abc'}, constraints={'moves': 7}, seconds=20)
        self.assertEqual(r['state'], 'running')
        name, args = self.env._call.await_args_list[0].args
        self.assertEqual(name, 'submit')
        self.assertEqual(args['arguments'], {'board': 'abc'})
        self.assertEqual(args['constraints'], {'moves': 7})
        self.assertEqual(self.runner.state()['v'], 2)
        self.assertNotIn('steps', self.runner.state())
        self.assertEqual((await self.runner.start('other', {}))['status'], 'busy')

    async def test_old_foreign_and_delayed_states_are_rejected(self):
        await self.runner.start('puzzle.solve', {})
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 0}))
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 2, 'session': 'old'}))
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 2, 'task_id': 'other'}))
        self.assertTrue(self.runner.accept({**self.remote, 'revision': 2, 'state': 'succeeded', 'message': 'Verified'}))
        self.assertEqual(len(self.lines), 1)
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 2, 'state': 'succeeded'}))
        self.assertIn('Verified', self.lines[0]['instructions'])

    async def test_cancelling_is_not_stopped_and_decision_needs_matching_id(self):
        await self.runner.start('puzzle.solve', {})
        self.remote.update(state='cancelling', revision=2, reason='stop_unconfirmed')
        self.env._call.side_effect = None
        self.env._call.return_value = copy.deepcopy(self.remote)
        result = await self.runner.stop()
        self.assertEqual(result['state'], 'cancelling')
        self.assertEqual(self.runner.state()['task']['state'], 'cancelling')
        self.assertIsNotNone(self.runner.body_step())
        self.assertEqual((await self.runner.answer('decision', 'retry'))['reason'], 'stale_decision')
        self.remote.update(state='needs_decision', revision=3, decision={'decision_id': 'decision'})
        self.runner.accept(self.remote)
        self.env._call.return_value = copy.deepcopy(self.remote)
        await self.runner.answer('decision', 'retry')
        name, args = self.env._call.await_args.args
        self.assertEqual(name, 'answer')
        self.assertEqual(args, {'task_id': 'task', 'decision_id': 'decision', 'action': 'retry'})

    async def test_unsupported_version_and_invalid_budget_do_not_submit(self):
        self.env.profile['work']['version'] = 99
        self.assertEqual((await self.runner.start('puzzle.solve', {}))['reason'], 'work_protocol_mismatch')
        self.env._call.assert_not_awaited()
        self.env.profile['work']['version'] = 1
        self.assertEqual((await self.runner.start('puzzle.solve', {}, seconds=True))['reason'], 'invalid_budget')
        self.assertEqual((await self.runner.start('puzzle.solve', {}, seconds=601))['reason'], 'invalid_budget')
        self.env._call.assert_not_awaited()

    async def test_transport_error_does_not_report_success(self):
        await self.runner.start('puzzle.solve', {})
        self.env._call.side_effect = None
        self.env._call.return_value = {'status': 'no_answer'}
        await asyncio.sleep(.6)
        self.assertEqual(self.runner.work['state'], 'running')
        self.assertTrue(any(not s['confirmed'] for s in self.states))
        self.assertEqual(self.lines, [])

    async def test_invalid_state_and_all_valid_states(self):
        for change in ({'state': {}}, {'state': 'paused'}, {'version': True}, {'remaining_ms': float('nan')}, {'decision': []}):
            self.assertFalse(self.runner.valid({**self.remote, **change}))
        for revision, state in enumerate(('accepted', 'running', 'needs_decision', 'cancelling', 'cancelled'), 1):
            self.runner.accept({**self.remote, 'revision': revision, 'state': state})
            self.assertEqual(self.runner.state()['task']['state'], state)
            self.assertNotIn('steps', self.runner.state())

    async def test_confirmation_recovers_without_work_revision_change(self):
        await self.runner.start('puzzle.solve', {})
        self.runner._publish(unknown=True)
        self.assertFalse(self.runner.state()['confirmed'])
        self.assertFalse(self.runner.accept(copy.deepcopy(self.remote)))
        self.assertTrue(self.runner.state()['confirmed'])
        self.assertEqual(self.lines, [])

    async def test_remaining_budget_changes_without_state_revision(self):
        self.remote['remaining_ms'] = 20000
        await self.runner.start('puzzle.solve', {}, seconds=20)
        self.remote['remaining_ms'] = 15000
        self.runner.accept(copy.deepcopy(self.remote))
        self.assertTrue(self.runner.state()['confirmed'])
        self.assertLessEqual(self.runner.state()['task']['remaining_ms'], 15000)
        self.remote['remaining_ms'] = 999999
        self.runner.accept(copy.deepcopy(self.remote))
        self.assertLessEqual(self.runner.state()['task']['remaining_ms'], 20000)

    async def test_stale_controls_never_target_new_work(self):
        await self.runner.start('puzzle.solve', {})
        count = self.env._call.await_count
        base = dict(v=2, type='goal.control', stream_id=self.runner._stream_id,
                    session='server', task_id='task', revision=1, action='stop')
        for change in ({'stream_id': 'old'}, {'session': 'old'}, {'task_id': 'old'}, {'revision': 0}):
            await self.runner._control({**base, **change})
        self.assertEqual(self.env._call.await_count, count)
        await self.runner._control(base)
        self.assertEqual(self.runner.work['state'], 'cancelled')

    async def test_control_revalidates_after_waiting_for_lock(self):
        await self.runner.start('puzzle.solve', {})
        await self.runner._lock.acquire()
        pending = asyncio.create_task(self.runner._control(dict(stream_id=self.runner._stream_id,
            session='server', task_id='task', revision=1, action='stop')))
        await asyncio.sleep(0)
        self.runner.accept({**self.remote, 'revision': 2})
        count = self.env._call.await_count
        self.runner._lock.release()
        await pending
        self.assertEqual(self.env._call.await_count, count)

    async def test_old_and_malformed_controls_are_ignored(self):
        import json
        await self.runner.start('puzzle.solve', {})
        count = sum(c.args[0] == 'cancel' for c in self.env._call.await_args_list)
        for message in ([], None, {'v': 1, 'type': 'goal.control', 'action': 'stop'}):
            self.runner.on_data(types.SimpleNamespace(topic='ciel.goal', data=json.dumps(message).encode()))
        await asyncio.sleep(0)
        self.assertEqual(sum(c.args[0] == 'cancel' for c in self.env._call.await_args_list), count)

    async def test_transport_exception_preserves_state_and_watch(self):
        await self.runner.start('puzzle.solve', {})
        self.env._call.side_effect = RuntimeError('offline')
        await asyncio.sleep(.05)
        self.assertFalse(self.runner.state()['confirmed'])
        self.assertEqual(self.runner.state()['task']['state'], 'running')
        self.assertFalse(self.runner._watch.done())

class OneBodyCallTest(unittest.TestCase):
    def test_only_one_moving_tool_per_reply(self):
        # 集めると作るを同時に呼び、体の技が取り合いになって両方失敗した件（2026-11-07）
        import mind
        from livekit.agents import llm
        def chunk(*names):
            calls = [llm.FunctionToolCall(name=n, arguments='{}', call_id=f'c{i}') for i, n in enumerate(names)]
            return llm.ChatChunk(id='x', delta=llm.ChoiceDelta(role='assistant', tool_calls=calls))
        taken = []
        moving = {'collect_blocks', 'craft_item'} | mind.GOAL_ONE   # ゲームの act の道具と、目的の道具（Mind.one_call_tools）
        out, dropped = mind.one_body_call(chunk('collect_blocks', 'look_around', 'craft_item'), taken, moving)
        self.assertEqual([c.name for c in out.delta.tool_calls], ['collect_blocks', 'look_around'])
        self.assertEqual(dropped, ['craft_item'])
        out, dropped = mind.one_body_call(chunk('submit_game_task'), taken, moving)   # 同じ返事の続きの chunk でも
        self.assertIsNone(out)
        self.assertEqual(dropped, ['submit_game_task'])
        out, dropped = mind.one_body_call(chunk('remember_about_speaker'), [], moving)
        self.assertEqual(dropped, [])


if __name__ == '__main__':
    unittest.main()
