"""Web research provider: no conversation history, speech handles or UI."""
import json
import time

import models
from research import web_url
from service_mcp import call_service


def parse_response(response) -> tuple[str, list[dict], bool]:
    # モデルの知識だけで答えた結果や、途中で打ち切られた結果を検索済みとしない。
    if response.status != 'completed' or not any(
            item.type == 'web_search_call' and item.status == 'completed' for item in response.output):
        raise ValueError('search_not_completed')
    sources, chunks, clipped = [], [], False
    for item in response.output:
        if item.type != 'message':
            continue
        for content in item.content:
            if content.type != 'output_text':
                continue
            text = content.text
            replacements = []
            for citation in content.annotations:
                if citation.type != 'url_citation' or not web_url(citation.url):
                    continue
                source = next((s for s in sources if s['url'] == citation.url), None)
                if source is None:
                    if len(sources) >= 8:
                        clipped = True
                        continue
                    source = {'number': len(sources) + 1, 'title': citation.title[:200], 'url': citation.url}
                    sources.append(source)
                if 0 <= citation.start_index <= citation.end_index <= len(text):
                    replacements.append((citation.start_index, citation.end_index, f"[{source['number']}]"))
            for start, end, marker in sorted(replacements, reverse=True):
                text = text[:start] + marker + text[end:]
            chunks.append(text)
    summary = '\n\n'.join(chunks).strip()
    if not summary or not sources:
        raise ValueError('no_cited_result')
    return summary[:5000], sources, clipped or len(summary) > 5000


class ResearchService:
    def __init__(self, client, instructions, model, timeout):
        self.client, self.instructions, self.model, self.timeout = client, instructions, model, timeout

    async def search(self, question, requested_at):
        async def execute(arguments):
            response = await self.client.responses.create(
                model=self.model, store=False, instructions=self.instructions,
                input=json.dumps(arguments, ensure_ascii=False),
                tools=[{'type': 'web_search', 'external_web_access': True}],
                tool_choice='required', reasoning={'effort': 'low'}, max_output_tokens=2200)
            models.record('research', self.model, getattr(response, 'usage', None))
            summary, sources, clipped = parse_response(response)
            return {'summary': summary, 'sources': sources, 'clipped': clipped, 'checked_at': time.time()}
        schema = {'type': 'object', 'properties': {
            'question': {'type': 'string', 'minLength': 1, 'maxLength': 600},
            'requested_at': {'type': 'string', 'maxLength': 64}},
            'required': ['question', 'requested_at'], 'additionalProperties': False}
        return await call_service('research', 'search_web', execute, schema=schema,
            arguments={'question': question, 'requested_at': requested_at}, timeout=self.timeout)
