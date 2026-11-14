"""試験用の一括切り替え。外部接続なしで SDK の実際の要求も検証する。"""
import json
import unittest
from types import SimpleNamespace
from unittest import mock

import httpx
import openai
from livekit.agents import APIConnectOptions, function_tool, llm
from livekit.plugins import openai as lk_openai

import models


class LocalBackendTest(unittest.IsolatedAsyncioTestCase):
    async def test_default_preserves_fixed_system_and_trailing_state(self):
        import mind
        ctx=llm.ChatContext()
        ctx.add_message(role='system',content='fixed')
        ctx.add_message(role='user',content='hello')
        ctx.add_message(role='system',content='state')
        messages,_=mind.local_context(ctx).to_provider_format('openai')
        self.assertEqual([m['role'] for m in messages],['system','user','user'])
        self.assertEqual(messages[0]['content'],'fixed')
        self.assertEqual(messages[-1]['content'],'SYSTEM: state')

    async def test_changing_notes_preserves_fixed_system_and_recovers_real_request(self):
        import mind
        original = llm.ChatContext()
        original.add_message(role='user',content='original request')
        systems=[]
        for note in ('state version 1','state version 2'):
            ctx=llm.ChatContext()
            ctx.add_message(role='system',content='fixed persona')
            ctx.add_message(role='system',content=note)
            call=llm.FunctionCall(call_id='c',name='status',arguments='{}')
            result=llm.FunctionCallOutput(call_id='c',name='status',output='{}',is_error=False)
            ctx.items.extend([call,result]);before=ctx.to_dict()
            out=mind.local_context(ctx,source=original,trailing_notes=True)
            systems.append(out.items[0].text_content)
            self.assertEqual(out.items[1].text_content,'original request')
            self.assertIn(note,out.items[2].text_content)
            self.assertEqual(out.items[2].text_content,'SYSTEM: '+note)
            self.assertEqual(out.items[-2:],[call,result])
            self.assertEqual(ctx.to_dict(),before)
        self.assertEqual(systems,['fixed persona','fixed persona'])

    async def test_local_new_turn_without_notice_does_not_repeat_user_request(self):
        import mind
        ctx = llm.ChatContext()
        ctx.add_message(role='user',content='原木を集めて')
        ctx.add_message(role='assistant',content='確認します')
        messages,_ = mind.local_context(ctx,trailing_notes=True).to_provider_format('openai')
        self.assertEqual([m['role'] for m in messages],['user','assistant','user'])
        self.assertEqual(messages[-1]['content'],'')
        self.assertEqual(ctx.items[-1].role,'assistant')

    async def test_local_autonomous_reply_merges_assistant_history_in_sdk_request(self):
        import mind
        ctx = llm.ChatContext()
        ctx.add_message(role='system',content='instructions')
        ctx.add_message(role='user',content='原木を8個集めて')
        ctx.add_message(role='assistant',content='探します')
        ctx.add_message(role='assistant',content='近くを確かめます')
        ctx.add_message(role='system',content='[内部通知] 現在のタスクを確認する番')
        before = ctx.to_dict()
        requests = []

        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            messages = body['messages']
            self.assertEqual([m['role'] for m in messages],['system','user','assistant','user'])
            self.assertIn('[内部通知]',json.dumps(messages[-1]['content'],ensure_ascii=False))
            self.assertNotIn('原木を8個集めて',json.dumps(messages[-1]['content'],ensure_ascii=False))
            text = json.dumps(messages[-2]['content'],ensure_ascii=False)
            self.assertLess(text.index('探します'),text.index('近くを確かめます'))
            chunk = {'id':'test','object':'chat.completion.chunk','created':0,'model':'local',
                     'choices':[{'index':0,'delta':{'role':'assistant','content':'確認中です'},'finish_reason':'stop'}]}
            return httpx.Response(200,headers={'content-type':'text/event-stream'},
                                  text='data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n')

        client = openai.AsyncOpenAI(base_url=models.LOCAL_URL,api_key='local',
                                   http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        model = lk_openai.LLM(**models.reply_options('none'),client=client)
        try:
            async with model.chat(chat_ctx=mind.local_context(ctx,trailing_notes=True),conn_options=APIConnectOptions(max_retry=0)) as stream:
                chunks = [chunk async for chunk in stream]
            self.assertTrue(chunks)
            self.assertEqual(len(requests),1)
            self.assertEqual(ctx.to_dict(),before)
        finally:
            await model.aclose()
            await client.close()

    async def test_notice_before_first_user_utterance_has_a_nonempty_query(self):
        import mind
        ctx = llm.ChatContext()
        ctx.add_message(role='system',content='persona')
        ctx.add_message(role='system',content='[internal notice] greet the newly connected person')
        before = ctx.to_dict()
        out = mind.local_context(ctx, source=ctx,trailing_notes=True)
        self.assertEqual(out.items[-1].role,'user')
        self.assertIn('[internal notice] greet the newly connected person',out.items[-1].text_content)
        self.assertTrue(out.items[-1].text_content.startswith('SYSTEM: '))
        self.assertEqual(ctx.to_dict(),before)

    async def test_local_assistant_merge_keeps_tool_boundaries(self):
        import mind
        ctx = llm.ChatContext()
        ctx.add_message(role='user',content='原木を集めて')
        ctx.add_message(role='assistant',content='確かめます')
        call = llm.FunctionCall(call_id='call1',name='minecraft_status',arguments='{}')
        result = llm.FunctionCallOutput(call_id='call1',name='minecraft_status',output='{}',is_error=False)
        ctx.items.extend([call,result])
        ctx.add_message(role='assistant',content='原木がありました')
        ctx.add_message(role='assistant',content='集めます')
        ctx.add_message(role='system',content='[内部通知] 続きを確認する番')
        out = mind.local_context(ctx,trailing_notes=True)
        self.assertEqual(out.items[2:4],[call,result])
        self.assertEqual(out.items[-1].role,'user')
        self.assertIn('[内部通知] 続きを確認する番',out.items[-1].text_content)
        self.assertEqual(len(out.items),6)
        self.assertEqual(len(ctx.items),7)

    async def test_local_tool_continuation_recovers_unrecorded_text_request(self):
        import mind
        original = llm.ChatContext()
        original.add_message(role='user',content='原木を8個集めて')
        prepared = llm.ChatContext()
        prepared.add_message(role='system',content='instructions')
        call = llm.FunctionCall(call_id='call1',name='minecraft_status',arguments='{}')
        result = llm.FunctionCallOutput(call_id='call1',name='minecraft_status',output='{}',is_error=False)
        prepared.items.extend([call,result])
        out = mind.local_context(prepared,source=original,trailing_notes=True)
        self.assertEqual(out.items[1].text_content,'原木を8個集めて')
        self.assertEqual(out.items[-2:],[call,result])
        self.assertEqual(len(prepared.items),3)

    async def test_local_context_keeps_fixed_system_and_note_position_and_tool_continuation(self):
        import mind
        ctx = llm.ChatContext()
        ctx.add_message(role='system',content='instructions')
        ctx.add_message(role='user',content='request')
        ctx.add_message(role='system',content='current game state')
        call = llm.FunctionCall(call_id='call1',name='minecraft_status',arguments='{}')
        result = llm.FunctionCallOutput(call_id='call1',name='minecraft_status',output='{}',is_error=False)
        ctx.items.extend([call,result])
        original = list(ctx.items)
        out = mind.local_context(ctx,trailing_notes=True)
        systems = [i for i in out.items if isinstance(i,llm.ChatMessage) and i.role == 'system']
        self.assertEqual(len(systems),1)
        self.assertIs(out.items[0],systems[0])
        self.assertEqual(systems[0].text_content,'instructions')
        self.assertEqual(out.items[2].role,'user')
        self.assertIn('current game state',out.items[2].text_content)
        self.assertEqual(out.items[-2:],[call,result])
        self.assertEqual(ctx.items,original)

    async def test_text_only_local_context_does_not_include_self_portrait(self):
        import mind
        from conversation import Conversation
        ctx = llm.ChatContext()
        ctx.add_message(role='system', content='test')
        ctx.add_message(role='user', content='原木を集めて')
        with mock.patch.object(models,'LOCAL_TEST',True):
            m = mind.Mind(Conversation(),self_image='data:image/png;base64,portrait')
            result = m.build(ctx)
        self.assertFalse(any(isinstance(c,llm.ImageContent) for i in result.items if isinstance(i,llm.ChatMessage) for c in i.content))

    def setUp(self):
        for name, value in [('LOCAL_TEST', True), ('LOCAL_URL', 'http://local-test.invalid/v1'),
                            ('LOCAL_ROLES', set()), ('_local_client', None)]:
            p = mock.patch.object(models, name, value)
            p.start()
            self.addCleanup(p.stop)

    async def test_roles_and_client_need_no_openai_key(self):
        for role in models.CHAT_ROLES:
            self.assertTrue(models.is_local(role), role)
        self.assertFalse(models.is_local('stt'))
        self.assertFalse(models.is_local('research'))
        with mock.patch.dict('os.environ', {}, clear=True):
            client = models.create_client('mind')
        self.assertEqual(str(client.base_url), models.LOCAL_URL + '/')
        await client.close()

    async def test_listener_and_minutes_use_local_options(self):
        import listener
        import minutes
        from conversation import Conversation
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))], usage=None)
        local, cloud = mock.AsyncMock(), mock.AsyncMock()
        local.chat.completions.create.return_value = response
        with mock.patch.object(models, '_local_client', local), mock.patch.object(models, 'create_client', return_value=cloud):
            ear = listener.Listener(None, None, 'test', client=cloud)
            await ear._check('議事録をお願い')
            worker = minutes.Minutes(None, 'test', Conversation(), 'test')
            worker.start()
            meeting = worker.meeting
            await worker._live_update(meeting, [], [])
            await worker._summarize(meeting.started, meeting.started, None, [])
        self.assertEqual(local.chat.completions.create.await_count, 3)
        for call in local.chat.completions.create.call_args_list:
            self.assertEqual(call.kwargs['model'], models.LOCAL_MODEL)
            self.assertNotIn('reasoning_effort', call.kwargs)
            self.assertGreaterEqual(call.kwargs['timeout'], models.LOCAL_TIMEOUT)
        cloud.chat.completions.create.assert_not_called()

    async def test_game_routing_and_learning_never_embed(self):
        import mind
        import router
        from conversation import Conversation
        client = mock.AsyncMock()
        route = router.Router('minecraft', client=client)
        route.start()
        self.assertIsNone(await route.wants_mind('石のピッケルが欲しいな'))
        self.assertEqual(await route.learn('石のピッケルが欲しいな', 'minecraft_act', 'tool'), 'skip')
        client.embeddings.create.assert_not_called()
        body = mock.Mock()
        body.playing.return_value = True
        m = mind.Mind(Conversation(), body=body)
        ctx = llm.ChatContext()
        ctx.add_message(role='user', content='石のピッケルが欲しいな')
        self.assertEqual(await m.second_look(ctx), 'mind')

    async def test_unsupported_services_do_not_call_openai(self):
        from conversation import Conversation
        from eyes import Eyes
        from web_research import WebResearcher
        client = mock.AsyncMock()
        worker = WebResearcher(Conversation(), '', client=client)
        self.assertEqual((await worker.search('調べて', 'call', None))['status'], 'unavailable')
        eye = Eyes(mock.Mock(), client=client)
        self.assertIsNone(eye.receive(b'\xff\xd8\xffimage'))
        self.assertIsNone(eye.see_game(b'\xff\xd8\xffimage'))
        client.responses.create.assert_not_called()
        client.chat.completions.create.assert_not_called()

    async def test_streamed_game_call_and_followup_use_local_endpoint(self):
        requests = []

        @function_tool
        async def minecraft_status() -> str:
            """ゲームの様子を確認する。"""
            return '{}'

        def respond(request):
            self.assertEqual(request.url.host, 'local-test.invalid')
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(body['model'], models.LOCAL_MODEL)
            self.assertNotIn('reasoning_effort', body)
            self.assertEqual(body['chat_template_kwargs'], {'enable_thinking': False})
            if len(requests) == 1:
                self.assertEqual(body['tools'][0]['function']['name'], 'minecraft_status')
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'call1', 'type': 'function',
                         'function': {'name': 'minecraft_status', 'arguments': '{}'}}]}
                finish = 'tool_calls'
            else:
                self.assertTrue(any(m['role'] == 'tool' and m['tool_call_id'] == 'call1' for m in body['messages']))
                delta, finish = {'role': 'assistant', 'content': '確認できました'}, 'stop'
            chunk = {'id': 'test', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'local',
                     'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}
            return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                  text='data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n')

        http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        client = openai.AsyncOpenAI(base_url=models.LOCAL_URL, api_key='local', http_client=http)
        model = lk_openai.LLM(**models.reply_options('none'), client=client)
        ctx = llm.ChatContext()
        ctx.add_message(role='user', content='マイクラの様子を教えて')
        try:
            async with model.chat(chat_ctx=ctx, tools=[minecraft_status], conn_options=APIConnectOptions(max_retry=0)) as stream:
                chunks = [chunk async for chunk in stream]
            calls = [call for chunk in chunks if chunk.delta for call in chunk.delta.tool_calls or []]
            self.assertEqual(calls[0].name, 'minecraft_status')
            ctx.items.append(llm.FunctionCall(call_id='call1', name='minecraft_status', arguments='{}'))
            ctx.items.append(llm.FunctionCallOutput(call_id='call1', name='minecraft_status', output='{}', is_error=False))
            async with model.chat(chat_ctx=ctx, tools=[minecraft_status], conn_options=APIConnectOptions(max_retry=0)) as stream:
                chunks = [chunk async for chunk in stream]
            self.assertIn('確認できました', ''.join(c.delta.content or '' for c in chunks if c.delta))
            self.assertEqual(len(requests), 2)
        finally:
            await model.aclose()
            await client.close()
