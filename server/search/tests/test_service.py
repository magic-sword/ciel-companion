import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

import httpx
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'server/search'))
sys.path.insert(0, str(ROOT / 'server/agent'))
from service import SearchEngine, create_app
from contract import SearchReply
from research_service import request_search, validate_reply, SCHEMA

TOKEN = 'test-token-' + 'a' * 40


class SearchAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        async def provider(source, query, limit, contact):
            self.calls.append((source, query, limit))
            return dict(status='ok', retrieved_at=datetime.now(timezone.utc).isoformat(), results=[dict(
                title='Example', url='https://example.org/', snippet='A fact', attribution='Contributor',
                license_url='https://example.org/license', history_url=None)])
        self.engine = SearchEngine('wikipedia-ja', 'test@example.org', provider)
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(create_app(TOKEN, self.engine),
                                    log_level='critical', access_log=False))
        self.task = asyncio.create_task(self.server.serve(sockets=[self.sock]))
        for _ in range(100):
            if self.server.started:
                break
            await asyncio.sleep(.01)
        self.url = f'http://127.0.0.1:{self.port}/mcp'
        self.env = patch.dict('os.environ', CIEL_SEARCH_URL=self.url, CIEL_SEARCH_TOKEN=TOKEN)
        self.env.start()

    async def asyncTearDown(self):
        self.env.stop()
        self.server.should_exit = True
        await asyncio.wait_for(self.task, 5)
        self.sock.close()

    async def test_auth_required_before_provider_access(self):
        async with httpx.AsyncClient() as client:
            for token in ('', 'Bearer wrong'):
                response = await client.post(self.url, headers={'Authorization': token}, json={})
                self.assertEqual(response.status_code, 401)
        self.assertEqual(self.calls, [])

    async def test_real_mcp_roundtrip_and_schema(self):
        result = await request_search('example', 3)
        self.assertEqual(result['version'], 1)
        self.assertEqual(result['coverage'], 'wikipedia-ja')
        self.assertEqual(result['results'][0]['attribution'], 'Contributor')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(SCHEMA, SearchReply.model_json_schema())
        with self.assertRaises(Exception):
            validate_reply({**result, 'version': 0})

    async def test_invalid_tool_arguments_never_reach_provider(self):
        async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + TOKEN}) as http:
            async with streamable_http_client(self.url, http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool('search', {'query': 'x', 'limit': 99})
                    self.assertTrue(result.isError)
        self.assertFalse(self.calls)

    async def test_cancellation_closes_remote_provider(self):
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def slow(*args):
            started.set()
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()
        self.engine.provider = slow
        task = asyncio.create_task(request_search('slow', 1))
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(cancelled.wait(), 3)

    async def test_rate_limit_is_shared_across_sessions(self):
        async def limited(*args):
            self.calls.append(args)
            return dict(status='rate_limited', retry_after='120')
        self.engine.provider = limited
        for _ in range(2):
            result = await request_search('example', 1)
            self.assertEqual(result['status'], 'rate_limited')
            self.assertGreater(result['retry_after_seconds'], 100)
        self.assertEqual(len(self.calls), 1)

    async def test_provider_error_does_not_leak_details(self):
        async def broken(*args):
            raise RuntimeError('secret-private-diagnostic')
        self.engine.provider = broken
        result = await request_search('example', 1)
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('secret-private', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
