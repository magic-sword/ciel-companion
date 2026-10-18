import asyncio
import json
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import AsyncMock

from conversation import Conversation
from research import ResearchBook, packets, web_url
from web_research import WebResearcher, parse_response
from tools.research import research_web, read_research


def response(text='休館です(ref)。条件は祝日です。', url='https://example.org/news'):
    citation = Obj(type='url_citation', url=url, title='公式のお知らせ', start_index=4, end_index=9)
    return Obj(status='completed', output=[Obj(type='web_search_call', status='completed'),
        Obj(type='message', content=[Obj(type='output_text', text=text, annotations=[citation])])])


class FakeSpeech:
    def __init__(self):
        self.chat_items, self.callbacks = [], []

    def add_done_callback(self, callback):
        self.callbacks.append(callback)

    def finish(self):
        for callback in self.callbacks:
            callback(self)


class ResearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.history = Conversation()
        self.user = self.history.reserve()
        self.history.complete(self.user, '明日の休館日を確認して')
        self.client = Obj(responses=Obj(create=AsyncMock(return_value=response())), close=AsyncMock())
        self.publish = AsyncMock()
        self.worker = WebResearcher(self.history, 'test instructions', self.publish, self.client)
        self.speech = FakeSpeech()

    async def test_search_is_required_and_only_question_is_sent(self):
        result = await self.worker.search('東京の施設の明日の休館日', 'call1', self.speech)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['request_turn_id'], self.user.id)
        self.assertIsNotNone(result['checked_at'])
        args = self.client.responses.create.call_args.kwargs
        self.assertEqual(args['tool_choice'], 'required')
        self.assertFalse(args['store'])
        self.assertEqual(args['tools'], [{'type': 'web_search', 'external_web_access': True}])
        self.assertEqual(json.loads(args['input'])['question'], '東京の施設の明日の休館日')
        self.assertNotIn(self.user.text, args['input'])
        self.assertEqual(len(self.history.turns), 1)
        self.assertEqual(result['sources'][0]['url'], 'https://example.org/news')

    async def test_links_only_messages_from_the_original_reply(self):
        await self.worker.search('休館日', 'call1', self.speech)
        reply = self.history.reserve(role='assistant')
        reply.source_id = 'reply1'
        self.history.complete(reply, '明日は休館みたい。')
        other = self.history.reserve(role='assistant')
        other.source_id = 'other'
        self.history.complete(other, '別の話です。')
        self.speech.chat_items.append(Obj(id='reply1', role='assistant'))
        self.speech.finish()
        record = self.history.research.records[0]
        self.assertEqual(record.answer_turn_ids, [reply.id])
        result = self.history.search('', reply.id, reply.id)
        self.assertEqual(result['research'][0]['id'], record.id)

    async def test_no_spoken_reply_is_not_claimed_as_spoken(self):
        await self.worker.search('休館日', 'call1', self.speech)
        self.speech.finish()
        self.assertEqual(self.history.research.records[0].answer_turn_ids, [])

    async def test_search_failure_does_not_return_cached_knowledge(self):
        self.client.responses.create.side_effect = RuntimeError('private error must not be returned')
        result = await self.worker.search('休館日', 'call1', self.speech)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['summary'], '')
        self.assertIsNone(result['checked_at'])
        self.assertNotIn('private', json.dumps(result))
        self.assertEqual(self.publish.call_args.args[0]['type'], 'research.complete')

    async def test_timeout_releases_lock(self):
        async def slow(**kwargs):
            await asyncio.sleep(1)
        self.client.responses.create.side_effect = slow
        self.worker.timeout = .001
        result = await self.worker.search('休館日', 'call1', self.speech)
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(self.worker._lock.locked())

    async def test_cancellation_is_recorded_and_not_linked_to_next_reply(self):
        started = asyncio.Event()
        async def slow(**kwargs):
            started.set()
            await asyncio.sleep(10)
        self.client.responses.create.side_effect = slow
        task = asyncio.create_task(self.worker.search('休館日', 'call1', self.speech))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.history.research.records[0].status, 'cancelled')
        self.assertEqual(self.speech.callbacks, [])

    async def test_parallel_calls_are_not_duplicated(self):
        async with self.worker._lock:
            result = await self.worker.search('休館日', 'call2', self.speech)
        self.assertEqual(result['status'], 'busy')
        self.client.responses.create.assert_not_awaited()

    async def test_ui_delivery_failure_does_not_fail_search(self):
        self.publish.side_effect = RuntimeError
        result = await self.worker.search('休館日', 'call1', self.speech)
        self.assertEqual(result['status'], 'completed')

    async def test_slow_ui_delivery_has_its_own_timeout(self):
        async def slow(packet):
            await asyncio.sleep(1)
        self.worker.publish = slow
        self.worker.publish_timeout = .001
        result = await self.worker.search('休館日', 'call1', self.speech)
        self.assertEqual(result['status'], 'completed')

    async def test_invalid_question_never_calls_api(self):
        for question in (' ', 'a' * 601):
            result = await self.worker.search(question, 'call1', self.speech)
            self.assertEqual(result['status'], 'invalid_question')
        self.client.responses.create.assert_not_awaited()

    async def test_reading_record_links_new_reply_without_erasing_original(self):
        await self.worker.search('休館日', 'call1', self.speech)
        first = self.history.reserve(role='assistant')
        first.source_id = 'first'
        self.history.complete(first, '休館です')
        self.speech.chat_items.append(Obj(id='first', role='assistant'))
        self.speech.finish()
        later_speech = FakeSpeech()
        context = Obj(userdata=Obj(history=self.history, researcher=self.worker), speech_handle=later_speech)
        await read_research(context, 1)
        later = self.history.reserve(role='assistant')
        later.source_id = 'later'
        self.history.complete(later, '出典はこちらです')
        later_speech.chat_items.append(Obj(id='later', role='assistant'))
        later_speech.finish()
        self.assertEqual(self.history.research.get(1).answer_turn_ids, [first.id, later.id])
        self.assertEqual(self.client.responses.create.await_count, 1)

    async def test_tool_recall_does_not_run_search_again(self):
        context = Obj(userdata=Obj(history=self.history, researcher=self.worker),
                      function_call=Obj(call_id='call1'), speech_handle=self.speech)
        first = json.loads(await research_web(context, '休館日'))
        recalled = json.loads(await read_research(context, first['id']))
        self.assertEqual(first['checked_at'], recalled['checked_at'])
        self.assertEqual(self.client.responses.create.await_count, 1)
        self.assertEqual(json.loads(await read_research(context, 999))['status'], 'not_retained')


class ParsingTests(unittest.TestCase):
    def test_requires_completed_search_and_real_citations(self):
        for result in (Obj(status='incomplete', output=[]), Obj(status='completed', output=[]), response(url='javascript:alert(1)')):
            with self.subTest(result=result), self.assertRaises(ValueError):
                parse_response(result)

    def test_citations_have_stable_numbers_and_text_is_bounded(self):
        result = response('abcd(ref)' + '本文' * 3000)
        summary, sources, clipped = parse_response(result)
        self.assertTrue(summary.startswith('abcd[1]'))
        self.assertEqual(len(summary), 5000)
        self.assertTrue(clipped)
        self.assertEqual(sources[0]['number'], 1)

    def test_urls_reject_non_web_schemes_credentials_and_control_chars(self):
        for value in ('file:///C:/secret', 'javascript:alert(1)', 'https://user:pass@example.org', 'https://example.org\n', 'https://[bad'):
            self.assertFalse(web_url(value))
        self.assertTrue(web_url('https://example.org/news?q=1'))

    def test_record_retention_and_session_isolation(self):
        book = ResearchBook(max_records=2)
        for i in range(3):
            book.begin(f'質問{i}', 1, 'call')
        self.assertIsNone(book.get(1))
        self.assertEqual(book.dropped_through, 1)
        self.assertEqual(Conversation().research.records, [])
        book.records[0].summary = '長文' * 100
        book.max_chars = 50
        book.trim()
        self.assertLessEqual(len(book.records), 1)

    def test_related_record_payload_and_packets_are_bounded(self):
        h = Conversation()
        for _ in range(5):
            r = h.research.begin('質問😀' * 150, None, 'call')
            r.summary = '調査結果😀' * 1000
            r.sources = [{'number': i + 1, 'title': '出典😀' * 50, 'url': 'https://example.org/' + 'a' * 1400} for i in range(8)]
        results = h.research.related('', [])
        self.assertLessEqual(sum(len(json.dumps(r, ensure_ascii=False)) for r in results), 7000)
        self.assertTrue(all(r['clipped'] for r in results))
        for packet in packets(r):
            self.assertLess(len(json.dumps(packet, ensure_ascii=False).encode('utf-8')), 14000)


if __name__ == '__main__':
    unittest.main()
