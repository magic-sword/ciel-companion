import asyncio
import unittest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from ciel_core import CielCore


class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_authentication_and_response(self):
        core = CielCore()
        async def context(): return {'persona': 'CIEL'}
        async def infer(ctx, messages): return ctx['persona']
        token = core.bind(context=context, infer=infer)
        async with TestClient(TestServer(core.application())) as client:
            payload = {'request_id': 'http', 'messages': [{'role': 'user', 'content': 'hello'}]}
            response = await client.post('/v1/respond', json=payload)
            self.assertEqual(response.status, 401)
            response = await client.post('/v1/respond', json=payload, headers={'Authorization': 'Bearer ' + token})
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.json(), {'request_id': 'http', 'text': 'CIEL'})
        self.assertFalse(core.sessions)

    async def test_context_is_bound_and_fresh(self):
        core = CielCore()
        state = {'persona': 'CIEL', 'memory': 'first'}
        seen = []
        async def context(): return state
        async def infer(ctx, messages):
            seen.append(ctx)
            ctx['persona'] = 'local copy'
            return ctx['memory']
        token = core.bind(context=context, infer=infer)
        session = core.sessions[token]
        def request(i): return {'request_id': i, 'messages': [{'role': 'user', 'content': 'observe'}]}
        self.assertEqual((await session.respond(request('1')))['text'], 'first')
        state['memory'] = 'second'
        self.assertEqual((await session.respond(request('2')))['text'], 'second')
        self.assertEqual(state['persona'], 'CIEL')
        with self.assertRaises(web.HTTPConflict): await session.respond(request('1'))
        with self.assertRaises(web.HTTPBadRequest): await session.respond({**request('3'), 'person_id': 'other'})
        await core.release(token)
        self.assertNotIn(token, core.sessions)

    async def test_cancel_rejects_even_a_late_backend_result(self):
        core = CielCore()
        started = asyncio.Event()
        async def context(): return {}
        async def infer(ctx, messages):
            started.set()
            try: await asyncio.sleep(100)
            except asyncio.CancelledError: return 'late action'
        token = core.bind(context=context, infer=infer)
        session = core.sessions[token]
        response = asyncio.create_task(session.respond({'request_id': 'stop', 'messages': [{'role': 'user', 'content': 'go'}]}))
        await started.wait()
        await session.cancel('stop')
        with self.assertRaises(asyncio.CancelledError): await response
        await core.release(token)


if __name__ == '__main__': unittest.main()
