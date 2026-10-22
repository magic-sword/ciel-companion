import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np

import interruptions
import speakers
from turns import TurnReplies


class FakeRealtime:
    def __init__(self):
        self.handlers = {}

    def on(self, event, fn):
        self.handlers.setdefault(event, []).append(fn)

    def off(self, event, fn):
        self.handlers[event].remove(fn)

    def emit(self, event, ev=None):
        for fn in list(self.handlers.get(event, [])):
            fn(ev)


class FakeActivity:
    """LiveKit の AgentActivity の代わり：話し始めの知らせで、状態を更新してから声を止める"""

    def __init__(self, session):
        self.session = session
        self._rt_session = FakeRealtime()
        self._rt_session.on('input_speech_started', self._on_input_speech_started)
        self.stopped = 0

    def _on_input_speech_started(self, ev):
        self.session.user_state = 'speaking'
        self.interrupt(source='audio_activity')

    def interrupt(self, **kwargs):
        self.stopped += 1


class FakeTap:
    def __init__(self):
        self.loud = 0.0

    def window(self, start, end):
        n = int(self.loud * speakers.SR)
        return np.full(n, 0.1, np.float32)   # -20 dB：声とみなす大きさ


class InterruptionGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = SimpleNamespace(agent_state='speaking', user_state='listening', interrupt=Mock())
        self.session._activity = FakeActivity(self.session)
        self.tap = FakeTap()
        self.gate = interruptions.InterruptionGate(self.session, self.tap, confirm_seconds=0.6)
        self.assertTrue(self.gate.install())

    def speech_started(self):
        self.session._activity._rt_session.emit('input_speech_started')

    async def test_when_ciel_is_quiet_speech_start_works_as_before(self):
        self.session.agent_state = 'listening'
        self.speech_started()
        self.assertEqual(self.session._activity.stopped, 1)
        self.assertEqual(self.session.user_state, 'speaking')
        self.assertFalse(self.gate.end_of_turn())

    async def test_short_voice_while_ciel_speaks_does_not_stop_her_and_gets_no_reply(self):
        self.tap.loud = 0.3   # 咳・「うん」くらい
        self.speech_started()
        self.assertEqual(self.session.user_state, 'speaking')   # 状態は今までどおり更新する
        self.assertEqual(self.session._activity.stopped, 0)     # 声は止めない
        await asyncio.sleep(0.15)
        self.session.interrupt.assert_not_called()
        self.assertTrue(self.gate.end_of_turn())

    async def test_sustained_voice_while_ciel_speaks_stops_her(self):
        self.tap.loud = 1.0   # 「ちょっと待って、シエル」くらい
        self.speech_started()
        await asyncio.sleep(0.15)
        self.session.interrupt.assert_called_once()
        self.assertFalse(self.gate.end_of_turn())   # 止めた発言には、ふつうに返事をする

    async def test_ciel_finishing_on_her_own_makes_it_a_normal_turn(self):
        self.tap.loud = 0.2
        self.speech_started()
        self.session.agent_state = 'listening'
        await asyncio.sleep(0.15)
        self.session.interrupt.assert_not_called()
        self.assertFalse(self.gate.end_of_turn())

    async def test_keeps_old_behaviour_when_livekit_internals_differ(self):
        gate = interruptions.InterruptionGate(SimpleNamespace(agent_state='speaking'), self.tap)
        self.assertFalse(gate.install())

    async def test_turns_skip_the_reply_for_an_ignored_overlap(self):
        replies = TurnReplies(SimpleNamespace(), None, None, SimpleNamespace(talk='normal'), '')
        replies.overlap = SimpleNamespace(end_of_turn=lambda: True)
        replies._settle = Mock()
        replies.on_transcribed(SimpleNamespace(is_final=False, transcript=''))
        replies._settle.assert_not_called()


if __name__ == '__main__':
    unittest.main()
