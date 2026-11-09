"""Responses API の Web 検索。検索の成否・引用を検証してから調査記録にする。"""
import asyncio
import logging
import os

import openai

import models
from research import packets
from research_service import ResearchService, parse_response

log = logging.getLogger('ciel-agent.web-research')


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
        if models.LOCAL_TEST:
            return {'status': 'unavailable', 'reason': 'local_backend'}
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
                result = await ResearchService(self._client, self.instructions, self.model, self.timeout).search(
                    question, record.payload()['requested_at'])
                record.summary, record.sources, record.clipped = result['summary'], result['sources'], result['clipped']
                record.status = 'completed'
                record.checked_at = result['checked_at']
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
        if speech is None:
            return   # シエルが自分から調べた（curiosity.py）。結び付ける返事は無い
        after = len(speech.chat_items)
        speech.add_done_callback(lambda done: self.history.research.link_answers(
            record, self.history, done.chat_items[after:]))

    async def close(self):
        if self._client is not None:
            await self._client.close()
