"""Session-bound CIEL inference API. Context and inference are owned by the host."""
import asyncio
import copy
import secrets
from dataclasses import dataclass, field

from aiohttp import web


@dataclass
class CoreSession:
    context: object
    infer: object
    tasks: dict = field(default_factory=dict)
    closed: bool = False

    async def respond(self, request):
        if self.closed:
            raise web.HTTPGone()
        if not isinstance(request, dict) or set(request) != {'request_id', 'messages'}:
            raise web.HTTPBadRequest(reason='invalid_request')
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
        if any(not task.done() for task in self.tasks.values()):
            raise web.HTTPConflict(reason='session_busy')

        async def generate():
            async with asyncio.timeout(120):
                # The host supplies persona, permitted memory and current conversation.
                context = copy.deepcopy(await self.context())
                result = await self.infer(context, copy.deepcopy(messages))
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
    def __init__(self):
        self.sessions = {}

    def bind(self, *, context, infer):
        """Only the trusted conversation host can bind permitted context and model access."""
        token = secrets.token_urlsafe(32)
        self.sessions[token] = CoreSession(context, infer)
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

        async def cleanup(_):
            for token in list(self.sessions):
                await self.release(token)

        app.router.add_post('/v1/respond', respond)
        app.router.add_delete('/v1/requests/{id}', cancel)
        app.on_cleanup.append(cleanup)
        return app
