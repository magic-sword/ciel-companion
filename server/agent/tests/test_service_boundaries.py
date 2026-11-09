import asyncio
import json
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import AsyncMock, Mock, patch

from livekit.agents import ToolError
from mcp import ClientSession

import app_env
import board
import curiosity
import tools
from capabilities import CapabilityCatalog
from conversation import Conversation
from image_analysis import ImageAnalysis
from initiative import Thought
from memory_jobs import run_memory_job
from notes import NoteTaker
from service_mcp import ServiceError, call_service
from session_mcp import SessionMCP
from web_research import WebResearcher
from youtube_source import read_youtube


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_validation_prevents_backend_side_effects(self):
        handler = AsyncMock(return_value='ok')
        with self.assertRaises(ServiceError):
            await call_service('test', 'empty', handler, arguments={'person_id': 99})
        handler.assert_not_awaited()

    async def test_private_failure_text_does_not_reach_mcp_result(self):
        replies = []
        original = ClientSession.call_tool
        async def capture(client, *args, **kwargs):
            result = await original(client, *args, **kwargs)
            replies.append(result)
            return result
        handler = AsyncMock(side_effect=ValueError('private credential'))
        with patch.object(ClientSession, 'call_tool', capture):
            with self.assertRaisesRegex(ValueError, 'private credential'):
                await call_service('test', 'fail', handler)
        self.assertTrue(replies[0].isError)
        self.assertNotIn('private credential', replies[0].model_dump_json())

    async def test_deadline_cancels_backend_without_leaking_tasks(self):
        cancelled = asyncio.Event()
        async def slow(arguments):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        with self.assertRaises(TimeoutError):
            await call_service('test', 'slow', slow, timeout=.1)
        self.assertTrue(cancelled.is_set())

    async def test_worker_memory_operations_are_not_model_tools(self):
        handler = AsyncMock(return_value=False)
        self.assertIs(await run_memory_job('consolidate_notes', handler), False)
        self.assertNotIn('consolidate_notes', {t.id for t in tools.TOOLS})
        with self.assertRaises(ValueError):
            await run_memory_job('raw_sql', handler)
        self.assertEqual(handler.await_count, 1)

    async def test_autonomous_research_uses_the_same_mcp_provider(self):
        citation = Obj(type='url_citation', url='https://example.org/', title='Source', start_index=0, end_index=1)
        response = Obj(status='completed', output=[Obj(type='web_search_call', status='completed'),
            Obj(type='message', content=[Obj(type='output_text', text='answer', annotations=[citation])])])
        client = Obj(responses=Obj(create=AsyncMock(return_value=response)), close=AsyncMock())
        researcher = WebResearcher(Conversation(), 'instructions', client=client)
        say = Mock()
        worker = curiosity.Curiosity(researcher, board.Board(), say, 'FOUND', style=Obj(talk='normal'))
        thought = Thought('気になる', 'research', 4.0, query='質問')
        with patch('models.LOCAL_TEST', False), patch('service_mcp.debug_log.record') as trace:
            self.assertTrue(worker.offer(thought))
            await worker._task
        self.assertEqual(researcher.history.research.records[0].status, 'completed')
        self.assertTrue(any(c.kwargs.get('service') == 'research' and
                            c.kwargs.get('operation') == 'search_web' for c in trace.call_args_list))
        say.assert_called_once()

    async def test_cancelled_memory_generation_restores_save_and_forget_requests(self):
        started = asyncio.Event()
        async def generate(**kwargs):
            started.set()
            await asyncio.Event().wait()
        client = Obj(chat=Obj(completions=Obj(create=generate)))
        store = Obj(memory_snapshot=AsyncMock(return_value={
            'consent': True, 'name': '本人', 'notes': [], 'forgets': []}), apply_notes=AsyncMock())
        book = Obj(store=store, known=[Obj(person_id=1, notes_ok=True)])
        with patch('models.create_client', return_value=client), patch('models.client_for', return_value=client):
            worker = NoteTaker(book, 'instructions', Conversation())
            worker._requested[1], worker._forgets[1] = ['覚える内容'], ['忘れる内容']
            task = asyncio.create_task(worker._write_once(1))
            await asyncio.wait_for(started.wait(), 3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(worker._requested[1], ['覚える内容'])
        self.assertEqual(worker._forgets[1], ['忘れる内容'])
        store.apply_notes.assert_not_awaited()

    async def test_image_refs_are_resolved_and_expired_refs_do_not_infer(self):
        response = Obj(choices=[Obj(message=Obj(content='a short caption'))])
        client = Obj(chat=Obj(completions=Obj(create=AsyncMock(return_value=response))))
        resolve = Mock(return_value='data:image/jpeg;base64,fixture')
        service = ImageAnalysis('instructions', resolve, lambda: client)
        with patch('models.LOCAL_TEST', False), patch('models.client_for', return_value=client):
            result = await service.describe('picture-1')
            self.assertEqual(result, {'status': 'completed', 'caption': 'a short caption'})
            resolve.assert_called_with('picture-1')
            resolve.return_value = None
            self.assertEqual((await service.describe('picture-1'))['status'], 'not_retained')
        self.assertEqual(client.chat.completions.create.await_count, 1)

    async def test_local_image_backend_is_explicitly_unavailable(self):
        resolve = Mock()
        with patch('models.LOCAL_TEST', True):
            result = await ImageAnalysis('instructions', resolve, Mock()).describe('image')
        self.assertEqual(result['status'], 'unavailable')
        resolve.assert_not_called()

    async def test_app_raw_schema_is_checked_before_sending_to_device(self):
        catalog = CapabilityCatalog(tools.MODULES)
        sent = []
        async def send(message):
            sent.append(message)
            app.on_data(Obj(topic='ciel.app', data=json.dumps({
                'type': 'app.result', 'id': message['id'], 'result': {'status': 'ok'}}).encode()))
        app = app_env.AppEnv(send)
        app.on_data(Obj(topic='ciel.app', data=json.dumps({'type': 'app.hello', 'tools': [{
            'name': 'app_show_card', 'inputSchema': {'type': 'object', 'properties': {'title': {'type': 'string'}},
                                                   'required': ['title']}}]}).encode()))
        catalog.bind_external(app.tools, 'app')
        wrapped = SessionMCP(catalog).wrap(app.tools[0])
        eligible = [wrapped, catalog.loader]
        catalog.select(eligible)
        catalog.load(['8'])
        catalog.select(eligible)
        result = await wrapped({'title': 'test'}, None)
        self.assertEqual(json.loads(result.output)['status'], 'ok')
        with self.assertRaises(ToolError):
            await wrapped({'title': 123}, None)
        self.assertEqual(len(sent), 1)

    async def test_youtube_service_cannot_be_used_as_arbitrary_http_client(self):
        http = Obj(get=Mock())
        with self.assertRaises(ValueError):
            await read_youtube(http, 'https://example.org', 'private', '../admin', {}, timeout=1)
        http.get.assert_not_called()
