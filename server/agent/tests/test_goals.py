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
        self.assertEqual(self.runner.state()['steps'], [])
        self.assertEqual((await self.runner.start('other', {}))['status'], 'busy')

    async def test_old_foreign_and_delayed_states_are_rejected(self):
        await self.runner.start('puzzle.solve', {})
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 0}))
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 2, 'session': 'old'}))
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 2, 'task_id': 'other'}))
        self.assertTrue(self.runner.accept({**self.remote, 'revision': 2, 'state': 'succeeded', 'message': 'Verified'}))
        self.assertEqual(len(self.lines), 1)
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 2, 'state': 'succeeded'}))
        self.assertEqual(self.runner.report(), 'Verified')
        self.runner.reported()
        self.assertIsNone(self.runner.notice)

    async def test_cancelling_is_not_stopped_and_decision_needs_matching_id(self):
        await self.runner.start('puzzle.solve', {})
        self.remote.update(state='cancelling', revision=2, reason='stop_unconfirmed')
        self.env._call.side_effect = None
        self.env._call.return_value = copy.deepcopy(self.remote)
        result = await self.runner.stop()
        self.assertEqual(result['state'], 'cancelling')
        self.assertEqual(self.runner.state()['goal']['status'], 'paused')
        self.assertIsNotNone(self.runner.body_step())
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
        self.env._call.assert_not_awaited()

    async def test_transport_error_does_not_report_success(self):
        await self.runner.start('puzzle.solve', {})
        self.env._call.side_effect = None
        self.env._call.return_value = {'status': 'no_answer'}
        await asyncio.sleep(.6)
        self.assertEqual(self.runner.work['state'], 'running')
        self.assertTrue(any(s['attention'] == '状態不明・停止未確認' for s in self.states))
        self.assertEqual(self.lines, [])

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
