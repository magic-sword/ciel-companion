"""Long meetings: odd voices are held instead of making new people, unknown people who turn out to be one are joined,
and remembered people who are not there are not added on one 'maybe' (speakers.py)."""
import unittest

import numpy as np
from speakers import SpeakerBook, Known, MAX_PENDING


def axis(i: int) -> np.ndarray:
    e = np.zeros(192, np.float32)
    e[i] = 1.0
    return e


def near(i: int, cos: float, j: int) -> np.ndarray:
    return (cos * axis(i) + np.sqrt(1 - cos * cos) * axis(j)).astype(np.float32)


def unit(v: np.ndarray) -> np.ndarray:
    return (v / np.linalg.norm(v)).astype(np.float32)


def drifted(i: int, cos: float, k: int) -> np.ndarray:
    """cos with axis(i), and very close to the other drifted voices"""
    return unit(cos * axis(i) + np.sqrt(1 - cos * cos - 0.04) * axis(40) + 0.2 * axis(41 + k))


class CrowdTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.book = SpeakerBook(None)

    async def speak(self, e, seconds):
        j = self.book.judge(e, seconds)
        await self.book.identify_parts(j)
        return j

    async def test_odd_voices_in_a_long_meeting_of_two_do_not_add_people(self):
        a = await self.speak(axis(0), 3.0)
        b = await self.speak(axis(1), 3.0)
        rng = np.random.default_rng(0)
        for _ in range(40):   # laughs, overlaps, noise: each like nobody, and not like each other
            j = await self.speak(unit(rng.standard_normal(192)), 1.5)
            self.assertIsNone(j.sp)
            self.assertIsNotNone(j.pending)
        self.assertEqual(self.book.speakers, [a.sp, b.sp])
        self.assertLessEqual(len(self.book.pending), MAX_PENDING)
        self.assertIs((await self.speak(near(0, 0.8, 60), 1.5)).sp, a.sp)   # the two are still found

    async def test_the_first_voice_and_long_new_voices_make_a_person_at_once(self):
        a = await self.speak(axis(0), 1.0)
        self.assertIsNotNone(a.sp)
        b = await self.speak(axis(1), 2.5)
        self.assertIsNotNone(b.sp)
        self.assertEqual(len(self.book.speakers), 2)

    async def test_a_held_voice_heard_again_becomes_a_new_person(self):
        await self.speak(axis(0), 3.0)
        first = await self.speak(axis(2), 1.5)
        self.assertIsNone(first.sp)
        again = await self.speak(near(2, 0.8, 61), 1.5)
        self.assertIsNotNone(again.sp)
        self.assertTrue(again.sure)
        self.assertEqual(again.sp.label, '知らない人B')
        self.assertEqual(len(again.sp.embeddings), 2)   # both voices are its samples
        self.assertEqual(self.book.pending, [])

    async def test_two_unknown_people_whose_voices_come_together_are_joined(self):
        merged = []
        self.book.on_merge = lambda src, dst: merged.append((src, dst))
        x = await self.speak(axis(0), 3.0)
        v = near(0, 0.3, 50)                    # one person, first heard in an odd voice: a second person
        y = (await self.speak(v, 3.0)).sp   # (the last judgment is pointed at the person it is joined to)
        self.assertEqual(len(self.book.speakers), 2)
        w = unit(axis(0) + v)                   # their usual voice: like both
        j = await self.speak(w, 2.0)
        self.assertEqual(self.book.speakers, [x.sp])
        self.assertIs(j.sp, x.sp)
        self.assertEqual(len(merged), 1)
        self.assertIs(merged[0][0], y)
        self.assertIs(merged[0][1], x.sp)

    async def test_unknown_people_with_different_names_are_not_joined(self):
        x = await self.speak(axis(0), 3.0)
        await self.book.name(x.sp.speaker_id, 'ハカセ', False)
        v = near(0, 0.3, 50)
        y = await self.speak(v, 3.0)
        await self.book.name(y.sp.speaker_id, 'ミナ', False)
        await self.speak(unit(axis(0) + v), 2.0)
        self.assertEqual(len(self.book.speakers), 2)

    async def test_a_remembered_person_who_is_not_here_needs_two_maybes(self):
        self.book.known = [Known(1, 'ハカセ', [axis(5)])]
        a = await self.speak(axis(0), 3.0)
        once = await self.speak(near(5, 0.45, 60), 2.0)
        self.assertIsNone(once.sp)
        self.assertEqual(self.book.speakers, [a.sp])
        twice = await self.speak(near(5, 0.45, 61), 2.0)
        self.assertEqual(twice.sp.person_id, 1)
        self.assertFalse(twice.sure)
        self.assertEqual(len(twice.sp.embeddings), 2)
        # once here, one maybe is enough as before
        self.assertIs((await self.speak(near(5, 0.45, 62), 2.0)).sp, twice.sp)

    async def test_a_sure_remembered_person_is_added_at_once(self):
        self.book.known = [Known(1, 'ハカセ', [axis(5)])]
        await self.speak(axis(0), 3.0)
        j = await self.speak(near(5, 0.7, 60), 2.0)
        self.assertEqual(j.sp.person_id, 1)
        self.assertTrue(j.sure)

    async def test_a_held_maybe_for_someone_absent_is_not_named(self):
        self.book.known = [Known(1, 'ハカセ', [axis(5)])]
        await self.speak(axis(0), 3.0)
        await self.speak(near(5, 0.45, 60), 2.0)
        result = await self.book.register_name('田中', self_introduction=True)
        self.assertEqual(result['status'], 'pending_identity')
        self.assertEqual(len(self.book.speakers), 1)

    async def test_an_unknown_is_joined_to_someone_absent_only_when_quite_close(self):
        self.book.known = [Known(1, 'ハカセ', [axis(5)])]
        await self.speak(axis(0), 3.0)
        u = await self.speak(drifted(5, 0.34, 0), 3.0)
        self.assertIsNone(u.sp.person_id)
        for k in range(1, 5):   # about 0.52 on average: was joined at 0.50
            j = await self.speak(drifted(5, 0.56, k), 2.0)
            self.assertIs(j.sp, u.sp)
        self.assertIsNone(u.sp.person_id)
        j = await self.speak(drifted(5, 0.56, 5), 2.0)   # the last five now average 0.56
        self.assertEqual(j.sp.person_id, 1)


if __name__ == '__main__':
    unittest.main()
