"""YouTube read service. Conversation policy and comment selection stay in the host."""
import aiohttp
from service_mcp import call_service


async def read_youtube(http, base_url, key, path, params, *, timeout):
    # The destination and credentials are trusted host configuration, not tool arguments.
    if path not in ('videos', 'liveChat/messages'):
        raise ValueError('unsupported_youtube_operation')

    async def execute(arguments):
        async with http.get(f'{base_url}/{path}', params={**params, 'key': key}) as response:
            try:
                body = await response.json(content_type=None)
            except (ValueError, aiohttp.ContentTypeError):
                body = {}
            return {'status_code': response.status, 'body': body if isinstance(body, dict) else {}}

    # Page data is for the trusted ingestion worker only; it is not added to model context.
    packet = await call_service('youtube', 'read_video' if path == 'videos' else 'read_comments',
                                execute, timeout=timeout, max_chars=2_000_000)
    return packet['status_code'], packet['body']
