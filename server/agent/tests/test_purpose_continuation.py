import copy
import json
import unittest
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock

import test_game_decision as game_tests
import test_goals as goal_tests
import test_tool_decision as conversation_tests


class PurposeTest(unittest.IsolatedAsyncioTestCase):
    setUp = game_tests.DecisionTest.setUp
    reply = staticmethod(game_tests.DecisionTest.reply)
    respond = game_tests.DecisionTest.respond
    say = game_tests.DecisionTest.say
    async def test_reply_is_exact_owner_text_and_has_no_generated_message(self):
        self.runner.work = dict(state='needs_decision', decision=dict(decision_id='d', actions=['reply', 'cancel']))
        self.respond(dict(say='OK', act=dict(kind='reply')))
        await self.say('Use wood, please.')
        self.assertEqual(self.runner.answer.await_args.args, ('d', 'reply', 'Use wood, please.'))

    async def test_replacement_passes_the_whole_new_objective(self):
        self.runner.work = dict(state='needs_decision', decision=dict(actions=['reply', 'cancel']))
        self.runner.replace = AsyncMock(return_value=dict(status='accepted'))
        self.respond(dict(say='OK', act=dict(kind='replace', request='Make a wooden pickaxe')))
        await self.say('Now make a wooden pickaxe')
        self.assertEqual(self.runner.replace.await_args.args, ('game.goal', {'request': 'Make a wooden pickaxe'}))
        self.runner.answer.assert_not_awaited()

    async def test_replacement_cannot_cancel_a_different_work(self):
        import game_decision
        old = dict(state='running', session='s', task_id='old')
        ops = game_decision.operations(dict(kind='replace', request='new objective'), old, self.env)
        self.runner.work = {**old, 'task_id': 'different'}
        self.runner.replace = AsyncMock()
        self.assertIsNotNone(await self.decision._carry_out(ops, 'new objective', None, None))
        self.runner.replace.assert_not_awaited()


class ReplacementTest(unittest.IsolatedAsyncioTestCase):
    setUp = goal_tests.WorkTest.setUp
    call = goal_tests.WorkTest.call
    asyncTearDown = goal_tests.WorkTest.asyncTearDown
    async def test_replace_waits_for_confirmed_cancellation_and_updates_title(self):
        await self.runner.start('puzzle.solve', {'board': 'old'}, title='Old board')
        original = self.call
        async def call(name, args, **kwargs):
            if name == 'submit':
                return {**self.remote, 'task_id': 'new', 'state': 'running', 'arguments': args['arguments']}
            return await original(name, args, **kwargs)
        self.env._call.side_effect = call
        result = await self.runner.replace('puzzle.solve', {'board': 'new'}, title='New board')
        self.assertEqual(result['task_id'], 'new')
        self.assertEqual(self.runner.title, 'New board')
        names = [c.args[0] for c in self.env._call.await_args_list]
        self.assertEqual(names[:3], ['submit', 'cancel', 'submit'])

    async def test_unconfirmed_stop_does_not_submit_replacement(self):
        await self.runner.start('puzzle.solve', {'board': 'old'})
        self.env._call.side_effect = None
        self.env._call.return_value = {**self.remote, 'state': 'cancelling', 'revision': 2}
        result = await self.runner.replace('puzzle.solve', {'board': 'new'})
        self.assertEqual(result['reason'], 'stop_unconfirmed')
        self.assertEqual(sum(c.args[0] == 'submit' for c in self.env._call.await_args_list), 1)


class SilentAndCacheTest(unittest.IsolatedAsyncioTestCase):
    setUp = conversation_tests.ConversationDecisionTests.setUp
    answer = conversation_tests.ConversationDecisionTests.answer
    node = conversation_tests.ConversationDecisionTests.node
    dispatch = conversation_tests.ConversationDecisionTests.dispatch
    async def test_silent_step_continues_without_a_text_chunk(self):
        self.create.side_effect = [self.answer(dict(kind='none'), next='continue', memo='Compare the two choices'),
                                  self.answer(dict(kind='none'), 'The first choice fits.', memo=None)]
        chunks = await self.node()
        self.assertEqual(len(chunks), 1)
        self.assertIn('first choice', chunks[0].delta.content)
        self.assertEqual(self.create.await_count, 2)

    async def test_tool_feedback_preserves_entire_previous_request_prefix(self):
        requests = []
        async def create(**kwargs):
            requests.append(copy.deepcopy(kwargs['messages']))
            return (self.answer(dict(kind='load', service_ids=['6'])) if len(requests) == 1 else
                    self.answer(dict(kind='clarify'), 'Which entry?'))
        self.create.side_effect = create
        chunks = await self.node()
        await self.dispatch(chunks[0].delta.tool_calls[0])
        self.chat.add_message(role='system', content='Changed current state at tool reentry')
        await self.node()
        self.assertEqual(requests[1][:len(requests[0])], requests[0])
        self.assertTrue(any(m.get('role') == 'tool' for m in requests[1]))

    async def test_repeated_silent_state_stops_without_speech(self):
        self.create.return_value = self.answer(dict(kind='none'), next='continue', memo='same unfinished point')
        with self.assertRaisesRegex(ValueError, 'repeated_silent_continuation'):
            await self.node()
        self.assertEqual(self.create.await_count, 2)
