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
