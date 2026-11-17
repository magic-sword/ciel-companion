import json
import asyncio
import unittest
from dataclasses import replace
from unittest.mock import patch
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace as Obj

import jsonschema
from capabilities import CapabilityCatalog
from persona import load_persona
from tool_decision import ToolDecision, ConversationDecision
import tools
from livekit.agents import RunContext, ToolResult, llm
from livekit.agents.llm import utils
from livekit.agents.voice.events import FunctionToolsExecutedEvent
from tool_decision import ConversationDecision


class ToolDecisionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = CapabilityCatalog(tools.MODULES)
        self.visible = {f.id: f for f in self.catalog.select(tools.TOOLS + [self.catalog.loader, self.catalog.executor])}
        self.loop = ToolDecision()

    def choose(self, act):
        schema = self.loop.schema(self.catalog, self.visible)
        return self.loop.resolve({'say': [], 'act': act}, schema, self.catalog, self.visible)

    def test_none_is_a_valid_initial_choice(self):
        self.assertEqual(self.choose({'kind': 'none'}), ('', None))
        self.assertEqual(self.loop.outcome, 'none')

    def test_load_is_not_completion_and_does_not_expose_unloaded_tools(self):
        with self.assertRaises(jsonschema.ValidationError):
            self.choose({'kind': 'call', 'tool_id': 'read_minutes', 'arguments': {}})
        _, call = self.choose({'kind': 'load', 'service_ids': ['5']})
        result = self.catalog.load(['5'])
        self.loop.observe(call.name, result)
        for terminal in ('none', 'complete', 'accepted'):
            with self.assertRaises(jsonschema.ValidationError):
                self.choose({'kind': terminal, **({'evidence': ['r1']} if terminal != 'none' else {})})
        _, call = self.choose({'kind': 'call', 'tool_id': 'read_minutes', 'arguments': {}})
        self.assertEqual(call.name, 'execute_capability')
        self.assertEqual(json.loads(call.arguments)['version'], self.catalog.definition('read_minutes')['version'])
        self.loop.observe('read_minutes', {'status': 'ok'})
        self.choose({'kind': 'complete', 'evidence': ['r2']})
        self.assertEqual(self.loop.outcome, 'complete')

    def test_failed_result_can_be_reported_but_not_cited_as_success(self):
        self.catalog.load(['5'])
        self.choose({'kind': 'call', 'tool_id': 'read_minutes', 'arguments': {}})
        self.loop.observe('read_minutes', {'status': 'failed'})
        with self.assertRaises(jsonschema.ValidationError):
            self.choose({'kind': 'complete', 'evidence': ['r1']})
        self.choose({'kind': 'blocked'})

    def test_repeat_operation_is_not_dispatched_twice(self):
        self.catalog.load(['5'])
        act = {'kind': 'call', 'tool_id': 'read_minutes', 'arguments': {}}
        self.choose(act)
        self.loop.observe('read_minutes', {'status': 'ok'})
        with self.assertRaisesRegex(ValueError, 'duplicate_operation'):
            self.choose(act)

    def test_current_permissions_override_old_schema(self):
        self.catalog.load(['5'])
        schema = self.loop.schema(self.catalog, self.visible)
        self.catalog.select(tools.for_comments(tools.TOOLS))
        with self.assertRaisesRegex(ValueError, 'no_longer_allowed'):
            self.loop.resolve({'say': [], 'act': {'kind': 'call', 'tool_id': 'read_minutes', 'arguments': {}}},
                              schema, self.catalog, self.visible)

    def test_refused_operation_absent_and_can_clarify_after_loading(self):
        self.catalog.load(['5'])
        schema = self.loop.schema(self.catalog, self.visible, {'start_minutes'})
        self.assertNotIn('start_minutes', json.dumps(schema))
        self.choose({'kind': 'load', 'service_ids': ['5']})
        self.choose({'kind': 'clarify'})

    def test_cancel_timeout_and_step_budget(self):
        self.loop.cancelled = True
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.choose({'kind': 'none'})
        self.loop.cancelled = False
        with patch('tool_decision.time.monotonic', return_value=self.loop.started + 121):
            with self.assertRaises(TimeoutError):
                self.choose({'kind': 'none'})
        self.loop.steps = 8
        with self.assertRaises(TimeoutError):
            self.choose({'kind': 'none'})

    def test_intermediate_speech_is_held_and_prompt_is_loaded(self):
        schema = self.loop.schema(self.catalog, self.visible)
        speech, call = self.loop.resolve({'say': [{'feeling': 'neutral', 'text': '記録します。'}],
            'act': {'kind': 'load', 'service_ids': ['5']}}, schema, self.catalog, self.visible)
        self.assertEqual(speech, '')
        self.assertIsNotNone(call)
        persona = load_persona()
        self.assertIn('{state}', persona.tool_decide_instructions)
        self.assertNotEqual(persona.fingerprint, replace(persona, tool_decide_instructions='changed').fingerprint)


class ConversationDecisionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from agent import Ciel
        from conversation import Conversation
        from mind import Mind
        with patch('agent.PIPELINE', True):
            self.agent = Ciel()
        history = Conversation()
        history.complete(history.reserve(), 'fixture project', label='owner', sure=True)
        self.agent.mind = Mind(history)
        self.agent.style = Obj(talk='normal', presence='solo')
        self.speech = Obj(id='turn-1', num_steps=1, interrupted=False)
        self.session = Obj(userdata=tools.State(history=history), current_speech=self.speech, _global_run_state=None)
        self.chat = llm.ChatContext()
        self.chat.add_message(role='system', content=self.agent.instructions)
        self.chat.add_message(role='user', content='Search fixture in this conversation')
        self.create = AsyncMock()
        self.client = MagicMock()
        self.client.__aenter__ = AsyncMock(return_value=Obj(chat=Obj(completions=Obj(create=self.create))))
        self.client.__aexit__ = AsyncMock(return_value=False)

    def answer(self, act, text='', next='wait', memo=''):
        return Obj(usage=None, choices=[Obj(message=Obj(content=json.dumps(dict(
            say=[dict(feeling='neutral', text=text)] if text else [], act=act, next=next, memo=memo))))])

    async def node(self):
        with patch.object(self.agent, '_get_activity_or_raise', return_value=Obj(session=self.session)), \
                patch('models.is_local', return_value=False), patch('models.create_client', return_value=self.client):
            return [c async for c in self.agent._pipeline_llm(self.chat, self.agent.tools, {})]

    async def dispatch(self, call):
        fn = next(f for f in self.agent.capabilities.select(self.agent.tools) if f.id == call.name)
        call = llm.FunctionCall(call_id=call.call_id, name=call.name, arguments=call.arguments)
        context = RunContext(session=self.session, speech_handle=self.speech, function_call=call)
        args, kwargs = utils.prepare_function_arguments(fnc=fn, json_arguments=call.arguments, call_ctx=context)
        result = await fn(*args, **kwargs)
        required = True
        if isinstance(result, ToolResult):
            required, result = result.reply_required, result.output
        out = llm.FunctionCallOutput(call_id=call.call_id, name=call.name,
            output=result if isinstance(result, str) else json.dumps(result), is_error=False, reply_required=required)
        self.agent.conversation_decision.feedback(FunctionToolsExecutedEvent(function_calls=[call], function_call_outputs=[out]))
        self.chat.items.extend([call, out])
        return out

    async def test_normal_pipeline_loads_executes_real_mcp_and_answers_from_result(self):
        self.create.side_effect = [self.answer(dict(kind='load', service_ids=['6'])),
            self.answer(dict(kind='call', tool_id='search_conversation', arguments={'query': 'fixture'})),
            self.answer(dict(kind='complete', evidence=['r2']), 'Found fixture project')]
        chunks = await self.node()
        self.assertEqual(chunks[0].delta.tool_calls[0].name, 'load_capabilities')
        await self.dispatch(chunks[0].delta.tool_calls[0])
        chunks = await self.node()
        self.assertEqual(chunks[0].delta.tool_calls[0].name, 'execute_capability')
        output = await self.dispatch(chunks[0].delta.tool_calls[0])
        self.assertIn('fixture project', output.output)
        chunks = await self.node()
        self.assertIn('Found fixture project', chunks[0].delta.content)
        self.assertEqual(self.agent.conversation_decision.loop.steps, 3)
        self.assertEqual(self.create.await_count, 3)

    async def test_late_model_result_cannot_dispatch_after_user_interrupts(self):
        async def interrupted(**kwargs):
            self.agent.conversation_decision.on_user_state(Obj(new_state='speaking'))
            return self.answer(dict(kind='load', service_ids=['6']))
        self.create.side_effect = interrupted
        self.assertEqual(await self.node(), [])
        self.assertTrue(self.agent.conversation_decision.loop.cancelled)

    async def test_spoken_continuation_streams_without_another_user_turn(self):
        states = []
        self.agent.conversation_decision = ConversationDecision(observe_continuation=lambda **s: states.append(s))
        states.clear()
        self.create.side_effect = [self.answer(dict(kind='none'), 'First part.', next='continue'),
                                  self.answer(dict(kind='none'), 'Last part.')]
        chunks = await self.node()
        self.assertEqual(len(chunks), 2)
        self.assertIn('First part.', chunks[0].delta.content)
        self.assertIn('Last part.', chunks[1].delta.content)
        self.assertTrue(self.agent.conversation_decision.flow.waiting)
        self.assertEqual(self.create.await_count, 2)
        self.assertEqual([s['phase'] for s in states], ['responding', 'continuing', 'continuing', 'waiting'])
        self.assertTrue(all(s['enabled'] for s in states))

    async def test_disabled_continuation_reports_response_and_wait_without_enabling(self):
        states = []
        self.agent.conversation_decision = ConversationDecision(observe_continuation=lambda **s: states.append(s))
        states.clear()
        value = dict(say=[], act=dict(kind='none'))
        self.create.return_value = Obj(usage=None, choices=[Obj(message=Obj(content=json.dumps(value)))])
        with patch.dict('os.environ', {'CIEL_INITIATIVE': '0'}):
            await self.node()
        self.assertEqual(states, [dict(enabled=False, phase='responding'), dict(enabled=False, phase='waiting')])

    def test_initial_setting_and_mode_change_are_visible_without_a_model_request(self):
        from tool_decision import ConversationDecision
        states = []
        control = ConversationDecision(observe_continuation=lambda **s: states.append(s), enabled=True)
        control.configure(False)
        self.assertEqual(states, [dict(enabled=True, phase='waiting'), dict(enabled=False, phase='waiting')])

    async def test_interruption_after_streamed_chunk_stops_continuation(self):
        self.create.return_value = self.answer(dict(kind='none'), 'First part.', next='continue')
        with patch.object(self.agent, '_get_activity_or_raise', return_value=Obj(session=self.session)), \
                patch('models.is_local', return_value=False), patch('models.create_client', return_value=self.client):
            stream = self.agent._pipeline_llm(self.chat, self.agent.tools, {})
            first = await anext(stream)
            self.assertIn('First part.', first.delta.content)
            self.agent.conversation_decision.on_user_state(Obj(new_state='speaking'))
            self.assertEqual([chunk async for chunk in stream], [])
        self.assertEqual(self.create.await_count, 1)

    async def test_service_owned_notice_gets_feedback_without_duplicate_speech(self):
        self.create.return_value = self.answer(dict(kind='load', service_ids=['6']))
        chunks = await self.node()
        await self.dispatch(chunks[0].delta.tool_calls[0])
        loop = self.agent.conversation_decision.loop
        loop.issued['notice'] = 'search_conversation'
        output = llm.FunctionCallOutput(call_id='notice', name='execute_capability', output='{"status":"ok"}',
            is_error=False, reply_required=False)
        event = FunctionToolsExecutedEvent(function_calls=[llm.FunctionCall(call_id='notice', name='execute_capability', arguments='{}')], function_call_outputs=[output])
        self.agent.conversation_decision.feedback(event)
        self.agent.conversation_decision.feedback(event)
        self.assertTrue(event.has_tool_reply)
        self.assertEqual(len(loop.results), 2)
        self.create.return_value = self.answer(dict(kind='complete', evidence=['r2']), 'Already announced')
        chunks = await self.node()
        self.assertEqual(chunks, [])

    async def test_new_speech_does_not_inherit_pending_actions(self):
        self.create.return_value = self.answer(dict(kind='load', service_ids=['6']))
        await self.node()
        old = self.agent.conversation_decision.loop
        self.speech.id = 'turn-2'
        self.create.return_value = self.answer(dict(kind='none'), 'Hello')
        chunks = await self.node()
        self.assertTrue(old.cancelled)
        self.assertEqual(self.agent.conversation_decision.loop.outcome, 'none')
        self.assertIn('Hello', chunks[0].delta.content)
