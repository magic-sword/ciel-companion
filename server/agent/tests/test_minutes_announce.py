"""Telling Ciel how sending the minutes ended: sent, saved, failed or empty, at a pause in the talk (minutes.py)."""
import asyncio
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from conversation import Conversation
import minutes


class AnnounceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, value in [('minutes.openai.AsyncOpenAI', Mock()), ('minutes.WEBHOOK', ''),
                              ('minutes.SAVE_DIR', Path(self.tmp.name)), ('minutes.ANNOUNCE_POLL', 0.01)]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        self.h = Conversation()
        self.m = minutes.Minutes(None, 'test instructions', self.h)
        self.m._summarize = AsyncMock(return_value=None)
        self.m.on_change = Mock()

    def add(self, text):
        t = self.h.reserve(time.time())
        self.h.complete(t, text)

    async def settle(self):
        await asyncio.gather(*self.m._tasks)
        await asyncio.gather(*self.m._announcing)

    def events(self):
        return [c.args[0] for c in self.m.on_change.call_args_list]

    async def meeting(self):
        self.m.start()
        self.add('first')
        self.add('second')
        self.m.finish()
        await self.settle()

    async def test_sent_is_told_after_finishing(self):
        with patch('minutes.WEBHOOK', 'https://example.invalid/hook'), patch('minutes.post_discord') as post:
            await self.meeting()
        post.assert_called_once()
        self.assertEqual(self.events(), [minutes.STARTED, minutes.FINISHED, minutes.EXPORT_SENT])

    async def test_saved_locally_failed_and_empty_are_told(self):
        await self.meeting()
        self.assertEqual(self.events()[-1], minutes.EXPORT_SAVED)
        self.m.on_change.reset_mock()
        self.m._write = AsyncMock(side_effect=RuntimeError('boom'))
        await self.meeting()
        self.assertEqual(self.events()[-1], minutes.EXPORT_FAILED)
        del self.m._write
        self.m.on_change.reset_mock()
        self.m.start()
        self.m.finish()
        await self.settle()
        self.assertEqual(self.events(), [minutes.STARTED, minutes.FINISHED, minutes.EXPORT_EMPTY])

    async def test_past_minutes_are_told_too(self):
        self.add('first')
        self.add('second')
        self.assertEqual(self.m.summarize_past(), minutes.PAST_QUEUED)
        await self.settle()
        self.assertEqual(self.events(), [minutes.PAST_QUEUED, minutes.EXPORT_SAVED])

    async def test_nothing_is_told_when_the_conversation_ends(self):
        self.m.start()
        self.add('first')
        self.add('second')
        await self.m.flush()
        await asyncio.gather(*self.m._announcing)
        self.assertEqual(self.events(), [minutes.STARTED])
        self.assertIsNone(self.m.take_note())

    async def test_waits_while_someone_is_talking(self):
        talking = [True]
        self.m.busy = lambda: talking[0]
        self.m.start()
        self.add('first')
        self.add('second')
        self.m.finish()
        await asyncio.gather(*self.m._tasks)
        await asyncio.sleep(0.05)
        self.assertEqual(self.events(), [minutes.STARTED, minutes.FINISHED])   # not yet
        talking[0] = False
        await asyncio.gather(*self.m._announcing)
        self.assertEqual(self.events()[-1], minutes.EXPORT_SAVED)
        self.assertIsNone(self.m.take_note())

    async def test_a_long_talk_puts_the_result_into_the_next_reply(self):
        self.m.busy = lambda: True
        with patch('minutes.ANNOUNCE_WAIT', 0.05):
            await self.meeting()
        self.assertEqual(self.events(), [minutes.STARTED, minutes.FINISHED])
        self.assertEqual(self.m.take_note(), minutes.LINES[minutes.EXPORT_SAVED])
        self.assertIsNone(self.m.take_note())   # only once

    def test_every_event_has_a_line(self):
        for what in [minutes.STARTED, minutes.ALREADY, minutes.FINISHED, minutes.NOT_RECORDING, minutes.PAST_QUEUED,
                     minutes.PAST_PARTIAL, minutes.STARTED_EARLIER, minutes.STARTED_PARTIAL, *minutes.RESULTS.values()]:
            self.assertTrue(minutes.LINES[what].startswith('[議事録：'))


if __name__ == '__main__':
    unittest.main()
