import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import inference_activity
from recall import Idea
import speak_up


class Handle:
    def __init__(self):
        self.finished = False
        self.interrupt = MagicMock(side_effect=lambda force=False: setattr(self, 'finished', True))

    def done(self):
        return self.finished


class Turn(SimpleNamespace):
    pass


def turn(id, role='user', text='話'):
    t = Turn(id=id, role=role, text=text, ready=asyncio.Event())
    t.ready.set()
    return t


class SpeakUpTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.t = [0.0]
        self.session = SimpleNamespace(current_speech=None, user_state='listening')
        self.said = []
        self.mouth = SimpleNamespace(say=lambda why, **kw: self.said.append((why, kw)) or Handle())
        self.mind = SimpleNamespace(ideas=[])
        self.history = SimpleNamespace(turns=[turn(1)])
        self.up = speak_up.SpeakUp(self.session, self.mouth, self.mind, self.history, '話したい：{idea}',
                                   clock=lambda: self.t[0])
        patcher = patch.object(inference_activity.activity, 'generating', 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def idea(self, text='丸石で拠点を作ろう', level=4.0, turn=1):
        return Idea('suggest', '準備', text, [], [], round(level), level, turn, 0.0)

    def playing(self):
        self.session.current_speech = Handle()   # 返事 N を話している
        self.up.step()

    def test_high_fresh_idea_while_reply_plays_is_asked_once(self):
        self.up.replied('倒れないための準備ですね。')
        self.playing()
        self.mind.ideas = [self.idea(level=3.2), self.idea(level=4.1)]
        self.up.step()
        self.assertEqual(len(self.said), 1)
        why, kw = self.said[0]
        self.assertEqual((why, kw['instructions'], kw['tool_choice']), ('idea', '話したい：丸石で拠点を作ろう', 'none'))
        self.assertEqual(self.mind.ideas, [])
        self.up.step()
        self.assertEqual(len(self.said), 1)

    def test_low_repeat_stale_mode_or_late_ideas_are_dropped(self):
        cases = {
            'low': dict(idea=self.idea(level=3.4)),
            'repeat': dict(idea=self.idea(text='鎖は鉄インゴット1個と鉄塊2個'), reply='鎖を作るには鉄インゴット1個と鉄塊2個が要るのです'),
            'stale': dict(idea=self.idea(turn=0)),
            'mode': dict(idea=self.idea(), allowed=False),
            'late': dict(idea=self.idea(), late=True),
        }
        for name, c in cases.items():
            with self.subTest(name):
                self.said.clear()
                self.up = speak_up.SpeakUp(self.session, self.mouth, self.mind, self.history, '{idea}',
                                           allowed=lambda: c.get('allowed', True), clock=lambda: self.t[0])
                self.up.replied(c.get('reply', 'そうですね'))
                self.playing()
                if c.get('late'):
                    self.session.current_speech.finished = True
                    self.up.step()
                    self.t[0] += speak_up.SpeakUp.LATE + 1
                self.mind.ideas = [c['idea']]
                self.up.step()
                self.assertEqual(self.said, [])

    def test_unanswered_raises_the_threshold_and_an_answer_resets_it(self):
        self.up.spoken_at = 0.0
        self.t[0] = speak_up.SpeakUp.ANSWER + 1
        self.history.turns.append(turn(2))
        self.up.step()
        self.assertEqual(self.up.unanswered, 1)
        self.assertEqual(self.up.threshold, speak_up.SpeakUp.HIGH + speak_up.SpeakUp.STEP)
        self.up.spoken_at = self.t[0]
        self.history.turns.append(turn(3))
        self.up.step()
        self.assertEqual(self.up.unanswered, 0)

    async def test_hold_speaks_after_the_gap_and_drops_when_the_user_starts(self):
        async def source():
            yield 'こんにちは'
        real = [0.0]
        self.up.clock = lambda: real[0]
        self.up.reply_ended = 0.0

        async def tick():
            while True:
                await asyncio.sleep(0.01)
                real[0] += 0.1
        ticker = asyncio.create_task(tick())
        try:
            got = [c async for c in self.up.hold(source())]
            self.assertEqual(got, ['こんにちは'])
            self.assertIsNotNone(self.up.spoken_at)
            self.up.handle = Handle()
            self.up.on_user_state(SimpleNamespace(new_state='speaking'))
            self.assertIsNone(self.up.handle)
            got = [c async for c in self.up.hold(source())]
            self.assertEqual(got, [])
        finally:
            ticker.cancel()

    def test_overlap(self):
        self.assertEqual(speak_up.overlap('', 'x'), 0.0)
        self.assertGreater(speak_up.overlap('鉄インゴット1個', '鉄インゴット1個と鉄塊'), 0.9)


if __name__ == '__main__':
    unittest.main()
