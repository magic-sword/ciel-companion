import asyncio
import json
import types
import unittest
from unittest.mock import AsyncMock
from livekit.agents import llm
from game_intake import GameIntake, STOP


class IntakeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.runner = types.SimpleNamespace(env=types.SimpleNamespace(playing=lambda: True,
            profile={'work': {'capabilities': [{'name': 'puzzle.solve'}]}}), work=None,
            status=lambda: {}, body_step=lambda: None, start=AsyncMock(return_value={'task_id': 't'}),
            stop=AsyncMock(return_value={'state': 'cancelled', 'message': 'Stopped'}), answer=AsyncMock())
        self.create = AsyncMock()
        self.client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create)), close=AsyncMock())
        self.intake = GameIntake(self.runner, 'Return a work decision', client=self.client)

    def respond(self, value):
        self.create.return_value = types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(value)))])

    async def test_one_accepted_user_item_submits_once_and_preserves_opaque_arguments(self):
        self.respond({'operation': 'submit', 'capability': 'puzzle.solve', 'arguments': {'board': 'abc'},
                      'constraints': {'moves': 7}, 'seconds': 90, 'title': 'Puzzle'})
        item = llm.ChatMessage(role='user', content=['Solve it'])
        await self.intake.handle(item)
        await self.intake.handle(item)
        self.runner.start.assert_awaited_once()
        self.assertEqual(self.runner.start.await_args.args, ('puzzle.solve', {'board': 'abc'}))
        self.assertEqual(self.runner.start.await_args.kwargs['request_id'], item.id)
        self.assertLessEqual(self.runner.start.await_args.kwargs['seconds'], 90)

    async def test_chat_does_not_submit_and_pseudo_tool_text_is_rejected(self):
        self.respond({'operation': 'none'})
        self.assertIsNone(await self.intake.handle(llm.ChatMessage(role='user', content=['Question?'])))
        self.create.return_value.choices[0].message.content = '<submit_game_task>pretend</submit_game_task>'
        self.assertIsNotNone(await self.intake.handle(llm.ChatMessage(role='user', content=['Do it'])))
        self.runner.start.assert_not_awaited()

    async def test_stop_during_inference_prevents_delayed_submission(self):
        entered, release = asyncio.Event(), asyncio.Event()
        self.respond({'operation': 'submit', 'capability': 'puzzle.solve', 'arguments': {}, 'constraints': {}})
        response = self.create.return_value
        async def generate(**kw):
            entered.set()
            await release.wait()
            return response
        self.create.side_effect = generate
        task = asyncio.create_task(self.intake.handle(llm.ChatMessage(role='user', content=['Do it'])))
        await entered.wait()
        self.intake.on_transcribed(types.SimpleNamespace(is_final=True, transcript='やめて'))
        release.set()
        await task
        self.runner.start.assert_not_awaited()
        self.runner.stop.assert_awaited_once()

    def test_fast_stop_does_not_match_quotes_negation_or_questions(self):
        for text in ('止めないで', '「止まって」と言った', '止めた方がいい？', '止めていいですか'):
            self.assertIsNone(STOP.fullmatch(text))
        self.assertIsNotNone(STOP.fullmatch('今の作業をやめて、その場で待ってください。こちらが頼むまで再開しないでください。'))

    async def test_invalid_schema_gets_one_correction_within_original_budget(self):
        self.respond({'operation': 'submit', 'capability': 'puzzle.solve', 'arguments': {}, 'constraints': {}, 'seconds': 90})
        self.runner.start.side_effect = [{'reason': 'invalid_request', 'status': 'error'}, {'task_id': 't'}]
        item = llm.ChatMessage(role='user', content=['Do it'])
        await self.intake.handle(item)
        self.assertEqual(self.create.await_count, 2)
        calls = self.runner.start.await_args_list
        self.assertEqual(calls[0].kwargs['request_id'], calls[1].kwargs['request_id'])
        self.assertLessEqual(calls[1].kwargs['seconds'], calls[0].kwargs['seconds'])
        self.runner.start.reset_mock(side_effect=True)
        self.runner.start.return_value = {'reason': 'invalid_request', 'status': 'error'}
        await self.intake.handle(llm.ChatMessage(role='user', content=['New request']))
        self.assertEqual(self.runner.start.await_count, 2)
