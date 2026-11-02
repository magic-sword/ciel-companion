import json
import types
import unittest
from unittest import mock

import numpy as np

import soundcheck


class FakeBackchannel:
    def __init__(self, ready=True):
        self.ready = ready
        self.played = []
        self.fitted = 0

    def fit(self, pcm, sr):
        self.fitted += 1
        return ['frame']

    def play_frames(self, frames):
        self.played.append(frames)


def packet(msg, topic=soundcheck.TOPIC):
    return types.SimpleNamespace(topic=topic, data=json.dumps(msg).encode('utf-8'))


def voice():
    pcm = (np.sin(np.arange(4800) / 10) * 8000).astype('<i2').tobytes()
    return pcm, 24000


class SoundCheckTest(unittest.IsolatedAsyncioTestCase):
    async def test_plays_the_line_without_the_conversation_model(self):
        sent, b = [], FakeBackchannel()
        check = soundcheck.SoundCheck(b, sent.append)
        with mock.patch('emotion.synthesize', mock.AsyncMock(return_value=voice())) as synth:
            await check.play()
            await check.play()   # 2 回目は読み上げ直さない
        self.assertEqual(synth.await_count, 1)
        self.assertEqual(synth.await_args.args[1], soundcheck.LINE)
        self.assertEqual(b.played, [['frame'], ['frame']])
        self.assertEqual(sent[-1], {'v': 1, 'type': 'voice.test', 'state': 'playing'})

    async def test_not_ready_and_tts_failure_are_reported(self):
        sent = []
        await soundcheck.SoundCheck(None, sent.append).play()
        await soundcheck.SoundCheck(FakeBackchannel(ready=False), sent.append).play()
        with mock.patch('emotion.synthesize', mock.AsyncMock(side_effect=OSError('down'))):
            await soundcheck.SoundCheck(FakeBackchannel(), sent.append).play()
        self.assertEqual([m.get('reason') for m in sent], ['not_ready', 'not_ready', 'tts'])
        self.assertTrue(all(m['state'] == 'failed' for m in sent))

    async def test_on_data_only_reacts_to_its_topic(self):
        sent, b = [], FakeBackchannel()
        check = soundcheck.SoundCheck(b, sent.append)
        with mock.patch('emotion.synthesize', mock.AsyncMock(return_value=voice())):
            check.on_data(packet({'v': 1, 'type': 'voice.test'}, topic='ciel.volume'))
            check.on_data(packet({'v': 1, 'type': 'other'}))
            self.assertIsNone(check._task)
            check.on_data(packet({'v': 1, 'type': 'voice.test'}))
            await check._task
        self.assertEqual(len(b.played), 1)


if __name__ == '__main__':
    unittest.main()
