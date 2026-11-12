import asyncio
import json
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import AsyncMock, Mock, patch

from livekit.agents import RunContext, ToolError, ToolResult, function_tool
from livekit.agents.llm import FunctionCall, utils

import mind
import tools
from capabilities import CapabilityCatalog
from session_mcp import SessionMCP
from persona import load_persona


def context(**userdata):
    return RunContext(session=Obj(userdata=Obj(**userdata), _global_run_state=None),
                      speech_handle=Obj(num_steps=1),
                      function_call=FunctionCall(call_id='test-call', name='test', arguments='{}'))


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = CapabilityCatalog(tools.MODULES)
        self.all = tools.TOOLS + [self.catalog.loader, self.catalog.executor]

    def ids(self, eligible=None):
        return {t.id for t in self.catalog.select(eligible or self.all)}

    def test_initial_catalog_has_summaries_without_domain_schemas(self):
        self.assertEqual(self.ids(), {'current_time', 'stop_game_task', 'game_task_status', 'load_capabilities',
                                     'finish_minutes', 'get_minutes_status', 'execute_capability',
                                     'register_participant_name', 'get_speaker_status'})
        summary = json.loads(self.catalog.summary())
        self.assertEqual(len(summary['services']), 7)  # app is not connected
        self.assertNotIn('remember_about_speaker', self.catalog.summary())
        self.assertNotIn('inputSchema', self.catalog.summary())

    def test_one_selection_loads_multiple_services_and_does_not_execute(self):
        self.ids()
        self.assertEqual(self.catalog.load(['3', '4'])['status'], 'loaded')
        visible = self.ids()
        self.assertNotIn('remember_about_speaker', visible)
        self.assertNotIn('research_web', visible)
        self.assertTrue(self.catalog.can_execute('remember_about_speaker'))
        self.assertTrue(self.catalog.can_execute('research_web'))
        self.assertNotIn('start_listening_to_song', visible)

    def test_unknown_or_disconnected_selection_is_atomic(self):
        self.ids()
        for ids in ([], ['3', '8'], ['3', '3'], [3], ['1', '2', '3', '4']):
            self.assertNotEqual(self.catalog.load(ids)['status'], 'loaded')
            self.assertFalse(self.catalog.loaded)

    def test_lru_bound_and_session_isolation(self):
        self.ids()
        self.catalog.load(['3', '4', '5'])
        self.catalog.load(['3'])
        self.catalog.load(['2'])
        self.assertEqual(list(self.catalog.loaded), ['minutes', 'memory', 'karaoke'])
        self.assertFalse(CapabilityCatalog(tools.MODULES).loaded)

    def test_comment_permissions_still_apply_after_loading(self):
        self.ids()
        self.catalog.load(['3'])
        allowed = tools.for_comments(tools.TOOLS) + [self.catalog.loader]
        visible = self.ids(allowed)
        self.assertTrue(self.catalog.can_execute('people_here'))
        self.assertNotIn('remember_about_speaker', visible)
        self.assertNotIn('recall_about_speaker', visible)
        self.assertNotIn('stop_game_task', visible)

    def test_disconnect_and_unclassified_tools_fail_closed(self):
        self.ids()
        self.catalog.load(['4'])
        self.catalog.disabled = {'research'}
        visible = self.ids(self.all + [Obj(id='unknown_tool')])
        self.assertNotIn('research_web', visible)
        self.assertNotIn('unknown_tool', visible)
        self.assertNotIn('4', [s['id'] for s in json.loads(self.catalog.summary())['services']])

    def test_external_tools_are_deferred_but_stop_is_immediate(self):
        external = Obj(id='minecraft_look')
        self.catalog.bind_external([external], 'game')
        eligible = self.all + [external]
        self.assertNotIn(external.id, self.ids(eligible))
        self.catalog.load(['1'])
        self.assertNotIn(external.id, self.ids(eligible))
        self.assertIn('stop_game_task', self.ids(eligible))

    def test_external_replacement_cannot_shadow_a_host_tool(self):
        with self.assertRaises(ValueError):
            self.catalog.bind_external([Obj(id='remember_about_speaker')], 'app')
        self.catalog.bind_external([Obj(id='old_app_tool')], 'app')
        self.catalog.bind_external([Obj(id='new_app_tool')], 'app')
        self.assertNotIn('old_app_tool', self.catalog.external)

    def test_existing_stream_guard_blocks_unloaded_registered_tools(self):
        visible = self.catalog.select(self.all)
        chunk = mind.llm.ChatChunk(id='test', delta=mind.llm.ChoiceDelta(
            role='assistant', tool_calls=[mind.llm.FunctionToolCall(
                name='remember_about_speaker', arguments='{}', call_id='test')]))
        _, dropped = mind.only_given(chunk, visible)
        self.assertEqual(dropped, ['remember_about_speaker'])

    def test_discovery_prompt_is_loaded_and_fingerprinted(self):
        from dataclasses import replace
        p = load_persona()
        self.assertIn('load_capabilities', p.tool_discovery_instructions)
        self.assertNotEqual(p.fingerprint, replace(p, tool_discovery_instructions='changed').fingerprint)


class MCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.catalog = CapabilityCatalog(tools.MODULES)
        self.bridge = SessionMCP(self.catalog)
        self.all = tools.TOOLS + [self.catalog.loader]
        self.catalog.select(self.all)
        self.catalog.load(['3', '2', '7'])
        self.catalog.select(self.all)

    async def test_real_mcp_keeps_trusted_actor_out_of_model_arguments(self):
        person = Obj(person_id=42, name='本人', notes_ok=True)
        book = Obj(refresh=AsyncMock(), current_person=Mock(return_value=person))
        notes = Obj(request=Mock())
        fn = self.bridge.wrap(tools.memory.remember_about_speaker)
        schema = fn.info.raw_schema
        self.assertEqual(set(schema['parameters']['properties']), {'note'})
        ctx = context(book=book, notes=notes)
        result = await fn({'note': '猫が好き'}, ctx)
        self.assertIsInstance(result, ToolResult)
        self.assertFalse(result.reply_required)
        self.assertEqual(result.output['status'], 'queued')
        notes.request.assert_called_once_with(42, '猫が好き')
        book.refresh.assert_awaited_once()

    async def test_generic_executor_preserves_real_mcp_consent_and_no_reply_result(self):
        wrapped = [self.bridge.wrap(t) for t in tools.TOOLS]
        self.catalog.select(wrapped + [self.catalog.loader, self.catalog.executor])
        result = self.catalog.load(['3'])
        definition = next(t for s in result['definitions'] for t in s['tools'] if t['tool_id']=='remember_about_speaker')
        self.assertIn('parameters', definition['schema'])
        self.assertNotIn('person_id',definition['schema']['parameters']['properties'])
        person=Obj(person_id=42,name='本人',notes_ok=True)
        book=Obj(refresh=AsyncMock(),current_person=Mock(return_value=person))
        notes=Obj(request=Mock())
        arguments={'tool_id':definition['tool_id'],'version':definition['version'],'arguments':{'note':'猫が好き'}}
        returned=await self.catalog.executor(arguments,context(book=book,notes=notes))
        self.assertFalse(returned.reply_required)
        self.assertEqual(returned.output['status'],'queued')
        notes.request.assert_called_once_with(42,'猫が好き')
        for invalid in ({**arguments,'version':'old'}, {**arguments,'arguments':{'note':123}},
                        {**arguments,'arguments':{'note':'secret','person_id':99}}, {**arguments,'person_id':99}):
            with self.assertRaises(ToolError):
                await self.catalog.executor(invalid,context(book=book,notes=notes))
        self.catalog.select(tools.for_comments(wrapped)+[self.catalog.loader,self.catalog.executor])
        with self.assertRaises(ToolError):
            await self.catalog.executor(arguments,context(book=book,notes=notes))
        notes.request.assert_called_once()

    async def test_definition_and_fixed_prefix_do_not_change_when_loading(self):
        from agent import Ciel
        with patch('agent.PIPELINE',True):
            agent=Ciel()
            catalog=agent.capabilities
            before={f.id for f in catalog.select(agent.tools)}
            instructions=agent.instructions_for('normal','solo')
            summary=catalog.summary()
            loaded=catalog.load(['3','6'])
            self.assertTrue(loaded['definitions'][0]['instructions'])
            self.assertEqual(before,{f.id for f in catalog.select(agent.tools)})
            self.assertEqual(instructions,agent.instructions_for('normal','solo'))
            self.assertEqual(summary,catalog.summary())

    async def test_pipeline_places_catalog_before_changing_turn_notes(self):
        from agent import Ciel
        from conversation import Conversation
        from livekit.agents import Agent, llm
        from tools import State
        with patch('agent.PIPELINE',True):
            agent=Ciel()
        history=Conversation()
        agent.mind=mind.Mind(history)
        agent.style=Obj(talk='normal',presence='solo')
        state=State(history=history)
        session=Obj(userdata=state,current_speech=Obj(id='test',num_steps=1),_global_run_state=None)
        seen=[]
        async def capture(owner,ctx,functions,settings):
            seen.append(ctx)
            yield llm.ChatChunk(id='test',delta=llm.ChoiceDelta(role='assistant',content='ok'))
        with patch.object(agent,'_get_activity_or_raise',return_value=Obj(session=session)), \
                patch.object(Agent.default,'llm_node',capture),patch('agent.models.is_local',return_value=True):
            for suffix in ('state-A','state-B'):
                chat=llm.ChatContext()
                chat.add_message(role='system',content=agent.instructions)
                chat.add_message(role='user',content='hello')
                chat.add_message(role='system',content=suffix)
                _=[c async for c in agent._pipeline_llm(chat,agent.tools,{})]
                self.assertEqual(chat.items[-1].text_content,suffix)
        prefix=agent.instructions_for('normal','solo')+'\n\n'+agent.capabilities.summary()
        for ctx,suffix in zip(seen,('state-A','state-B')):
            self.assertEqual(ctx.items[0].text_content,prefix)
            self.assertEqual(ctx.items[-1].role,'user')
            self.assertEqual(json.loads(ctx.items[-1].text_content.split('\n',1)[1])['text'],suffix)
            self.assertEqual(ctx.items[0].text_content.count(agent.capabilities.summary()),1)

    async def test_executor_refuses_definition_changed_after_discovery(self):
        self.catalog.select(self.all)
        self.catalog.load(['3'])
        definition=self.catalog.definition('remember_about_speaker')
        self.catalog.instructions['memory']='new instructions'
        with self.assertRaises(ToolError):
            await self.catalog.executor({'tool_id':definition['tool_id'],'version':definition['version'],
                'arguments':{'note':'test'}},context())

    async def test_executor_and_stream_guard_limit_body_operations(self):
        calls=[]
        @function_tool
        async def body(context: RunContext):
            """Move a fixture body."""
            calls.append('moved')
            return 'ok'
        self.catalog.bind_external([body],'app')
        self.catalog.select(self.all+[body,self.catalog.executor])
        self.catalog.load(['8'])
        definition=self.catalog.definition(body.id)
        values={'tool_id':body.id,'version':definition['version'],'arguments':{}}
        self.catalog.moving={body.id}
        ctx=context()
        self.assertEqual(await self.catalog.executor(values,ctx),'ok')
        with self.assertRaises(ToolError):
            await self.catalog.executor(values,ctx)
        self.assertEqual(calls,['moved'])
        chunk=mind.llm.ChatChunk(id='test',delta=mind.llm.ChoiceDelta(role='assistant',tool_calls=[
            mind.llm.FunctionToolCall(name=self.catalog.executor.id,arguments=json.dumps(values),call_id='first'),
            mind.llm.FunctionToolCall(name=self.catalog.executor.id,arguments=json.dumps(values),call_id='second')]))
        kept,dropped=mind.one_body_call(chunk,[],{body.id},target=self.catalog.target)
        self.assertEqual(len(kept.delta.tool_calls),1)
        self.assertEqual(dropped,[body.id])
        malformed=Obj(name=self.catalog.executor.id,arguments='{"tool_id":[]}')
        self.assertEqual(self.catalog.target(malformed),self.catalog.executor.id)

    async def test_mcp_rejects_injected_actor_and_wrong_argument_types(self):
        fn = self.bridge.wrap(tools.memory.remember_about_speaker)
        notes = Obj(request=Mock())
        for arguments in ({'note': 'secret', 'person_id': 99}, {'note': 123}, {}):
            with self.assertRaises(ToolError):
                await fn(arguments, context(book=None, notes=notes))
        notes.request.assert_not_called()

    async def test_refreshed_consent_and_identity_are_required(self):
        person = Obj(person_id=42, name='本人', notes_ok=False)
        book = Obj(refresh=AsyncMock(), current_person=Mock(return_value=person))
        notes = Obj(request=Mock())
        fn = self.bridge.wrap(tools.memory.remember_about_speaker)
        result = await fn({'note': '猫が好き'}, context(book=book, notes=notes))
        self.assertEqual(result.output['status'], 'consent_required')
        book.current_person.return_value = None
        result = await fn({'note': '猫が好き'}, context(book=book, notes=notes))
        self.assertEqual(result.output['status'], 'unidentified')
        notes.request.assert_not_called()

    async def test_loading_never_overrides_new_origin_permissions(self):
        fn = self.bridge.wrap(tools.memory.remember_about_speaker)
        self.catalog.select(tools.for_comments(self.all))
        with self.assertRaises(ToolError):
            await fn({'note': 'secret'}, context(book=None, notes=None))

    async def test_real_sdk_argument_preparation_and_no_reply_flag(self):
        fn = self.bridge.wrap(tools.singing.start_listening_to_song)
        song = Obj(start=Mock(return_value='started'))
        ctx = context(song=song)
        args, kwargs = utils.prepare_function_arguments(fnc=fn, json_arguments='{}', call_ctx=ctx)
        result = await fn(*args, **kwargs)
        self.assertFalse(result.reply_required)
        song.start.assert_called_once()

    async def test_cancel_reaches_domain_operation(self):
        started, cancelled = asyncio.Event(), asyncio.Event()

        @function_tool
        async def wait(context: RunContext):
            """Test cancellation of a domain call."""
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.catalog.exposed.add(wait.id)
        task = asyncio.create_task(self.bridge.wrap(wait)({}, context()))
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(cancelled.wait(), 3)

    async def test_large_results_are_explicitly_truncated(self):
        @function_tool
        async def large(context: RunContext):
            """Return a deliberately large result."""
            return 'x' * 20000

        self.catalog.exposed.add(large.id)
        result = await self.bridge.wrap(large)({}, context())
        self.assertTrue(result.output['clipped'])
        self.assertEqual(result.output['status'], 'truncated')
        self.assertLess(len(json.dumps(result.output)), 16000)
