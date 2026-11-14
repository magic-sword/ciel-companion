"""Session-bound CIEL inference API. Context and inference are owned by the host."""
import asyncio
import copy
import secrets
import time
from dataclasses import dataclass, field

from aiohttp import web

import inference_scheduler

REFERENCE_CHARS = 48000
SESSION_IN_FLIGHT = 8
PREPARE_SECONDS = 120


@dataclass
class CoreSession:
    context: object
    infer: object
    scheduler: object = field(default_factory=inference_scheduler.shared)
    tasks: dict = field(default_factory=dict)
    closed: bool = False
    # Fixed execution material (e.g. Mindcraft command docs), registered once per session.
    reference: str | None = None

    async def _context(self):
        # The host supplies persona, permitted memory and current conversation.
        context = copy.deepcopy(await self.context())
        if self.reference:
            # Keep the fixed material directly after the persona, before history and memory
            # that change between turns, so the inference server can reuse its prompt cache.
            # It is the client's own text in a user message, never system authority.
            at = next((i for i, m in enumerate(context) if m.get('role') != 'system'), len(context))
            context.insert(at, {'role': 'user', 'content': self.reference})
        return context

    def _idle(self):
        if self.closed:
            raise web.HTTPGone()
        if any(not task.done() for task in self.tasks.values()):
            raise web.HTTPConflict(reason='session_busy')

    def set_reference(self, request):
        self._idle()
        if not isinstance(request, dict) or set(request) != {'text'} or not isinstance(request['text'], str):
            raise web.HTTPBadRequest(reason='invalid_reference')
        if not 1 <= len(request['text']) <= REFERENCE_CHARS:
            raise web.HTTPRequestEntityTooLarge(max_size=REFERENCE_CHARS, actual_size=len(request['text']))
        self.reference = request['text']
        return {'status': 'registered', 'chars': len(self.reference)}

    async def prepare(self):
        """Startup preparation: evaluate the fixed prefix once so later requests reuse it.
        Its duration is reported separately from the work that follows."""
        self._idle()
        if not self.reference:
            raise web.HTTPConflict(reason='reference_required')

        async def run():
            began = time.monotonic()
            async with asyncio.timeout(PREPARE_SECONDS), self.scheduler.slot('decision') as queued:
                context = await self._context()
                await self.infer(context, [{'role': 'user', 'content': 'prepare'}],
                                 response_format='text', max_tokens=1, purpose='game_core_prepare',
                                 queued_seconds=queued)
            if self.closed or asyncio.current_task().cancelling():
                raise asyncio.CancelledError()
            return {'status': 'prepared', 'seconds': round(time.monotonic() - began, 3)}

        task = asyncio.create_task(run())
        self.tasks[f'prepare-{len(self.tasks)}'] = task
        return await task

    async def respond(self, request):
        if self.closed:
            raise web.HTTPGone()
        if (not isinstance(request, dict) or not {'request_id', 'messages', 'response_format'} <= set(request)
                or not set(request) <= {'request_id', 'messages', 'response_format', 'priority'}):
            raise web.HTTPBadRequest(reason='invalid_request')
        priority = request.get('priority', 'decision')
        if priority not in inference_scheduler.PRIORITY:
            raise web.HTTPBadRequest(reason='invalid_priority')
        if request['response_format'] not in ('text','json'):
            raise web.HTTPBadRequest(reason='invalid_response_format')
        ident, messages = request['request_id'], request['messages']
        if not isinstance(ident, str) or not 1 <= len(ident) <= 128:
            raise web.HTTPBadRequest(reason='invalid_request_id')
        if not isinstance(messages, list) or not 1 <= len(messages) <= 64:
            raise web.HTTPBadRequest(reason='invalid_messages')
        for message in messages:
            if (not isinstance(message, dict) or set(message) != {'role', 'content'}
                    or message['role'] not in ('user', 'assistant')
                    or not isinstance(message['content'], str)):
                raise web.HTTPBadRequest(reason='invalid_message')
        if sum(len(m['content']) for m in messages) > 64000:
            raise web.HTTPRequestEntityTooLarge(max_size=64000, actual_size=64001)
        # IDs are single-use for the lifetime of a bound session, including failed requests.
        if ident in self.tasks:
            raise web.HTTPConflict(reason='request_id_used')
        if len(self.tasks) >= 1024:
            raise web.HTTPTooManyRequests(reason='session_request_limit')
        # Concurrent requests are accepted, as with hosted LLM APIs; the shared scheduler
        # decides when each runs. Only a runaway client is refused.
        if sum(not task.done() for task in self.tasks.values()) >= SESSION_IN_FLIGHT:
            raise web.HTTPTooManyRequests(reason='session_in_flight_limit')

        async def generate():
            # The deadline covers waiting for a slot as well as inference.
            async with asyncio.timeout(120), self.scheduler.slot(priority) as queued:
                context = await self._context()
                result = await self.infer(context, copy.deepcopy(messages), response_format=request['response_format'],
                                          queued_seconds=queued)
                if self.closed or asyncio.current_task().cancelling():
                    raise asyncio.CancelledError()
                if not isinstance(result, str):
                    raise TypeError('Core inference must return text')
                return {'request_id': ident, 'text': result}

        task = asyncio.create_task(generate())
        self.tasks[ident] = task
        return await task

    async def cancel(self, ident):
        task = self.tasks.get(ident)
        if task is None:
            raise web.HTTPNotFound(reason='unknown_request')
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def close(self):
        self.closed = True
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)


class CielCore:
    def __init__(self, scheduler=None):
        self.sessions = {}
        # Process-wide by default: every bound session competes for the same model slots.
        self.scheduler = scheduler or inference_scheduler.shared()

    def bind(self, *, context, infer):
        """Only the trusted conversation host can bind permitted context and model access."""
        token = secrets.token_urlsafe(32)
        self.sessions[token] = CoreSession(context, infer, self.scheduler)
        return token

    async def release(self, token):
        session = self.sessions.pop(token, None)
        if session:
            await session.close()

    def application(self):
        app = web.Application(client_max_size=300000)

        def session(request):
            authorization = request.headers.get('Authorization', '')
            token = authorization.removeprefix('Bearer ')
            bound = self.sessions.get(token) if authorization.startswith('Bearer ') else None
            if bound is None:
                raise web.HTTPUnauthorized()
            return bound

        async def respond(request):
            bound = session(request)
            try:
                payload = await request.json()
            except (ValueError, UnicodeError):
                raise web.HTTPBadRequest(reason='invalid_json')
            try:
                return web.json_response(await bound.respond(payload))
            except asyncio.CancelledError:
                return web.json_response({'error': 'cancelled'}, status=409)
            except TimeoutError:
                return web.json_response({'error': 'deadline_exceeded'}, status=504)
            except web.HTTPException:
                raise
            except Exception:
                return web.json_response({'error': 'inference_failed'}, status=502)

        async def cancel(request):
            await session(request).cancel(request.match_info['id'])
            return web.json_response({'status': 'cancelled'})

        async def reference(request):
            bound = session(request)
            try:
                payload = await request.json()
            except (ValueError, UnicodeError):
                raise web.HTTPBadRequest(reason='invalid_json')
            return web.json_response(bound.set_reference(payload))

        async def prepare(request):
            bound = session(request)
            try:
                return web.json_response(await bound.prepare())
            except asyncio.CancelledError:
                return web.json_response({'error': 'cancelled'}, status=409)
            except TimeoutError:
                return web.json_response({'error': 'deadline_exceeded'}, status=504)
            except web.HTTPException:
                raise
            except Exception:
                return web.json_response({'error': 'inference_failed'}, status=502)

        async def cleanup(_):
            for token in list(self.sessions):
                await self.release(token)

        app.router.add_post('/v1/respond', respond)
        app.router.add_delete('/v1/requests/{id}', cancel)
        app.router.add_put('/v1/reference', reference)
        app.router.add_post('/v1/prepare', prepare)
        app.on_cleanup.append(cleanup)
        return app
