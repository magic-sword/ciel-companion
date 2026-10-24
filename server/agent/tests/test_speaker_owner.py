"""The device owner, recovery from a wrong 'unknown person', and persisting manual merges (speakers.py)."""
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
import unittest

import numpy as np
from speakers import SpeakerBook, Known, SessionSpeaker


def axis(i: int) -> np.ndarray:
    e = np.zeros(192, np.float32)
    e[i] = 1.0
    return e


def near(i: int, cos: float, j: int) -> np.ndarray:
    """A voice whose cosine with axis(i) is cos (the rest points along axis(j))"""
    return (cos * axis(i) + np.sqrt(1 - cos * cos) * axis(j)).astype(np.float32)


def drifted(i: int, cos: float, k: int) -> np.ndarray:
    """A voice heard through another microphone: cos with axis(i), and much closer to the other drifted voices"""
    v = cos * axis(i) + np.sqrt(1 - cos * cos - 0.04) * axis(40) + 0.2 * axis(41 + k)
    return (v / np.linalg.norm(v)).astype(np.float32)


DEVICE = {'device_id': 'device-0123456789', 'secret': 's' * 32}


class OwnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pairs = {}

        async def pair(device_id, secret_hash, pid):
            self.pairs[device_id] = (secret_hash, pid)

        async def owner(device_id, secret_hash):
            row = self.pairs.get(device_id)
            return row[1] if row and row[0] == secret_hash else None

        async def unpair(device_id, secret_hash):
            return self.pairs.pop(device_id, None) is not None if await owner(device_id, secret_hash) else False

        self.store = SimpleNamespace(pair_device=AsyncMock(side_effect=pair), device_owner=AsyncMock(side_effect=owner),
                                     unpair_device=AsyncMock(side_effect=unpair), add_voiceprints=AsyncMock(return_value=[1]),
                                     touch=AsyncMock(), memory_snapshot=AsyncMock(return_value=None))
        self.book = SpeakerBook(self.store)
        self.book.known = [Known(1, 'ハカセ', [axis(0)] * 3), Known(2, 'ミナ', [axis(1)] * 3)]
        self.presence = 'solo'
        self.book.private = lambda: self.presence in ('solo', 'close')
        self.sent = []
        self.book.on_change = self.sent.append

    async def test_owner_is_paired_only_from_a_sure_remembered_speaker_and_found_again_by_hello(self):
        control = self.book.app_control
        self.assertEqual(await control({'action': 'hello', **DEVICE}), 'no_owner')
        j = self.book.judge(axis(1), 2.0)   # ミナ, sure
        await self.book.identify_parts(j)
        other = SessionSpeaker(label='知らない人A')
        self.book.speakers.append(other)
        self.assertEqual(await control({'action': 'pair', 'speaker_id': other.speaker_id, **DEVICE}),
                         'not_current_speaker')
        self.assertEqual(self.sent[-1]['pairable'], j.sp.speaker_id)
        self.assertEqual(await control({'action': 'pair', 'speaker_id': j.sp.speaker_id, **DEVICE}), 'paired')
        self.assertEqual(self.book.owner_id, 2)
        self.assertEqual(self.sent[-1]['owner_name'], 'ミナ')
        self.assertEqual(self.sent[-1]['owner'], j.sp.speaker_id)
        self.assertEqual(self.sent[-1]['pairable'], '')
        # only the hash of the secret is stored
        self.assertEqual(self.pairs[DEVICE['device_id']][0], hashlib.sha256(DEVICE['secret'].encode()).hexdigest())

        fresh = SpeakerBook(self.store)
        fresh.known = self.book.known
        self.assertEqual(await fresh.app_control({'action': 'hello', **DEVICE}), 'owner')
        self.assertEqual(fresh.owner_id, 2)
        self.assertEqual(await fresh.app_control({'action': 'hello', 'device_id': DEVICE['device_id'],
                                                  'secret': 'x' * 32}), 'no_owner')
        self.assertIsNone(fresh.owner_id)
        self.assertEqual(await fresh.app_control({'action': 'unpair', 'device_id': DEVICE['device_id'],
                                                  'secret': 'x' * 32}), 'not_paired')
        self.assertEqual(await fresh.app_control({'action': 'unpair', **DEVICE}), 'unpaired')
        self.assertEqual(self.pairs, {})

    async def test_bad_device_messages_are_refused(self):
        control = self.book.app_control
        self.assertEqual(await control({'action': 'hello', 'device_id': 'a b', 'secret': 's' * 32}), 'invalid_device')
        self.assertEqual(await control({'action': 'hello', 'device_id': DEVICE['device_id'], 'secret': 'short'}),
                         'invalid_device')
        self.assertEqual(await control({'action': 'hello', 'device_id': 5, 'secret': None}), 'invalid_device')
        self.store.device_owner.assert_not_called()

    async def test_channel_does_not_contain_the_device_id(self):
        await self.book.app_control({'action': 'hello', **DEVICE})
        self.assertTrue(self.book.channel.startswith('device:'))
        self.assertNotIn(DEVICE['device_id'], self.book.channel)

    async def test_owner_voice_on_a_new_microphone_is_a_maybe_owner_instead_of_a_new_unknown_person(self):
        self.book.owner_id = 1
        j = self.book.judge(near(0, 0.38, 50), 2.0)   # below MAYBE for others, above OWNER_MAYBE
        self.assertEqual(j.sp.person_id, 1)
        self.assertFalse(j.sure)
        self.assertTrue(j.owner)
        j = self.book.judge(near(0, 0.6, 51), 2.0)
        self.assertTrue(j.sure)
        self.assertFalse(any(s.person_id is None for s in self.book.speakers))

    async def test_without_privacy_the_owner_gets_no_priority(self):
        self.book.owner_id = 1
        self.presence = 'public'
        j = self.book.judge(near(0, 0.30, 50), 2.0)
        self.assertIsNone(j.sp.person_id)
        self.assertFalse(j.owner)

    async def test_owner_is_not_sure_when_another_remembered_voice_is_as_close(self):
        self.book.owner_id = 1
        e = (axis(0) + axis(1)) / np.sqrt(2)   # 0.71 to both
        j = self.book.judge(e.astype(np.float32), 2.0)
        self.assertEqual(j.sp.person_id, 1)
        self.assertFalse(j.sure)

    async def test_someone_split_off_from_the_owner_stays_split(self):
        self.book.owner_id = 1
        split = SessionSpeaker(label='知らない人A', split=True)
        split.add(axis(5))
        self.book.speakers.append(split)
        j = self.book.judge(near(5, 0.9, 0), 2.0)
        self.assertIs(j.sp, split)

    async def test_owner_turns_are_added_as_voiceprints_of_this_channel(self):
        await self.book.app_control({'action': 'hello', **DEVICE})
        self.book.owner_id = 1
        for _ in range(8):
            await self.book.identify_parts(self.book.judge(near(0, 0.55, 60), 2.5))
        self.assertEqual(self.store.add_voiceprints.await_count, 6)   # MAX_OWNER_ADAPT
        self.assertEqual(self.store.add_voiceprints.await_args.kwargs['channel'], self.book.channel)


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.book = SpeakerBook(None)
        self.book.known = [Known(1, 'ハカセ', [axis(0)] * 3), Known(2, 'ミナ', [axis(1)] * 3)]
        self.merged = []
        self.book.on_merge = lambda src, dst: self.merged.append((src, dst))

    def unknown_from(self, voices):
        sp = SessionSpeaker(label='知らない人A')
        for v in voices:
            sp.add(v)
        self.book.speakers.append(sp)
        return sp

    async def test_an_unknown_person_whose_voice_keeps_matching_someone_remembered_is_merged_back(self):
        a = self.unknown_from([drifted(0, 0.55, i) for i in range(2)])
        # A's own voice beats the remembered prints, so without recovery it would stay unknown forever
        j = self.book.judge(drifted(0, 0.55, 2), 2.0)
        self.assertEqual(j.sp.person_id, 1)
        self.assertTrue(j.sure)
        self.assertNotIn(a, self.book.speakers)
        self.assertEqual(self.merged[0][0], a)

    async def test_too_few_or_too_far_voices_are_not_merged(self):
        a = self.unknown_from([drifted(0, 0.40, 0)])
        j = self.book.judge(drifted(0, 0.40, 1), 2.0)
        self.assertIs(j.sp, a)   # only two voices so far
        j = self.book.judge(drifted(0, 0.40, 2), 2.0)
        self.assertIs(j.sp, a)   # three, but 0.40 < RECOVER
        self.assertEqual(self.merged, [])

    async def test_named_or_split_people_are_not_merged(self):
        a = self.unknown_from([drifted(0, 0.6, i) for i in range(3)])
        a.name = 'タロウ'
        j = self.book.judge(drifted(0, 0.6, 5), 2.0)
        self.assertIs(j.sp, a)

    async def test_in_a_meeting_someone_already_heard_is_not_merged_into(self):
        self.book.private = lambda: False
        here = self.book._session_for(self.book.known[0])
        here.add(axis(0))
        a = self.unknown_from([drifted(0, 0.6, i) for i in range(3)])
        j = self.book.judge(drifted(0, 0.6, 5), 2.0)
        self.assertIs(j.sp, a)
        self.book.private = lambda: True
        j = self.book.judge(drifted(0, 0.6, 6), 2.0)
        self.assertIs(j.sp, here)

    async def test_owner_recovers_at_a_lower_score_when_private(self):
        self.book.private = lambda: True
        self.book.owner_id = 2
        # the owner prior would catch a new voice; build an unknown that formed before the device said hello
        a = self.unknown_from([drifted(1, 0.45, i) for i in range(2)])
        self.book.owner_id = None
        j = self.book.judge(drifted(1, 0.45, 2), 2.0)
        self.assertIs(j.sp, a)   # 0.45 < RECOVER
        self.book.owner_id = 2
        a.add(drifted(1, 0.45, 3))
        recovered = self.book._recover(a)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered[0].person_id, 2)


class MergePersistTests(unittest.IsolatedAsyncioTestCase):
    async def test_merging_into_a_remembered_person_saves_a_few_voiceprints(self):
        store = SimpleNamespace(add_voiceprints=AsyncMock(return_value=[1]))
        book = SpeakerBook(store)
        book.channel = 'device:abc'
        book.known = [Known(1, 'ハカセ', [axis(0)])]
        remembered = book._session_for(book.known[0])
        other = SessionSpeaker(label='知らない人A')
        for i in range(5):
            other.add(axis(10 + i))
        book.speakers.append(other)
        status = await book.app_control({'action': 'merge', 'speaker_id': other.speaker_id,
                                         'into': remembered.speaker_id})
        self.assertEqual(status, 'merged')
        args = store.add_voiceprints.await_args
        self.assertEqual(args.args[0], 1)
        self.assertEqual(len(args.args[1]), 3)
        self.assertEqual(args.kwargs['channel'], 'device:abc')

    async def test_merging_two_session_people_saves_nothing(self):
        store = SimpleNamespace(add_voiceprints=AsyncMock())
        book = SpeakerBook(store)
        a, b = SessionSpeaker(label='A', name='タロウ'), SessionSpeaker(label='B')
        a.add(axis(0))
        b.add(axis(1))
        book.speakers += [a, b]
        self.assertEqual(await book.app_control({'action': 'merge', 'speaker_id': b.speaker_id, 'into': a.speaker_id}),
                         'merged')
        store.add_voiceprints.assert_not_called()


class GreetingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from speaker_store import Relationship
        self.snapshot = {'blocked': False, 'consent': True, 'notes': [(i, f'note{i}') for i in range(8)],
                         'relationship': Relationship(2, 'feeling', 'mood', 3, 1)}
        self.store = SimpleNamespace(memory_snapshot=AsyncMock(side_effect=lambda pid: self.snapshot))
        self.book = SpeakerBook(self.store)
        self.book.known = [Known(1, 'ハカセ', [axis(0)], notes_ok=True, note_count=8)]
        self.book.owner_id = 1

    async def test_owner_name_recent_notes_and_relationship_when_private(self):
        about = await self.book.greeting_context(True)
        self.assertIn('たぶんハカセさん', about)
        self.assertIn('note7', about)
        self.assertNotIn('note2', about)   # only the recent ones
        self.assertIn('関係', about)

    async def test_nothing_in_public_or_without_owner(self):
        self.assertEqual(await self.book.greeting_context(False), '')
        self.book.owner_id = None
        self.assertEqual(await self.book.greeting_context(True), '')

    async def test_no_notes_without_consent_or_while_forgetting(self):
        self.snapshot['blocked'] = True
        about = await self.book.greeting_context(True)
        self.assertIn('ハカセ', about)
        self.assertNotIn('note', about)
        self.book.known[0].notes_ok = False
        self.snapshot['blocked'] = False
        self.assertNotIn('note', await self.book.greeting_context(True))

    async def test_hello_marks_the_device_known_even_when_it_fails(self):
        book = SpeakerBook(None)
        await book.app_control({'action': 'hello', 'device_id': 'bad id', 'secret': ''})
        self.assertTrue(book.device_known.is_set())


if __name__ == '__main__':
    unittest.main()
