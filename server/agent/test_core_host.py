import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from core_host import CoreHost
from aiohttp import ClientSession


class HostTests(unittest.IsolatedAsyncioTestCase):
    async def test_execution_json_format_reaches_model_without_changing_request(self):
        create = AsyncMock(return_value=SimpleNamespace(usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"item":"wooden_pickaxe"}'))]))
        client = SimpleNamespace(close=AsyncMock(), chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch('core_host.models.create_client', return_value=client):
            host = CoreHost(SimpleNamespace(persona=SimpleNamespace(execution_instructions='execution format')), None, record=lambda *a, **k: None)
        with patch('core_host.models.is_local', return_value=False), \
             patch('core_host.models.options', side_effect=lambda role, **kw: kw), \
             patch('core_host.models.record'):
            result = await host.infer([{'role':'system','content':'shared identity'}],
                [{'role':'user','content':'craft a wooden pickaxe'}], response_format='json')
        self.assertIn('wooden_pickaxe', result)
        options = create.call_args.kwargs
        self.assertEqual(options['response_format'], {'type':'json_object'})
        self.assertEqual(options['messages'][-1]['content'], 'craft a wooden pickaxe')
        await host.close()

    async def test_bound_http_uses_current_persona_memory_and_conversation(self):
        client = SimpleNamespace(close=AsyncMock())
        turns = [SimpleNamespace(role='user', name='owner', text='remember this request')]
        agent = SimpleNamespace(persona=SimpleNamespace(execution_instructions='execution format'),style=SimpleNamespace(talk='normal', presence='solo'),
            instructions_for=lambda *args, **kwargs: 'shared CIEL persona',
            mind=SimpleNamespace(_recent=lambda n: turns))
        book = SimpleNamespace(greeting_context=AsyncMock(return_value='permitted owner memory'))
        with patch('core_host.models.create_client', return_value=client):
            host = CoreHost(agent, book)
        received = []
        async def infer(context, messages, *, response_format, **options):
            received.append((context,messages))
            return '!inventory'
        host.infer = infer
        url, token = await host.start()
        try:
            async with ClientSession() as http:
                async with http.post(url+'/v1/respond', headers={'Authorization':'Bearer '+token},
                    json={'response_format':'text', 'request_id':'bound','messages':[{'role':'user','content':'game observation'}]}) as response:
                    self.assertEqual(response.status,200)
                    self.assertEqual((await response.json())['text'],'!inventory')
            context = str(received[0][0])
            self.assertIn('shared CIEL persona',context)
            self.assertIn('permitted owner memory',context)
            self.assertIn('remember this request',context)
            book.greeting_context.assert_awaited_with(True)
        finally: await host.close()
        client.close.assert_awaited_once()
