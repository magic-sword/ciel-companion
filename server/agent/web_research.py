"""Responses API の Web 検索。検索の成否・引用を検証してから調査記録にする。"""
import asyncio
import logging
import os
import json
import time

import openai

from research import packets, web_url

log = logging.getLogger('ciel-agent.web-research')


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


class WebResearcher:
    def __init__(self, history, instructions: str, publish=None, client=None):
        self.history, self.instructions, self.publish = history, instructions, publish
        self.model = os.environ.get('CIEL_RESEARCH_MODEL', 'gpt-5.4-mini')
        self.timeout = 45.0
        self.publish_timeout = 3.0
        self._client = client
        self._lock = asyncio.Lock()

    async def notify(self, record):
        if self.publish is not None:
            try:
                async with asyncio.timeout(self.publish_timeout):
                    for packet in packets(record):
                        await self.publish(packet)
            except Exception as exc:
                log.warning('調査結果を画面に送れない：%s', type(exc).__name__)

    async def search(self, question: str, call_id: str, speech):
        question = question.strip()
        if not question or len(question) > 600:
            return {'status': 'invalid_question'}
        if self._lock.locked():
            return {'status': 'busy'}
        async with self._lock:
            user = next((t for t in reversed(self.history.turns) if t.role == 'user'), None)
            record = self.history.research.begin(question, user.id if user else None, call_id)
            log.info('Web調査開始：id=%d', record.id)
            try:
                await self.notify(record)
                if self._client is None:
                    self._client = openai.AsyncOpenAI(timeout=self.timeout, max_retries=0)
                async with asyncio.timeout(self.timeout):
                    response = await self._client.responses.create(
                        model=self.model, store=False,
                        instructions=self.instructions,
                        input=json.dumps({'question': question, 'requested_at': record.payload()['requested_at']}, ensure_ascii=False),
                        tools=[{'type': 'web_search', 'external_web_access': True}],
                        tool_choice='required', reasoning={'effort': 'low'}, max_output_tokens=2200,
                    )
                record.summary, record.sources, record.clipped = parse_response(response)
                record.status = 'completed'
                record.checked_at = time.time()
                # 同じ返答のハンドルに属する発言だけを結ぶ。次の別の会話へ結び付けない。
                self.link_to_reply(record, speech)
            except asyncio.CancelledError:
                record.status = 'cancelled'
                raise
            except Exception as exc:
                record.status = 'failed'
                log.warning('Web調査を完了できない：%s', type(exc).__name__)
            finally:
                self.history.research.trim()
                log.info('Web調査終了：id=%d status=%s sources=%d', record.id, record.status, len(record.sources))
                await self.notify(record)
            return record.payload()

    def link_to_reply(self, record, speech):
        after = len(speech.chat_items)
        speech.add_done_callback(lambda done: self.history.research.link_answers(
            record, self.history, done.chat_items[after:]))

    async def close(self):
        if self._client is not None:
            await self._client.close()
