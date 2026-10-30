import asyncio
import types
import unittest
from unittest import mock

import mouth


class FakeSession:
    def __init__(self):
        self.user_state = 'listening'
        self.agent_state = 'listening'
        self.calls = []
        self.userdata = types.SimpleNamespace()

    def generate_reply(self, **kwargs):
        self.calls.append(kwargs)
        return 'handle'


class MouthTest(unittest.IsolatedAsyncioTestCase):
    async def test_say_passes_through_and_counts(self):
        s = FakeSession()
        m = mouth.Mouth(s)
        self.assertEqual(m.say('reply', instructions='x'), 'handle')
        self.assertEqual(s.calls, [{'instructions': 'x'}])
        self.assertEqual(m.counts['reply'], 1)

    async def test_of_uses_the_session_mouth(self):
        s = FakeSession()
        s.userdata.mouth = m = mouth.Mouth(s)
        self.assertIs(mouth.of(s), m)
        self.assertIsInstance(mouth.of(FakeSession()), mouth.Mouth)

    async def test_waits_for_a_pause(self):
        s = FakeSession()
        s.user_state = 'speaking'
        m = mouth.Mouth(s)

        async def stop_talking():
            await asyncio.sleep(0.05)
            s.user_state = 'listening'
        with mock.patch.object(mouth, 'FREE_POLL', 0.01):
            asyncio.create_task(stop_talking())
            self.assertEqual(await m.say_when_free('minutes', wait=1.0, instructions='y'), 'handle')
        self.assertEqual(s.calls, [{'instructions': 'y'}])

    async def test_a_breath_is_not_a_pause(self):
        s = FakeSession()
        m = mouth.Mouth(s)
        said_at = []

        async def breathe():
            for _ in range(3):   # 息つぎ（短い間）をはさみながら話し続ける
                await asyncio.sleep(0.03)
                s.user_state = 'speaking'
                await asyncio.sleep(0.03)
                s.user_state = 'listening'
        with mock.patch.object(mouth, 'FREE_POLL', 0.01):
            talk = asyncio.create_task(breathe())
            await m.say_when_free('minutes', wait=2.0, settle=0.1)
            said_at.append(talk.done())
        self.assertEqual(said_at, [True])   # 話し終えてから言う

    async def test_only_the_latest_notice_is_said(self):
        s = FakeSession()
        s.user_state = 'speaking'
        m = mouth.Mouth(s)
        with mock.patch.object(mouth, 'FREE_POLL', 0.01):
            m.say_latest('minutes', instructions='とり始めた')
            m.say_latest('minutes', instructions='まとめて送る')
            await asyncio.sleep(0.03)
            s.user_state = 'listening'
            await asyncio.sleep(0.05)
            m.say_latest('minutes', instructions='送った')
            await asyncio.sleep(0.05)
        self.assertEqual(s.calls, [{'instructions': 'まとめて送る'}, {'instructions': '送った'}])

    async def test_a_notice_told_in_a_reply_is_not_said_again(self):
        s = FakeSession()
        s.user_state = 'speaking'
        m = mouth.Mouth(s)
        with mock.patch.object(mouth, 'FREE_POLL', 0.01):
            m.say_latest('minutes', instructions='とり始めた')
            self.assertEqual(m.waiting(), {'minutes': 'とり始めた'})
            m.drop('minutes')   # 相手への返事の中で伝え終えた
            s.user_state = 'listening'
            await asyncio.sleep(0.05)
        self.assertEqual(s.calls, [])
        self.assertEqual(m.waiting(), {})

    async def test_gives_up_or_speaks_anyway(self):
        s = FakeSession()
        s.agent_state = 'speaking'
        m = mouth.Mouth(s)
        with mock.patch.object(mouth, 'FREE_POLL', 0.01):
            self.assertIsNone(await m.say_when_free('minutes', wait=0.03))
            self.assertEqual(await m.say_when_free('enrolled', wait=0.03, anyway=True), 'handle')
        self.assertEqual(len(s.calls), 1)


if __name__ == '__main__':
    unittest.main()
