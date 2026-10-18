"""Retrospective minutes: boundaries, asynchronous transcripts and delivery isolation."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from conversation import Conversation
import minutes
from tools.minutes import summarize_past_minutes, start_minutes


class PastMinutesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, value in [('minutes.openai.AsyncOpenAI', Mock()),
                              ('minutes.WEBHOOK', ''), ('minutes.SAVE_DIR', Path(self.tmp.name))]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        self.h = Conversation()
        self.m = minutes.Minutes(None, 'test instructions', self.h)
        self.m._summarize = AsyncMock(return_value=None)
        self.m.on_change = Mock()

    async def asyncTearDown(self):
        await self.m.flush()

    def add(self, text, age=0):
        t = self.h.reserve(time.time() - age)
        self.h.complete(t, text)
        return t

    def files(self):
        return list(Path(self.tmp.name).glob('*.md'))

    async def test_all_history_is_fixed_at_request_and_preserved(self):
        self.add('first')
        self.add('second')
        self.assertEqual(self.m.summarize_past(), minutes.PAST_QUEUED)
        self.assertFalse(self.m.recording)
        self.add('after request')
        await self.m.flush()
        text = self.files()[0].read_text(encoding='utf-8')
        self.assertIn('first', text)
        self.assertIn('second', text)
        self.assertNotIn('after request', text)
        self.assertEqual(len(self.h.turns), 3)
        self.m.on_change.assert_called_once_with(minutes.PAST_QUEUED)

    async def test_recent_minutes_exclude_older_turns(self):
        self.add('old', 2000)
        self.add('recent1', 60)
        self.add('recent2', 30)
        self.assertEqual(self.m.summarize_past(10), minutes.PAST_QUEUED)
        await self.m.flush()
        rows = self.m._summarize.call_args.args[3]
        self.assertEqual([t.text for t in rows], ['recent1', 'recent2'])

    async def test_id_bounds_are_inclusive(self):
        for i in range(5):
            self.add(str(i))
        self.assertEqual(self.m.summarize_past(first_id=2, last_id=3), minutes.PAST_QUEUED)
        await self.m.flush()
        self.assertEqual([t.id for t in self.m._summarize.call_args.args[3]], [2, 3])

    async def test_invalid_ranges_and_empty_do_not_queue(self):
        self.add('single')
        for args in [(-1,), (1441,), (True,), (1, 1), (0, 2), (0, 0, 2), (0, 1, -1)]:
            self.assertEqual(self.m.summarize_past(*args), minutes.INVALID_RANGE)
        self.assertEqual(self.m.summarize_past(), minutes.EMPTY)
        self.assertFalse(self.m._tasks)
        self.assertFalse(self.files())
        self.m.on_change.assert_not_called()

    async def test_active_recording_is_not_replaced_or_exported(self):
        self.add('first')
        self.add('second')
        self.m.start()
        meeting = self.m.meeting
        self.assertEqual(self.m.summarize_past(), minutes.ALREADY)
        self.assertIs(self.m.meeting, meeting)
        self.assertFalse(self.m._tasks)

    async def test_busy_avoids_concurrent_duplicate_but_later_export_is_unique(self):
        self.add('first')
        self.add('second')
        self.m.summarize_past()
        self.assertEqual(self.m.summarize_past(), minutes.BUSY)
        await self.m.flush()
        self.assertEqual(self.m.summarize_past(), minutes.PAST_QUEUED)
        await self.m.flush()
        self.assertEqual(len(self.files()), 2)

    async def test_missing_history_is_announced_and_marked_in_draft(self):
        self.h.max_turns = 2
        for text in ['dropped', 'kept1', 'kept2']:
            self.add(text)
        self.assertEqual(self.m.summarize_past(), minutes.PAST_PARTIAL)
        await self.m.flush()
        self.assertIn('一部の発言が欠けています', self.files()[0].read_text(encoding='utf-8'))
        self.assertEqual(self.m.summarize_past(first_id=2), minutes.PAST_QUEUED)

    async def test_pending_transcript_is_included_after_completion(self):
        pending = self.h.reserve()
        self.add('ready')
        self.m.summarize_past()
        await asyncio.sleep(0)
        self.assertFalse(self.files())
        self.h.complete(pending, 'late transcript')
        await self.m.flush()
        self.assertIn('late transcript', self.files()[0].read_text(encoding='utf-8'))

    async def test_snapshot_survives_history_eviction(self):
        self.h.max_turns = 2
        self.add('snapshot1')
        self.add('snapshot2')
        self.m.summarize_past()
        self.add('future1')
        self.add('future2')
        await self.m.flush()
        text = self.files()[0].read_text(encoding='utf-8')
        self.assertIn('snapshot1', text)
        self.assertNotIn('future1', text)
        self.assertNotIn('一部の発言が欠けています', text)

    async def test_evicted_pending_transcript_does_not_silently_disappear(self):
        self.h.max_turns = 2
        self.h.reserve()
        self.add('ready')
        self.m.summarize_past()
        self.add('future')
        await self.m.flush()
        self.assertIn('一部の発言が欠けています', self.files()[0].read_text(encoding='utf-8'))

    async def test_lookback_start_includes_past_and_future(self):
        self.add('too old', 2000)
        self.add('past1', 60)
        self.add('past2', 30)
        self.assertEqual(self.m.start(10), minutes.STARTED_EARLIER)
        self.add('future')
        self.m.finish()
        await self.m.flush()
        self.assertEqual([t.text for t in self.m._summarize.call_args.args[3]],
                         ['past1', 'past2', 'future'])

    async def test_lookback_partial_and_validation(self):
        self.h.max_turns = 2
        for text in ['lost', 'kept1', 'kept2']:
            self.add(text)
        for value in [-1, 1441, True]:
            self.assertEqual(self.m.start(value), minutes.INVALID_RANGE)
        self.assertEqual(self.m.start(10), minutes.STARTED_PARTIAL)
        original = self.m.meeting
        self.assertEqual(self.m.start(20), minutes.ALREADY)
        self.assertIs(self.m.meeting, original)

    async def test_tool_results_suppress_only_callback_announcements(self):
        context = SimpleNamespace(userdata=SimpleNamespace(minutes=self.m))
        empty = await summarize_past_minutes(context)
        self.assertEqual(json.loads(empty)['status'], minutes.EMPTY)
        self.add('one')
        self.add('two')
        result = await summarize_past_minutes(context)
        self.assertFalse(result.reply_required)
        busy = await summarize_past_minutes(context)
        self.assertEqual(json.loads(busy)['status'], minutes.BUSY)
        invalid = await start_minutes(context, -1)
        self.assertEqual(json.loads(invalid)['status'], minutes.INVALID_RANGE)

    async def test_existing_discord_delivery_is_used(self):
        self.add('one')
        self.add('two')
        with patch('minutes.WEBHOOK', 'test-webhook'), patch('minutes.post_discord') as post:
            self.m.summarize_past()
            await self.m.flush()
        post.assert_called_once()
        self.assertFalse(self.files())
