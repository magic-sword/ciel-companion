"""Independent authenticated MCP search service. No CIEL runtime imports."""
import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hmac
import os
import time
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.responses import JSONResponse
import uvicorn

from approved_search import async_search, source_policy
from contract import SearchReply


class SearchEngine:
    def __init__(self, source, contact, provider=async_search):
        source_policy(source)
        self.source, self.contact, self.provider = source, contact, provider
        self.lock = asyncio.Lock()
        self.retry_until = 0.0

    async def search(self, query, limit):
        base = dict(coverage=self.source, content_kind='search_snippets',
                    retrieved_at=datetime.now(timezone.utc), results=[])
        async with asyncio.timeout(30):
            async with self.lock:
                if time.monotonic() < self.retry_until:
                    return SearchReply(**base, status='rate_limited', reason='cooldown',
                                       retry_after_seconds=int(self.retry_until - time.monotonic()) + 1)
                try:
                    raw = await self.provider(self.source, query, limit, self.contact)
                except ValueError:
                    return SearchReply(**base, status='unavailable', reason='configuration_or_policy')
                if raw['status'] in ('rate_limited', 'api_error', 'http_error'):
                    delay = 60.0
                    value = raw.get('retry_after')
                    try:
                        delay = max(delay, float(value))
                    except (ValueError, TypeError):
                        if value:
                            try:
                                delay = max(delay, parsedate_to_datetime(value).timestamp() - time.time())
                            except (ValueError, TypeError, OverflowError):
                                pass
                    self.retry_until = time.monotonic() + delay
                    return SearchReply(**base, status='rate_limited', reason='provider_throttled',
                                       retry_after_seconds=int(delay) + 1)
                if raw['status'] not in ('ok', 'no_results'):
                    return SearchReply(**base, status='failed', reason='provider_failed')
                return SearchReply(**{**base, 'retrieved_at': raw['retrieved_at'], 'results': raw['results']},
                                   status=raw['status'])


class BearerOnly:
    def __init__(self, app, token):
        if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
            raise ValueError('SEARCH_API_TOKEN must be a random ASCII token of at least 32 characters')
        self.app, self.expected = app, ('Bearer ' + token).encode('ascii')

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            if scope['path'] == '/health' and scope['method'] == 'GET':
                await JSONResponse({'status': 'ok', 'api_version': 1})(scope, receive, send)
                return
            headers = [v for k, v in scope['headers'] if k.lower() == b'authorization']
            if len(headers) != 1 or not hmac.compare_digest(headers[0], self.expected):
                await JSONResponse({'error': 'unauthorized'}, status_code=401,
                                   headers={'WWW-Authenticate': 'Bearer'})(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(token, engine):
    mcp = FastMCP('approved-search', host='127.0.0.1', json_response=True,
                  max_request_body_size=16384, max_sessions=64, session_idle_timeout=90,
                  transport_security=TransportSecuritySettings(
                      allowed_hosts=['127.0.0.1:*', 'localhost:*'], allowed_origins=[]))

    @mcp.tool(name='search', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
              description='Search public information. Coverage and evidence type are returned explicitly.')
    async def search(query: Annotated[str, Field(min_length=1, max_length=600)],
                     limit: Annotated[int, Field(ge=1, le=5)] = 3) -> SearchReply:
        try:
            return await engine.search(query.strip(), limit)
        except TimeoutError:
            return SearchReply(status='failed', coverage=engine.source, content_kind='search_snippets',
                               retrieved_at=datetime.now(timezone.utc), results=[], reason='timeout')
        except Exception:
            # Never expose HTTP exceptions, user-agent contact, tokens or provider diagnostics.
            return SearchReply(status='failed', coverage=engine.source, content_kind='search_snippets',
                               retrieved_at=datetime.now(timezone.utc), results=[], reason='provider_failed')

    return BearerOnly(mcp.streamable_http_app(), token)


if __name__ == '__main__':
    engine = SearchEngine(os.getenv('SEARCH_SOURCE', 'wikipedia-ja'), os.environ['SEARCH_CONTACT'])
    app = create_app(os.environ['SEARCH_API_TOKEN'], engine)
    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('SEARCH_PORT', '8780')),
                access_log=False, log_level='warning')
