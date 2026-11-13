import asyncio
import unittest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from ciel_core import CielCore


class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_response_format_is_required_and_validated_before_inference(self):
        core = CielCore()
        seen = []
        async def context(): return []
        async def infer(ctx, messages, *, response_format):
            seen.append(response_format)
            return '{}'
        token = core.bind(context=context, infer=infer)
        bound = core.sessions[token]
        payload = {'request_id':'format','messages':[{'role':'user','content':'observe'}]}
        for invalid in (payload, {**payload,'response_format':'xml'}):
            with self.assertRaises(web.HTTPBadRequest): await bound.respond(invalid)
        await bound.respond({**payload,'response_format':'json'})
        self.assertEqual(seen, ['json'])
        await core.release(token)

    async def test_http_authentication_and_response(self):
        core = CielCore()
        async def context(): return {'persona': 'CIEL'}
        async def infer(ctx, messages, *, response_format): return ctx['persona']
        token = core.bind(context=context, infer=infer)
        async with TestClient(TestServer(core.application())) as client:
            payload = {'response_format':'text', 'request_id': 'http', 'messages': [{'role': 'user', 'content': 'hello'}]}
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
        async def infer(ctx, messages, *, response_format):
            seen.append(ctx)
            ctx['persona'] = 'local copy'
            return ctx['memory']
        token = core.bind(context=context, infer=infer)
        session = core.sessions[token]
        def request(i): return {'response_format':'text', 'request_id': i, 'messages': [{'role': 'user', 'content': 'observe'}]}
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
        async def infer(ctx, messages, *, response_format):
            started.set()
            try: await asyncio.sleep(100)
            except asyncio.CancelledError: return 'late action'
        token = core.bind(context=context, infer=infer)
        session = core.sessions[token]
        response = asyncio.create_task(session.respond({'response_format':'text', 'request_id': 'stop', 'messages': [{'role': 'user', 'content': 'go'}]}))
        await started.wait()
        await session.cancel('stop')
        with self.assertRaises(asyncio.CancelledError): await response
        await core.release(token)

    async def test_reference_follows_persona_and_precedes_changing_context(self):
        core = CielCore()
        history = ['first']
        seen = []
        async def context():
            return [{'role':'system','content':'persona'}, {'role':'user','content':history[-1]}]
        async def infer(ctx, messages, *, response_format='text', max_tokens=256, purpose='game_core'):
            seen.append((ctx, messages, max_tokens, purpose))
            return 'ok'
        token = core.bind(context=context, infer=infer)
        session = core.sessions[token]
        with self.assertRaises(web.HTTPConflict): await session.prepare()
        with self.assertRaises(web.HTTPBadRequest): session.set_reference({'text': 1})
        self.assertEqual(session.set_reference({'text':'command docs'}), {'status':'registered','chars':12})
        result = await session.prepare()
        self.assertEqual(result['status'], 'prepared')
        history.append('second')
        await session.respond({'response_format':'text','request_id':'r','messages':[{'role':'user','content':'stats'}]})
        prefixes = [[m['content'] for m in ctx[:2]] for ctx, *_ in seen]
        self.assertEqual(prefixes, [['persona', '{"type": "execution_reference", "text": "command docs"}']]*2)
        self.assertEqual(seen[1][0][2]['content'], 'second')
        self.assertEqual([(s[2], s[3]) for s in seen], [(1, 'game_core_prepare'), (256, 'game_core')])
        await core.release(token)

    async def test_reference_and_prepare_over_http_and_busy_session(self):
        core = CielCore()
        gate = asyncio.Event()
        async def context(): return [{'role':'system','content':'persona'}]
        async def infer(ctx, messages, **options):
            await gate.wait()
            return 'ok'
        token = core.bind(context=context, infer=infer)
        headers = {'Authorization': 'Bearer ' + token}
        async with TestClient(TestServer(core.application())) as client:
            self.assertEqual((await client.put('/v1/reference', json={'text':'docs'})).status, 401)
            self.assertEqual((await client.put('/v1/reference', json={'text':'docs'}, headers=headers)).status, 200)
            self.assertEqual((await client.put('/v1/reference', json={'text':'x'*48001}, headers=headers)).status, 413)
            preparing = asyncio.create_task(client.post('/v1/prepare', headers=headers))
            while not core.sessions[token].tasks: await asyncio.sleep(0)
            busy = await client.post('/v1/respond', headers=headers, json={'response_format':'text','request_id':'a',
                                                                         'messages':[{'role':'user','content':'go'}]})
            self.assertEqual(busy.status, 409)
            self.assertEqual((await client.put('/v1/reference', json={'text':'new'}, headers=headers)).status, 409)
            gate.set()
            response = await preparing
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())['status'], 'prepared')


if __name__ == '__main__': unittest.main()
