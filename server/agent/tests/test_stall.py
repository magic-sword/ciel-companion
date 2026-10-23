"""Watchdog: local VAD keeps hearing the user but the realtime model sends no end of turn."""
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch

import turns
from turns import TurnReplies


class Speech:
    def __init__(self, allow_interruptions: bool, done: bool = False) -> None:
        self.id = 'speech_1'
        self.allow_interruptions = allow_interruptions
        self._done = done
        self.interrupted = False
        self.interrupt = Mock()

    def done(self) -> bool:
        return self._done


class StallTests(unittest.IsolatedAsyncioTestCase):
    def make(self, speech, agent_state='listening'):
        activity = SimpleNamespace(_current_speech=speech, _speech_q=[])
        session = SimpleNamespace(agent_state=agent_state, _activity=activity)
        r = TurnReplies(session, None, None, SimpleNamespace(talk='normal', presence='close'), '')
        return r

    def segments(self, r, n):
        for _ in range(n):
            r.on_user_state(SimpleNamespace(new_state='speaking', old_state='listening', created_at=time.time()))
            r.on_user_state(SimpleNamespace(new_state='listening', old_state='speaking', created_at=time.time()))

    async def test_stuck_uninterruptible_speech_is_stopped_once(self):
        speech = Speech(allow_interruptions=False)
        r = self.make(speech, agent_state='thinking')
        r._heard_at -= turns.STALL_SECONDS + 1
        with self.assertLogs('ciel-agent.turns', 'WARNING') as logs:
            self.segments(r, turns.STALL_SEGMENTS + 2)
        speech.interrupt.assert_called_once_with(force=True)
        self.assertIn("'allow_interruptions': False", logs.output[0])

    async def test_end_of_turn_resets_the_watch(self):
        speech = Speech(allow_interruptions=False)
        r = self.make(speech)
        r._heard_at -= turns.STALL_SECONDS + 1
        self.segments(r, turns.STALL_SEGMENTS - 1)
        r.on_transcribed(SimpleNamespace(is_final=True, transcript=''))
        self.segments(r, turns.STALL_SEGMENTS)
        speech.interrupt.assert_not_called()

    async def test_needs_both_time_and_segments(self):
        speech = Speech(allow_interruptions=False)
        r = self.make(speech)
        self.segments(r, turns.STALL_SEGMENTS + 3)   # many segments but recently heard
        speech.interrupt.assert_not_called()

    async def test_normal_speaking_reply_is_not_cut(self):
        # 会話モデルが物音を声とみなさなかっただけのこともあるので、ふつうに話している割り込める話は止めない
        speech = Speech(allow_interruptions=True)
        r = self.make(speech, agent_state='speaking')
        r._heard_at -= turns.STALL_SECONDS + 1
        with self.assertLogs('ciel-agent.turns', 'WARNING'):
            self.segments(r, turns.STALL_SEGMENTS)
        speech.interrupt.assert_not_called()

    async def test_no_speech_only_logs(self):
        r = self.make(None)
        r._heard_at -= turns.STALL_SECONDS + 1
        with patch('turns.debug_log.record') as record, self.assertLogs('ciel-agent.turns', 'WARNING'):
            self.segments(r, turns.STALL_SEGMENTS)
        self.assertEqual(record.call_args.args[0], 'stall')


if __name__ == '__main__':
    unittest.main()
