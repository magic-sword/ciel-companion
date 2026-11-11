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
            _connection_epoch=1, meta={}, tools=[], use=AsyncMock(return_value={'status': 'started'}),
            profile={'work': {'capabilities': [{'name': 'puzzle.solve', 'description': 'Solve a puzzle',
                'arguments': {'type': 'object', 'properties': {'board': {'type': 'string'}},
                              'required': ['board'], 'additionalProperties': False},
                'constraints': {'type': 'object', 'properties': {'moves': {'type': 'integer'}},
                                'required': ['moves'], 'additionalProperties': False}}]}}), work=None,
            status=lambda: {}, body_step=lambda: None, start=AsyncMock(return_value={'task_id': 't'}),
            stop=AsyncMock(return_value={'state': 'cancelled', 'message': 'Stopped'}), answer=AsyncMock())
        self.create = AsyncMock()
        self.client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create)), close=AsyncMock())
        self.intake = GameIntake(self.runner, 'Return a work decision', client=self.client)

    def respond(self, value):
        self.create.return_value = types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(value)))])

    def sequence(self, *values):
        self.create.side_effect = [types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content=json.dumps(value)))]) for value in values]

    def tool(self):
        self.runner.env.tools = [types.SimpleNamespace(id='puzzle_move', info=types.SimpleNamespace(raw_schema={
            'name': 'puzzle_move', 'description': 'Move to a coordinate', 'parameters': {
                'type': 'object', 'properties': {'x': {'type': 'integer'}}, 'required': ['x']}}))]
        self.runner.env.meta['puzzle_move'] = {'ciel/role': 'act'}

    async def test_one_accepted_user_item_submits_once_and_preserves_opaque_arguments(self):
        self.sequence({'operation': 'select', 'capability': '1'},
            {'operation': 'submit', 'capability': '1', 'arguments': {'board': 'abc'},
             'constraints': {'moves': 7}, 'seconds': 90, 'title': 'Puzzle'})
        item = llm.ChatMessage(role='user', content=['Solve it'])
        await self.intake.handle(item)
        await self.intake.handle(item)
        self.runner.start.assert_awaited_once()
        self.assertEqual(self.runner.start.await_args.args, ('puzzle.solve', {'board': 'abc'}))
        self.assertEqual(self.runner.start.await_args.kwargs['request_id'], item.id)
        self.assertLessEqual(self.runner.start.await_args.kwargs['seconds'], 90)
        first = json.loads(self.create.await_args_list[0].kwargs['messages'][1]['content'])
        second = json.loads(self.create.await_args_list[1].kwargs['messages'][1]['content'])
        self.assertEqual(first['capabilities'], [{'id': '1', 'description': 'Solve a puzzle'}])
        self.assertNotIn('arguments', first['capabilities'][0])
        self.assertEqual(second['capability']['name'], 'puzzle.solve')
        self.assertEqual(second['required_operation'], 'submit')

    async def test_chat_does_not_submit_and_pseudo_tool_text_is_rejected(self):
        self.respond({'operation': 'none'})
        self.assertIsNone(await self.intake.handle(llm.ChatMessage(role='user', content=['Question?'])))
        self.create.return_value.choices[0].message.content = '<submit_game_task>pretend</submit_game_task>'
        self.assertIsNotNone(await self.intake.handle(llm.ChatMessage(role='user', content=['Do it'])))
        self.runner.start.assert_not_awaited()

    async def test_reference_is_frozen_across_selection_and_argument_generation(self):
        self.tool()
        env=self.runner.env
        env.profile['reference_context']=True
        env.state={'references':{'selection_id':'old'}}
        env._refresh=AsyncMock()
        env.tools[0].info.raw_schema['parameters']['properties']['selection_id']={'type':'string'}
        env.meta['puzzle_move']['ciel/reference_argument']='selection_id'
        responses=iter([{'operation':'select','capability':'2'},
                        {'operation':'execute','arguments':{'x':5,'selection_id':'old'}}])
        async def generate(**kw):
            env.state['references']['selection_id']='new'
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(next(responses))))])
        self.create.side_effect=generate
        await self.intake.handle(llm.ChatMessage(role='user',content=['Move here']))
        env.use.assert_awaited_once_with('puzzle_move',{'x':5,'selection_id':'old'})
        selection=json.loads(self.create.await_args_list[0].kwargs['messages'][1]['content'])
        self.assertEqual(selection['capabilities'][1]['reference_argument'],'selection_id')
        for call in self.create.await_args_list:
            self.assertEqual(json.loads(call.kwargs['messages'][1]['content'])['references']['selection_id'],'old')

    async def test_model_cannot_substitute_another_reference(self):
        self.tool()
        env=self.runner.env
        env.profile['reference_context']=True
        env.state={'references':{'selection_id':'old'}}
        env._refresh=AsyncMock()
        env.tools[0].info.raw_schema['parameters']['properties']['selection_id']={'type':'string'}
        env.meta['puzzle_move']['ciel/reference_argument']='selection_id'
        self.sequence({'operation':'select','capability':'2'},
                      {'operation':'execute','arguments':{'x':5,'selection_id':'invented'}})
        await self.intake.handle(llm.ChatMessage(role='user',content=['Move here']))
        env.use.assert_not_awaited()

    async def test_bound_coordinate_schema_resolves_without_model_numbers(self):
        self.tool()
        env = self.runner.env
        env.meta['puzzle_move']['ciel/target_binding'] = {'kind': 'axes', 'fields': {'x': ['x', 0]}, 'point': True}
        self.sequence({'operation': 'select', 'capability': '2'},
                      {'operation': 'execute', 'arguments': {'target_id': 'T1'}})
        await self.intake.handle(llm.ChatMessage(role='user', content=['X=-12へ移動して']))
        env.use.assert_awaited_once_with('puzzle_move', {'x': -12})
        detail = json.loads(self.create.await_args.kwargs['messages'][1]['content'])
        self.assertNotIn('x', detail['capability']['arguments']['properties'])

    async def test_model_cannot_override_bound_numbers_or_use_missing_target(self):
        self.tool()
        env = self.runner.env
        env.meta['puzzle_move']['ciel/target_binding'] = {'kind': 'axes', 'fields': {'x': ['x', 0]}}
        for arguments in ({'target_id': 'T1', 'x': 99}, {'target_id': 'invented'}):
            self.sequence({'operation': 'select', 'capability': '2'},
                          {'operation': 'execute', 'arguments': arguments},
                          {'operation': 'execute', 'arguments': arguments})
            await self.intake.handle(llm.ChatMessage(role='user', content=['X=5へ']))
        self.sequence({'operation': 'select', 'capability': '2'})
        await self.intake.handle(llm.ChatMessage(role='user', content=['X=へ']))
        env.use.assert_not_awaited()

    async def test_explicit_axes_block_old_pointer_even_if_model_selects_it(self):
        self.tool()
        env = self.runner.env
        env.profile['reference_context'] = True
        env.state = {'references': {'selection_id': 'old'}}
        env._refresh = AsyncMock()
        env.meta['puzzle_move']['ciel/target_binding'] = {'kind': 'reference', 'argument': 'selection_id'}
        self.sequence({'operation': 'select', 'capability': '2'})
        await self.intake.handle(llm.ChatMessage(role='user', content=['X=5、Y=64、Z=0を除去して']))
        self.assertEqual(self.create.await_count, 1)
        env.use.assert_not_awaited()

    async def test_speech_end_reference_is_bound_to_transcribed_item(self):
        env=self.runner.env
        env.profile['reference_context']=True
        env.state={'references':{'selection_id':'spoken-target'}}
        env._refresh=AsyncMock()
        self.intake.on_user_state(types.SimpleNamespace(old_state='speaking',new_state='listening'))
        await self.intake._speech_reference[1]
        self.intake.on_transcribed(types.SimpleNamespace(is_final=True,item_id='speech1',transcript='Look here'))
        env.state={'references':{'selection_id':'later-target'}}
        self.respond({'operation':'none'})
        await self.intake.handle(llm.ChatMessage(id='speech1',role='user',content=['Look here']))
        payload=json.loads(self.create.await_args.kwargs['messages'][1]['content'])
        self.assertEqual(payload['references']['selection_id'],'spoken-target')
        self.intake.on_user_state(types.SimpleNamespace(old_state='listening',new_state='speaking'))
        self.assertIsNone(self.intake._speech_reference)

    async def test_failed_refresh_cannot_reuse_stale_reference(self):
        env=self.runner.env
        env.profile['reference_context']=True
        env.state={'references':{'selection_id':'stale'}}
        env._refresh=AsyncMock(return_value=False)
        result=await self.intake.handle(llm.ChatMessage(role='user',content=['Move here']))
        self.assertIn('確認できません',result)
        self.create.assert_not_awaited()
        env.use.assert_not_awaited()

    async def test_next_text_item_does_not_reuse_previous_speech_capture(self):
        env = self.runner.env
        env.profile['reference_context'] = True
        env.state = {'references': {'selection_id': 'first'}}
        env._refresh = AsyncMock()
        self.intake.on_transcribed(types.SimpleNamespace(is_final=True, item_id='one', transcript='Here'))
        await self.intake._speech_reference[1]
        env.state = {'references': {'selection_id': 'second'}}
        self.intake.on_transcribed(types.SimpleNamespace(is_final=True, item_id='two', transcript='Here'))
        await self.intake._speech_reference[1]
        self.respond({'operation': 'none'})
        await self.intake.handle(llm.ChatMessage(id='two', role='user', content=['Here']))
        self.assertEqual(json.loads(self.create.await_args.kwargs['messages'][1]['content'])['references']['selection_id'], 'second')

    async def test_reconnect_after_speech_capture_cannot_reuse_reference(self):
        env = self.runner.env
        env.profile['reference_context'] = True
        env.state = {'references': {'selection_id': 'old-world'}}
        env._refresh = AsyncMock()
        self.intake.on_transcribed(types.SimpleNamespace(is_final=True, item_id='one', transcript='Here'))
        await self.intake._speech_reference[1]
        env._connection_epoch += 1
        await self.intake.handle(llm.ChatMessage(id='one', role='user', content=['Here']))
        self.create.assert_not_awaited()
        env.use.assert_not_awaited()

    async def test_stop_during_inference_prevents_delayed_submission(self):
        entered, release = asyncio.Event(), asyncio.Event()
        self.respond({'operation': 'select', 'capability': '1'})
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
        self.sequence({'operation': 'select', 'capability': '1'},
                      {'operation': 'submit', 'capability': '1', 'arguments': {}, 'constraints': {}, 'seconds': 90},
                      {'operation': 'submit', 'capability': '1', 'arguments': {'board': 'abc'},
                       'constraints': {'moves': 7}, 'seconds': 90})
        item = llm.ChatMessage(role='user', content=['Do it'])
        await self.intake.handle(item)
        self.assertEqual(self.create.await_count, 3)
        self.runner.start.assert_awaited_once()
        self.assertEqual(self.runner.start.await_args.kwargs['request_id'], item.id)
        self.runner.start.reset_mock()
        self.sequence({'operation': 'select', 'capability': '1'},
                      {'operation': 'submit', 'capability': '1', 'arguments': {}, 'constraints': {}},
                      {'operation': 'submit', 'capability': '1', 'arguments': {}, 'constraints': {}})
        await self.intake.handle(llm.ChatMessage(role='user', content=['New request']))
        self.runner.start.assert_not_awaited()

    async def test_body_action_uses_real_guarded_entry_once(self):
        self.tool()
        self.runner.env._body={'current':None,'pending':None,'blocked':False,
                               'last':{'phase':'succeeded','args':{'x':999}}}
        self.sequence({'operation': 'select', 'capability': '2'},
                      {'operation': 'execute', 'capability': '2', 'arguments': {'x': 12}})
        item = llm.ChatMessage(role='user', content=['Move there'])
        await self.intake.handle(item)
        await self.intake.handle(item)
        self.runner.env.use.assert_awaited_once_with('puzzle_move', {'x': 12})
        self.runner.start.assert_not_awaited()
        detail=json.loads(self.create.await_args_list[1].kwargs['messages'][1]['content'])
        self.assertEqual(detail['required_operation'], 'execute')
        for call in self.create.await_args_list:
            body=json.loads(call.kwargs['messages'][1]['content'])['body']
            self.assertNotIn('last',body)
            self.assertIn('current',body)
            self.assertIn('blocked',body)

    async def test_wrong_operation_is_repaired_with_bound_kind_not_executed_as_work(self):
        self.tool()
        self.sequence({'operation':'select','capability':'2'},
                      {'operation':'submit','arguments':{'x':12}},
                      {'operation':'execute','arguments':{'x':12}})
        await self.intake.handle(llm.ChatMessage(role='user',content=['Build there']))
        for call in self.create.await_args_list[1:]:
            self.assertEqual(json.loads(call.kwargs['messages'][1]['content'])['required_operation'],'execute')
        self.runner.env.use.assert_awaited_once_with('puzzle_move',{'x':12})
        self.runner.start.assert_not_awaited()

    async def test_unselected_or_unknown_tool_never_executes(self):
        self.tool()
        for action in ({'operation': 'execute', 'capability': '2', 'arguments': {'x': 12}},
                       {'operation': 'select', 'capability': 'invented'}):
            self.respond(action)
            await self.intake.handle(llm.ChatMessage(role='user', content=['Do it']))
        self.runner.env.use.assert_not_awaited()

    async def test_changed_connection_definition_and_extra_arguments_are_rejected(self):
        self.tool()
        for change in ('connection', 'definition', 'arguments'):
            self.runner.env._connection_epoch = 1
            self.runner.env.tools[0].info.raw_schema['description'] = 'Move to a coordinate'
            calls = 0
            async def generate(**kw):
                nonlocal calls
                calls += 1
                if calls == 1:
                    value = {'operation': 'select', 'capability': '2'}
                else:
                    if change == 'connection': self.runner.env._connection_epoch += 1
                    if change == 'definition': self.runner.env.tools[0].info.raw_schema['description'] = 'Changed'
                    value = {'operation': 'execute', 'capability': '2', 'arguments': {'x': 12}}
                    if change == 'arguments': value['arguments']['unexpected'] = True
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(value)))])
            self.create.side_effect = generate
            await self.intake.handle(llm.ChatMessage(role='user', content=['Move']))
        self.runner.env.use.assert_not_awaited()

    async def test_direct_follow_stop_does_not_claim_early_completion(self):
        self.runner.env.profile['stop_tool'] = 'puzzle_stop'
        self.runner.env.meta['puzzle_stop'] = {'ciel/role': 'act', 'ciel/stops': True}
        self.runner.env.use.return_value = {'status': 'stopping'}
        reply = await self.intake.handle(llm.ChatMessage(role='user', content=['やめて']))
        self.runner.env.use.assert_awaited_once_with('puzzle_stop', {})
        self.assertNotIn('停止しました', reply)
        self.create.assert_not_awaited()

    async def test_owner_permission_lost_while_generating_blocks_body(self):
        self.tool()
        count = 0
        async def generate(**kw):
            nonlocal count
            count += 1
            value = {'operation': 'select', 'capability': '2'} if count == 1 else {
                'operation': 'execute', 'capability': '2', 'arguments': {'x': 12}}
            if count == 2:
                self.intake.authorized = lambda: False
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(value)))])
        self.create.side_effect = generate
        await self.intake.handle(llm.ChatMessage(role='user', content=['Move']))
        self.runner.env.use.assert_not_awaited()
