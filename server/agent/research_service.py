"""Provider-independent authenticated search MCP client and conversation presentation."""
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

import httpx
import jsonschema
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from research import web_url

SCHEMA = json.loads((Path(__file__).with_name('config') / 'search-api.schema.json').read_text(encoding='utf8'))


def validate_reply(value):
    jsonschema.validate(value, SCHEMA, format_checker=jsonschema.FormatChecker())
    rows = value['results']
    for row in rows:
        if not web_url(row['url']) or any(row.get(k) and not web_url(row[k]) for k in ('license_url', 'history_url')):
            raise ValueError('invalid_search_url')
    if value['status'] == 'ok' and not rows:
        raise ValueError('search_missing_sources')
    if value['status'] != 'ok' and (rows or value.get('summary')):
        raise ValueError('failed_search_contains_answer')
    if value['content_kind'] == 'grounded_summary' and value['status'] == 'ok':
        citations = re.findall(r'\[(\d+)\]', value.get('summary') or '')
        if not citations or any(not 1 <= int(i) <= len(rows) for i in citations):
            raise ValueError('summary_missing_citations')
    if value['content_kind'] == 'search_snippets' and value.get('summary') is not None:
        raise ValueError('unexpected_generated_summary')
    return value


async def request_search(query, limit):
    try:
        return await _request_search(query, limit)
    except BaseException:
        # Session DELETE cancels the remote provider. Some MCP transports report
        # the closed POST as an HTTP error while unwinding; preserve caller cancellation.
        if asyncio.current_task().cancelling():
            raise asyncio.CancelledError from None
        raise


async def _request_search(query, limit):
    url = os.getenv('CIEL_SEARCH_URL', 'http://127.0.0.1:8780/mcp')
    token = os.getenv('CIEL_SEARCH_TOKEN', '')
    parsed = urlsplit(url)
    if (not token or parsed.username or parsed.password or parsed.fragment or
            not (parsed.scheme == 'https' or
                 (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')))):
        raise ValueError('search_connection_not_configured')
    async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + token},
                                 timeout=httpx.Timeout(35, connect=5), follow_redirects=False, trust_env=False) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool('search', {'query': query, 'limit': limit})
                if result.isError or result.structuredContent is None:
                    raise ValueError('search_service_error')
                return validate_reply(result.structuredContent)


class ResearchService:
    def __init__(self, timeout=45):
        self.timeout = timeout

    async def search(self, question, requested_at):
        async with asyncio.timeout(self.timeout):
            result = await request_search(question, 3)
        if result['status'] not in ('ok', 'no_results'):
            raise ValueError('search_unavailable:' + result['status'])
        kind = '検索概要（記事本文は未取得）' if result['content_kind'] == 'search_snippets' else '出典付き生成要約'
        sources, chunks = [], [f"検索範囲: {result['coverage']}。{kind}。"]
        for row in result['results']:
            number = len(sources) + 1
            title = row['title'] + (' — ' + row['attribution'] if row['attribution'] else '')
            sources.append(dict(number=number, title=title[:200], url=row['url']))
            if result['content_kind'] == 'search_snippets':
                chunks.append(f"[{number}] {row['title']}: {row['snippet']}")
        if result.get('summary'):
            chunks.append(result['summary'])
        for license_url in dict.fromkeys(row['license_url'] for row in result['results'] if row.get('license_url')):
            number = len(sources) + 1
            sources.append(dict(number=number, title='出典の利用条件', url=license_url))
            chunks.append(f'利用条件 [{number}]。概要は表示用に整形済み。')
        if result['status'] == 'no_results':
            chunks.append('この検索範囲では該当する結果がありません。')
        summary = '\n\n'.join(chunks)
        return dict(summary=summary[:5000], sources=sources[:8],
                    clipped=len(summary) > 5000 or len(sources) > 8,
                    checked_at=datetime.fromisoformat(result['retrieved_at'].replace('Z', '+00:00')).timestamp())
