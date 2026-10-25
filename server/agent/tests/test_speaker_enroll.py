"""Voice enrollment from the app ("声を登録する"): read sentences, then save name and voice (speakers.py)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import unittest

import numpy as np
from speakers import SpeakerBook, Known, ENROLL_NEEDED


def axis(i: int) -> np.ndarray:
    e = np.zeros(192, np.float32)
    e[i] = 1.0
    return e


def near(i: int, cos: float, j: int) -> np.ndarray:
    return (cos * axis(i) + np.sqrt(1 - cos * cos) * axis(j)).astype(np.float32)


class EnrollTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = SimpleNamespace(remember_person=AsyncMock(return_value=9), add_voiceprints=AsyncMock(return_value=[1]),
                                     touch=AsyncMock(), memory_snapshot=AsyncMock(return_value=None))
        self.book = SpeakerBook(self.store)
        self.states, self.enrolled, self.consented = [], [], []
        self.book.on_enroll = self.states.append
        self.book.on_enrolled = self.enrolled.append
        self.book.on_notes_consent = self.consented.append

    def pause(self):
        if self.book.enrolling is not None:
            self.book.enrolling.last_at -= 10   # the reader paused before the next sentence

    async def read(self, n, base=0, cos=0.8):
        for i in range(n):
            self.pause()
            self.book.judge(near(base, cos, 60 + i), 2.0)
        await asyncio.gather(*self.book._app_tasks)

    async def test_reading_the_sentences_saves_a_new_person_with_consent(self):
        self.assertEqual(await self.book.app_control({'action': 'enroll_start', 'name': '田中さん'}), 'enrolling')
        self.assertTrue(self.states[-1]['active'])
        await self.read(ENROLL_NEEDED)
        name, embeddings = self.store.remember_person.await_args.args[:2]
        self.assertEqual(name, '田中')
        self.assertEqual(len(embeddings), ENROLL_NEEDED)
        self.assertEqual(self.states[-1]['status'], 'saved')
        self.assertFalse(self.states[-1]['active'])
        self.assertIsNone(self.book.enrolling)
        self.assertEqual(self.enrolled, ['田中'])
        self.assertEqual(self.consented, [9])
        self.assertEqual(self.book.last.person_id, 9)
        self.assertTrue(self.book.last_sure)
        # recognized afterwards
        self.assertEqual(self.book.judge(near(0, 0.8, 90), 2.0).sp.person_id, 9)

    async def test_readings_are_marked_and_short_or_other_voices_are_not_accepted(self):
        await self.book.app_control({'action': 'enroll_start', 'name': '田中'})
        j = self.book.judge(axis(0), 2.0)
        self.assertTrue(j.enroll)
        self.assertEqual(self.book.judge(axis(0), 0.8).enroll, True)   # a fragment: ignored quietly
        self.assertEqual(self.states[-1]['status'], 'listening')
        self.pause()
        self.book.judge(axis(1), 2.0)   # someone else
        self.assertEqual(self.states[-1]['status'], 'other_voice')
        self.assertEqual(self.states[-1]['accepted'], 1)
        self.store.remember_person.assert_not_called()

    async def test_a_sentence_split_by_a_breath_counts_once(self):
        await self.book.app_control({'action': 'enroll_start', 'name': '田中'})
        self.book.judge(near(0, 0.8, 70), 1.6)
        self.book.judge(near(0, 0.8, 71), 1.3)   # right after: the rest of the same sentence
        self.assertEqual(self.states[-1]['accepted'], 1)
        self.assertEqual(len(self.book.enrolling.embeddings), 2)
        self.pause()
        self.book.judge(near(0, 0.8, 72), 2.0)
        self.assertEqual(self.states[-1]['accepted'], 2)

    async def test_cancel_removes_an_unused_chip(self):
        await self.book.app_control({'action': 'enroll_start', 'name': '田中'})
        self.assertEqual(len(self.book.speakers), 1)
        self.assertEqual(await self.book.app_control({'action': 'enroll_cancel'}), 'cancelled')
        self.assertEqual(self.book.speakers, [])
        self.assertIsNone(self.book.enrolling)

    async def test_bad_requests(self):
        control = self.book.app_control
        self.assertEqual(await control({'action': 'enroll_start', 'name': ''}), 'invalid_name')
        self.assertEqual(await control({'action': 'enroll_start', 'name': '田中', 'speaker_id': 'nope'}), 'speaker_not_found')
        await control({'action': 'enroll_start', 'name': '田中'})
        self.assertEqual(await control({'action': 'enroll_start', 'name': '佐藤'}), 'already_enrolling')
        self.book.store = None
        self.book.enrolling = None
        self.assertEqual(await control({'action': 'enroll_start', 'name': '田中'}), 'storage_unavailable')

    async def test_existing_session_speaker_must_match_the_first_reading(self):
        heard = self.book.judge(axis(0), 2.0).sp
        await self.book.app_control({'action': 'enroll_start', 'name': '田中', 'speaker_id': heard.speaker_id})
        self.pause()
        self.book.judge(axis(3), 2.0)
        self.assertEqual(self.states[-1]['status'], 'other_voice')
        await self.read(ENROLL_NEEDED)
        self.assertEqual(heard.person_id, 9)

    async def test_remembered_person_adds_samples_only_when_they_just_spoke(self):
        self.book.known = [Known(1, 'ハカセ', [axis(0)])]
        j = self.book.judge(axis(0), 2.0)
        await self.book.identify_parts(j)
        other = self.book.judge(axis(7), 2.0).sp
        await self.book.identify_parts(self.book.judge(axis(7), 2.0))
        self.assertEqual(await self.book.app_control({'action': 'enroll_start', 'name': 'x', 'speaker_id': j.sp.speaker_id}),
                         'not_current_speaker')
        await self.book.identify_parts(self.book.judge(axis(0), 2.0))
        self.assertEqual(await self.book.app_control({'action': 'enroll_start', 'name': 'x', 'speaker_id': j.sp.speaker_id}),
                         'enrolling')
        await self.read(ENROLL_NEEDED)
        self.assertEqual(self.store.add_voiceprints.await_args.args[0], 1)
        self.store.remember_person.assert_not_called()
        self.assertEqual(self.enrolled, ['ハカセ'])
        del other

    async def test_same_name_as_a_remembered_person_needs_a_similar_voice(self):
        self.book.known = [Known(1, '田中', [axis(5)])]
        await self.book.app_control({'action': 'enroll_start', 'name': '田中'})
        await self.read(ENROLL_NEEDED, base=0)
        self.assertEqual(self.states[-1]['status'], 'name_taken')
        self.store.add_voiceprints.assert_not_called()
        self.store.remember_person.assert_not_called()
        await self.book.app_control({'action': 'enroll_start', 'name': '田中'})
        await self.read(ENROLL_NEEDED, base=5)
        self.assertEqual(self.states[-1]['status'], 'saved')
        self.assertEqual(self.store.add_voiceprints.await_args.args[0], 1)


if __name__ == '__main__':
    unittest.main()
