"""Short replies ("いいよ", "はい"): checked only against the previous speaker, so consent can be confirmed (speakers.py)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import unittest

import numpy as np
from speakers import SpeakerBook, Known


def axis(i: int) -> np.ndarray:
    e = np.zeros(192, np.float32)
    e[i] = 1.0
    return e


def near(i: int, cos: float, j: int) -> np.ndarray:
    return (cos * axis(i) + np.sqrt(1 - cos * cos) * axis(j)).astype(np.float32)


class ShortReplyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.book = SpeakerBook(None)

    async def speak(self, e, seconds, solo=False):
        j = self.book.judge(e, seconds)
        await self.book.identify_parts(j, solo=solo)
        return j

    async def test_short_reply_in_the_previous_voice_keeps_the_speaker_and_certainty(self):
        a = await self.speak(axis(0), 2.0)   # 知らない人A, sure
        b = await self.speak(axis(1), 2.0)   # 知らない人B
        await self.speak(near(0, 0.8, 50), 2.0)   # A again
        j = await self.speak(near(0, 0.45, 51), 0.5)   # 「いいよ」
        self.assertTrue(j.short)
        self.assertIs(j.sp, a.sp)
        self.assertTrue(j.sure)
        self.assertIs(self.book.last, a.sp)
        self.assertTrue(self.book.last_sure)
        self.assertEqual(len(self.book.speakers), 2)   # no new person from a short reply
        self.assertEqual(len(a.sp.embeddings), 2)      # and the short voice is not added as a sample
        del b

    async def test_short_reply_closer_to_someone_else_is_unknown(self):
        await self.speak(axis(0), 2.0)
        b = await self.speak(axis(1), 2.0)
        await self.speak(axis(0), 2.0)   # A spoke last
        j = await self.speak(near(1, 0.6, 52), 0.5)   # B answers for A
        self.assertIsNone(j.sp)
        self.assertIsNone(self.book.last)
        del b

    async def test_short_voice_that_cannot_be_checked_still_counts_as_the_reply(self):
        a = await self.speak(axis(0), 2.0)
        await self.speak(axis(1), 2.0)
        await self.speak(axis(0), 2.0)
        j = await self.speak(near(0, 0.2, 57), 0.5)   # short voices score only about 0.2 even for the same person
        self.assertIs(j.sp, a.sp)
        self.assertTrue(j.sure)

    async def test_a_tiny_noise_in_between_does_not_lose_the_previous_speaker(self):
        a = await self.speak(axis(0), 2.0)
        await self.speak(None, 0.1)   # 「あ」: unknown, clears the current speaker in a group
        self.assertIsNone(self.book.last)
        j = await self.speak(near(0, 0.5, 53), 0.5)
        self.assertIs(j.sp, a.sp)
        self.assertTrue(self.book.last_sure)

    async def test_no_previous_speaker_or_too_long_ago_is_unknown(self):
        j = await self.speak(axis(0), 0.5)
        self.assertIsNone(j.sp)
        self.assertEqual(self.book.speakers, [])
        await self.speak(axis(0), 2.0)
        self.book.recent_at -= 40
        self.assertIsNone((await self.speak(near(0, 0.6, 54), 0.5)).sp)

    async def test_uncertain_previous_judgment_stays_uncertain(self):
        a = await self.speak(axis(0), 2.0)
        await self.speak(near(0, 0.40, 55), 2.0)   # たぶん A
        self.assertFalse(self.book.last_sure)
        j = await self.speak(near(0, 0.6, 56), 0.5)
        self.assertIs(j.sp, a.sp)
        self.assertFalse(j.sure)

    async def test_eight_tenths_of_a_second_is_long_enough_for_a_new_person(self):
        j = await self.speak(axis(0), 0.85)
        self.assertIsNotNone(j.sp)
        self.assertFalse(j.short)


class ShortConsentTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_yes_after_self_introduction_saves_the_person(self):
        saved = {}

        async def remember(name, embeddings, pid=None, channel=None):
            saved['args'] = (name, len(embeddings))
            return 7

        async def identity(pid):
            return {'name': '田中', 'notes_consented': True, 'voice_sample_count': 1} if 'args' in saved else None

        store = SimpleNamespace(remember_person=AsyncMock(side_effect=remember), identity=AsyncMock(side_effect=identity),
                                touch=AsyncMock(), memory_snapshot=AsyncMock(return_value=None),
                                add_voiceprints=AsyncMock(return_value=[1]))
        book = SpeakerBook(store)
        book.known = [Known(1, 'ハカセ', [axis(5)])]
        for e, sec in [(axis(5), 2.0), (axis(0), 1.2)]:   # ハカセ, then a new person introduces themself
            await book.identify_parts(book.judge(e, sec))
        first = await book.register_name('田中', self_introduction=True)
        self.assertEqual(first['status'], 'session_named')
        await book.identify_parts(book.judge(near(0, 0.5, 60), 0.4))   # 「いいよ」
        result = await book.confirm_name(first['registration_id'], '田中', remember=True)
        self.assertEqual(result['status'], 'saved')
        self.assertEqual(saved['args'][0], '田中')


if __name__ == '__main__':
    unittest.main()
