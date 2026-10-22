"""Actual recorder state must remain visible after rolling summaries and mode changes."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from conversation import Conversation
import minutes
from tools.minutes import finish_minutes, get_minutes_status, read_minutes, start_minutes
from turns import TurnReplies


class MinutesStateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        p = patch('minutes.openai.AsyncOpenAI')
        p.start()
        self.addCleanup(p.stop)
        self.h = Conversation()
        self.m = minutes.Minutes(None, 'test', self.h)
        self.m._write = AsyncMock()
        self.context = SimpleNamespace(userdata=SimpleNamespace(minutes=self.m))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, value in [('minutes.WEBHOOK', ''), ('minutes.SAVE_DIR', Path(self.tmp.name))]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    async def asyncTearDown(self):
        await self.m.flush()

    def add(self, text):
        t = self.h.reserve()
        self.h.complete(t, text)
        return t

    async def test_status_reports_pending_without_exposing_text(self):
        self.m.start()
        self.add('private meeting contents')
        self.h.reserve()
        state = self.m.status()
        self.assertTrue(state['recording'])
        self.assertEqual(state['ready_turn_count'], 1)
        self.assertEqual(state['pending_turn_count'], 1)
        self.assertNotIn('private meeting contents', self.m.context())
        self.assertIsNotNone(state['started_at'])

    async def test_rolling_summary_does_not_look_like_empty_meeting(self):
        self.m._summarize = AsyncMock(return_value={'title': 'private summary'})
        with patch('minutes.ROLL_SECONDS', 0.001):
            self.m.start()
            self.add('first')
            self.add('second')
            for _ in range(30):
                if self.m.meeting.summary is not None:
                    break
                await asyncio.sleep(0.002)
        state = self.m.status()
        self.assertTrue(state['recording'])
        self.assertTrue(state['has_summary'])
        self.assertEqual(state['summarized_turn_count'], 2)
        self.assertEqual(state['ready_turn_count'], 0)
        self.assertNotIn('private summary', self.m.context())
        self.add('third')
        self.assertEqual(self.m.status()['ready_turn_count'], 1)

    async def test_start_and_finish_return_actual_status(self):
        result = await start_minutes(self.context)
        state = json.loads(result.output)
        self.assertEqual(state['status'], minutes.STARTED)
        self.assertTrue(state['recording'])
        again = json.loads((await start_minutes(self.context)).output)
        self.assertEqual(again['status'], minutes.ALREADY)
        self.assertEqual(again['started_at'], state['started_at'])
        # Finish must work even without any transcript or summary.
        result = await finish_minutes(self.context)
        state = json.loads(result.output)
        self.assertEqual(state['status'], minutes.FINISHED)
        self.assertFalse(state['recording'])
        self.assertTrue(state['processing'])
        self.assertFalse(result.reply_required)
        self.assertEqual(json.loads((await finish_minutes(self.context)).output)['status'],
                         minutes.NOT_RECORDING)
        await self.m.flush()
        self.assertFalse(self.m.status()['processing'])

    async def test_status_tool_is_read_only(self):
        self.m.start()
        original = self.m.meeting
        state = json.loads(await get_minutes_status(self.context))
        self.assertTrue(state['available'])
        self.assertTrue(state['recording'])
        self.assertIs(self.m.meeting, original)
        self.assertFalse(self.m._tasks)
        self.context.userdata.minutes = None
        self.assertFalse(json.loads(await get_minutes_status(self.context))['available'])

    async def test_voice_finish_delivers_even_when_all_turns_were_summarized(self):
        self.m._write = minutes.Minutes._write.__get__(self.m)
        self.m._summarize = AsyncMock(return_value={'title': 'synthetic draft'})
        with patch('minutes.ROLL_SECONDS', 0.001), patch('minutes.WEBHOOK', 'test'), \
                patch('minutes.post_discord') as post:
            await start_minutes(self.context)
            self.add('first')
            self.add('second')
            for _ in range(30):
                if self.m.meeting.summary is not None:
                    break
                await asyncio.sleep(0.002)
            self.assertTrue(self.m.status()['has_summary'])
            self.assertEqual(self.m.status()['ready_turn_count'], 0)
            result = await finish_minutes(self.context)
            self.assertEqual(json.loads(result.output)['status'], minutes.FINISHED)
            await self.m.flush()
            post.assert_called_once()
            self.assertIn('synthetic draft', post.call_args.args[1])

    async def test_every_user_reply_includes_fresh_state_with_quiet_instructions(self):
        session = SimpleNamespace(generate_reply=Mock())
        style = SimpleNamespace(talk='quiet')
        replies = TurnReplies(session, None, None, style, 'quiet rules', minutes=self.m)
        self.m.start()
        self.add('first')
        await replies._reply(1, 2)
        extra = session.generate_reply.call_args.kwargs['instructions']
        self.assertIn('quiet rules', extra)
        state = json.loads(extra.split('[議事録状態]\n')[1])
        self.assertTrue(state['recording'])
        self.assertEqual(state['meeting_id'], self.m.meeting.export_id)
        self.assertNotIn('ready_turn_count', state)
        self.m.finish()
        style.talk = 'normal'
        await replies._reply(2, 3)
        extra = session.generate_reply.call_args.kwargs['instructions']
        self.assertNotIn('quiet rules', extra)
        self.assertFalse(json.loads(extra.split('[議事録状態]\n')[1])['recording'])

    async def test_speaker_identification_reply_also_includes_state(self):
        session = SimpleNamespace(generate_reply=Mock())
        book = SimpleNamespace(identify_parts=AsyncMock(return_value=('speaker metadata', '')), last=None)
        replies = TurnReplies(session, book, None, SimpleNamespace(talk='normal', presence='solo'), '', minutes=self.m)
        replies.encoder = object()
        replies._judgment_for = AsyncMock(return_value=None)
        self.m.start()
        await replies._reply(1, 2)
        extra = session.generate_reply.call_args.kwargs
        self.assertNotIn('user_input', extra)
        self.assertIn('speaker metadata', extra['instructions'])
        self.assertTrue(json.loads(extra['instructions'].split('[議事録状態]\n')[1])['recording'])

    async def test_retention_loss_is_reported_in_status(self):
        self.h.max_turns = 1
        self.m.start()
        self.add('lost')
        self.add('retained')
        self.assertTrue(self.m.status()['incomplete'])

    async def test_read_combines_checkpoint_and_unprocessed_turns_without_actions(self):
        self.m.start()
        self.add('earlier1')
        earlier = self.add('earlier2')
        m = self.m.meeting
        m.summary = {'title': 'checkpoint', 'decisions': ['Friday at three']}
        m.cursor, m.summarized_turn_count = earlier.id, 2
        self.add('newer decision')
        self.h.reserve()
        data = json.loads(await read_minutes(self.context))
        self.assertEqual(data['meeting_id'], m.export_id)
        self.assertEqual(data['summary_through_id'], earlier.id)
        self.assertIn('Friday at three', data['summary'])
        self.assertEqual(data['recent_turns'][0]['text'], 'newer decision')
        self.assertTrue(data['recent_turns'][1]['pending'])
        self.assertFalse(self.m._tasks)
        self.assertTrue(self.m.recording)

    async def test_finished_draft_is_queryable_after_a_new_meeting_starts(self):
        self.m._write = minutes.Minutes._write.__get__(self.m)
        self.m._summarize = AsyncMock(return_value=None)
        with patch('minutes.WEBHOOK', 'test'), patch('minutes.post_discord') as post:
            start = json.loads((await start_minutes(self.context)).output)
            meeting_id = start['meeting_id']
            self.add('first meeting1')
            self.add('first meeting2')
            await finish_minutes(self.context)
            self.assertEqual(self.m.status()['latest_export']['stage'], 'queued')
            await finish_minutes(self.context)
            await self.m.flush()
            post.assert_called_once()
        state = json.loads(await get_minutes_status(self.context))
        self.assertFalse(state['recording'])
        self.assertEqual(state['latest_export']['meeting_id'], meeting_id)
        self.assertEqual(state['latest_export']['stage'], 'sent')
        self.m.start()
        self.add('new meeting')
        self.assertNotEqual(self.m.read()['meeting_id'], meeting_id)
        old = json.loads(await read_minutes(self.context, meeting_id))
        self.assertIn('first meeting1', old['draft'])
        self.assertNotIn('new meeting', old['draft'])
        self.assertEqual(old['stage'], 'sent')
        self.assertEqual(self.m.read('unknown')['status'], 'not_found')

    async def test_local_fallback_is_distinct_from_discord_success(self):
        self.m._write = minutes.Minutes._write.__get__(self.m)
        self.m._summarize = AsyncMock(return_value=None)
        self.add('first')
        self.add('second')
        with patch('minutes.WEBHOOK', 'test'), patch('minutes.post_discord', side_effect=RuntimeError):
            self.m.summarize_past()
            await self.m.flush()
        self.assertEqual(self.m.status()['latest_export']['stage'], 'saved_locally')
        self.assertIn('first', self.m.read()['draft'])

    async def test_write_failure_is_observable_and_does_not_claim_sent(self):
        self.m._write = minutes.Minutes._write.__get__(self.m)
        self.m._summarize = AsyncMock(return_value=None)
        self.add('first')
        self.add('second')
        with patch('pathlib.Path.write_text', side_effect=PermissionError('private error contents')):
            self.m.summarize_past()
            await self.m.flush()
        state = self.m.status()['latest_export']
        self.assertEqual(state['stage'], 'failed')
        self.assertEqual(state['error'], 'PermissionError')
        self.assertTrue(state['draft_available'])
        self.assertNotIn('private error contents', json.dumps(state))
        self.assertFalse(self.m.status()['processing'])

    async def test_empty_export_does_not_disappear_or_look_sent(self):
        self.m._write = minutes.Minutes._write.__get__(self.m)
        self.m.start()
        self.m.finish()
        await self.m.flush()
        self.assertEqual(self.m.status()['latest_export']['stage'], 'empty')
        data = self.m.read()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['stage'], 'empty')
        self.assertFalse(data['draft_available'])

    async def test_read_and_cache_limits_are_explicit(self):
        self.m._write = minutes.Minutes._write.__get__(self.m)
        self.m._summarize = AsyncMock(return_value={'title': 'x' * 60000})
        self.add('first')
        self.add('second')
        self.m.summarize_past()
        await self.m.flush()
        self.assertEqual(len(self.m._exports[-1].draft), minutes.DRAFT_CACHE_CHARS)
        data = self.m.read()
        self.assertEqual(len(data['draft']), minutes.READ_CHARS)
        self.assertTrue(data['content_clipped'])
        self.m.start()
        for _ in range(12):
            self.add('x' * 2000)
        data = self.m.read()
        self.assertLessEqual(len(data['summary']) + sum(len(t['text']) for t in data['recent_turns']),
                             minutes.READ_CHARS)
        self.assertTrue(data['content_clipped'])
        self.assertEqual(data['unprocessed_turn_count'], 12)

    async def test_recent_result_retention_is_bounded_and_ids_do_not_alias(self):
        self.m._write = minutes.Minutes._write.__get__(self.m)
        self.m._summarize = AsyncMock(return_value=None)
        ids = []
        for _ in range(7):
            self.m.start()
            ids.append(self.m.meeting.export_id)
            self.add('first')
            self.add('second')
            self.m.finish()
            await self.m.flush()
        self.assertEqual(len(self.m._exports), minutes.RECENT_EXPORTS)
        self.assertEqual(len(set(ids)), 7)
        self.assertEqual(self.m.read(ids[0])['status'], 'not_found')
        self.assertEqual(self.m.read(ids[-1])['stage'], 'saved_locally')
