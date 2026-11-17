"""Reviewed API search through MCP; no model requests or result-page crawling."""
import os
import time
import asyncio
from email.utils import parsedate_to_datetime

from approved_search import async_search
from service_mcp import call_service

_search_lock = asyncio.Lock()
_retry_until = 0.0


async def collect(question):
    global _retry_until
    async with _search_lock:
        if time.monotonic() < _retry_until:
            raise ValueError('search_cooldown')
        result = await async_search('wikipedia-ja', question, 3, os.environ.get('CIEL_SEARCH_CONTACT'))
        if result['status'] in ('rate_limited', 'api_error', 'http_error'):
            delay = 60.0
            value = result.get('retry_after')
            try:
                delay = max(delay, float(value))
            except (ValueError, TypeError):
                if value:
                    try:
                        delay = max(delay, parsedate_to_datetime(value).timestamp() - time.time())
                    except (ValueError, TypeError, OverflowError):
                        pass
            _retry_until = time.monotonic() + delay
        return result


class ResearchService:
    def __init__(self, timeout=45):
        self.timeout = timeout

    async def search(self, question, requested_at):
        async def execute(arguments):
            result = await collect(arguments['question'])
            if result['status'] not in ('ok', 'no_results'):
                raise ValueError('approved_search_failed:' + result['status'])
            sources, chunks = [], ['日本語Wikipediaの検索概要。記事本文は未取得。']
            for row in result['results']:
                number = len(sources) + 1
                sources.append(dict(number=number, title=row['title'] + ' — Wikipedia contributors', url=row['url']))
                chunks.append(f"[{number}] {row['title']}: {row['snippet']}")
            if sources:
                number = len(sources) + 1
                sources.append(dict(number=number, title='CC BY-SA 4.0', url=result['policy']['license_url']))
                chunks.append(f'出典: Wikipedia contributors / CC BY-SA 4.0 [{number}]。概要はHTML除去・長さ制限済み。')
            else:
                chunks.append('該当する検索結果はありません。')
            summary = '\n\n'.join(chunks)
            return dict(summary=summary, sources=sources, clipped=False, checked_at=time.time())

        schema = {'type': 'object', 'properties': {
            'question': {'type': 'string', 'minLength': 1, 'maxLength': 600},
            'requested_at': {'type': 'string', 'maxLength': 64}},
            'required': ['question', 'requested_at'], 'additionalProperties': False}
        return await call_service('research', 'search_web', execute, schema=schema,
            arguments={'question': question, 'requested_at': requested_at}, timeout=self.timeout)
