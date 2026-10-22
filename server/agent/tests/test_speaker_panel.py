"""The app's participant panel: roster updates and session-only corrections."""
import json
from types import SimpleNamespace
import unittest

import numpy as np
from conversation import Conversation
from speakers import SpeakerBook, NameRegistration, Known, SessionSpeaker, APP_TOPIC


def voice(i: int) -> np.ndarray:
    e = np.zeros(192)
    e[i] = 1.0
    return e


class PanelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.book = SpeakerBook(None)
        self.sent = []
        self.book.on_change = self.sent.append
        self.history = Conversation()
        self.book.on_split = self.history.on_split
        self.book.on_merge = self.history.on_merge

    def turn(self, j, text='hello'):
        t = self.history.reserve()
        self.history.complete(t, text, j.sp, SpeakerBook.label(j), j.sure)
        return t

    async def test_each_judgment_publishes_who_spoke_without_voice_data(self):
        a = self.book.judge(voice(0), 2.0)
        self.book.judge(voice(0), 2.0)
        state = self.sent[-1]
        self.assertEqual(state['type'], 'speakers.state')
        self.assertEqual(state['speaking'], a.sp.speaker_id)
        self.assertEqual(state['heard'], 2)
        self.assertEqual(len(self.sent), 2)   # the same speaker twice still lights up again
        self.assertEqual(state['speakers'], [{'id': a.sp.speaker_id, 'name': a.sp.label, 'named': False,
                                              'remembered': False}])
        self.book.judge(None, 0.3)   # too short: keep the highlighted speaker
        self.assertEqual(self.sent[-1]['speaking'], a.sp.speaker_id)

    async def test_naming_is_session_only_and_relabels_history(self):
        j = self.book.judge(voice(0), 2.0)
        t = self.turn(j)
        status = await self.book.app_control({'action': 'name', 'speaker_id': j.sp.speaker_id, 'name': 'ハカセさん'})
        self.assertEqual(status, 'session_named')
        self.assertEqual(j.sp.name, 'ハカセ')
        self.assertIsNone(j.sp.person_id)
        self.assertEqual(t.name, 'ハカセ')
        self.assertEqual(self.sent[-1]['speakers'][0]['name'], 'ハカセ')

    async def test_naming_refuses_remembered_people_duplicates_and_bad_input(self):
        remembered = SessionSpeaker(label='ハカセ', person_id=1, name='ハカセ')
        other = SessionSpeaker(label='知らない人A')
        self.book.speakers += [remembered, other]
        control = self.book.app_control
        self.assertEqual(await control({'action': 'name', 'speaker_id': remembered.speaker_id, 'name': 'X'}), 'remembered')
        self.assertEqual(await control({'action': 'name', 'speaker_id': other.speaker_id, 'name': 'ハカセ'}), 'name_taken')
        self.assertEqual(await control({'action': 'name', 'speaker_id': other.speaker_id, 'name': ' '}), 'invalid_name')
        self.assertEqual(await control({'action': 'name', 'speaker_id': other.speaker_id, 'name': 7}), 'invalid_name')
        self.assertEqual(await control({'action': 'name', 'speaker_id': 'nope', 'name': 'Y'}), 'speaker_not_found')
        self.assertIsNone(other.name)

    async def test_naming_binds_a_pending_introduction(self):
        entry = NameRegistration('ミナ', 'introduced')
        self.book.name_registrations[entry.registration_id] = entry
        j = self.book.judge(voice(0), 2.0)
        await self.book.app_control({'action': 'name', 'speaker_id': j.sp.speaker_id, 'name': 'ミナ'})
        self.assertEqual(entry.speaker_id, j.sp.speaker_id)
        self.assertEqual(entry.stage, 'session_named')

    async def test_merge_joins_two_voices_and_their_history(self):
        a = self.book.judge(voice(0), 2.0)
        b = self.book.judge(voice(1), 2.0)
        ta, tb = self.turn(a), self.turn(b)
        self.book.last = b.sp
        await self.book.app_control({'action': 'name', 'speaker_id': a.sp.speaker_id, 'name': 'ハカセ'})
        status = await self.book.app_control({'action': 'merge', 'speaker_id': b.sp.speaker_id, 'into': a.sp.speaker_id})
        self.assertEqual(status, 'merged')
        self.assertEqual([s.speaker_id for s in self.book.speakers], [a.sp.speaker_id])
        self.assertIs(tb.speaker, a.sp)
        self.assertEqual(tb.name, 'ハカセ')
        self.assertIs(self.book.last, a.sp)
        self.assertEqual(self.sent[-1]['speaking'], a.sp.speaker_id)
        self.assertIs(self.book.judge(voice(1), 2.0).sp, a.sp)   # the merged voice now matches the same person

    async def test_merge_keeps_the_remembered_person_in_memory_only(self):
        k = Known(1, 'ハカセ', [voice(0)])
        self.book.known.append(k)
        remembered = self.book.judge(voice(0), 2.0).sp
        unknown = self.book.judge(voice(1), 2.0).sp
        status = await self.book.app_control({'action': 'merge', 'speaker_id': remembered.speaker_id,
                                              'into': unknown.speaker_id})
        self.assertEqual(status, 'merged')
        self.assertEqual(self.book.speakers, [remembered])
        self.assertEqual(len(k.embeddings), 2)
        other = SessionSpeaker(label='ミナ', person_id=2, name='ミナ')
        self.book.speakers.append(other)
        self.assertEqual(await self.book.app_control({'action': 'merge', 'speaker_id': other.speaker_id,
                                                      'into': remembered.speaker_id}), 'both_remembered')

    async def test_split_only_for_the_named_last_speaker(self):
        j = self.book.judge(voice(0), 2.0)
        await self.book.identify_parts(j)
        self.assertEqual(self.sent[-1]['correctable'], '')   # unnamed: nothing to be wrong about
        await self.book.app_control({'action': 'name', 'speaker_id': j.sp.speaker_id, 'name': 'ハカセ'})
        self.assertEqual(self.sent[-1]['correctable'], j.sp.speaker_id)
        other = SessionSpeaker(label='知らない人B')
        self.book.speakers.append(other)
        self.assertEqual(await self.book.app_control({'action': 'split', 'speaker_id': other.speaker_id}),
                         'not_current_speaker')
        t, before = self.turn(j), j.sp
        self.assertEqual(await self.book.app_control({'action': 'split', 'speaker_id': j.sp.speaker_id}), 'split')
        self.assertEqual(len(self.book.speakers), 3)
        self.assertIsNot(t.speaker, before)
        self.assertIs(t.speaker, self.book.last)
        self.assertEqual(self.sent[-1]['speaking'], self.book.last.speaker_id)

    async def test_on_data_ignores_other_topics_and_bad_messages(self):
        j = self.book.judge(voice(0), 2.0)
        packet = lambda topic, data: SimpleNamespace(topic=topic, data=data)
        self.book.on_data(packet('ciel.minutes', b'{"action":"name"}'))
        self.book.on_data(packet(APP_TOPIC, b'not json'))
        self.book.on_data(packet(APP_TOPIC, b'[1]'))
        self.assertFalse(self.book._app_tasks)
        msg = {'v': 1, 'type': 'speakers.control', 'action': 'name', 'speaker_id': j.sp.speaker_id, 'name': 'ミナ'}
        self.book.on_data(packet(APP_TOPIC, json.dumps(msg).encode()))
        for task in list(self.book._app_tasks):
            await task
        self.assertEqual(j.sp.name, 'ミナ')


if __name__ == '__main__':
    unittest.main()
