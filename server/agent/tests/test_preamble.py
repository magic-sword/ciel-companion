"""道具を呼んだ返事の前置きを、読み上げている 1 文のあとで止める（emotion.PreambleCut）。"""
import json
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import AsyncMock, patch

import emotion
import minutes as service
from tools import cut_preamble
from tools.minutes import start_minutes
from tools.singing import start_listening_to_song


async def stream(*chunks):
    for c in chunks:
        yield c


class PreambleTests(unittest.IsolatedAsyncioTestCase):
    async def speak(self, cut, speech_id, after_first=None):
        said = []

        async def synthesize(http, text, caption, seconds=None, style=None):
            said.append(text)
            if after_first is not None and len(said) == 1:
                after_first()   # 1 文目を作ったところで道具が呼ばれた
            return b'\0\0' * 480, 48000
        events = Obj(send=AsyncMock())
        with patch.object(emotion, 'synthesize', synthesize):
            frames = [f async for f in emotion.tts_node(
                stream('[happy]いいですね！', 'どんな歌か楽しみです。', '準備ができたら教えてくださいね。'),
                events, stop=lambda: cut.stop(speech_id))]
        return said, frames

    async def test_stops_after_the_sentence_being_spoken(self):
        cut = emotion.PreambleCut()
        said, frames = await self.speak(cut, 'speech_1', after_first=lambda: cut.request(Obj(id='speech_1')))
        self.assertEqual(len(said), 1)
        self.assertTrue(said[0].startswith('いいですね'))
        self.assertTrue(frames)

    async def test_other_replies_are_not_cut(self):
        # 前置きを止めたあとの「どうぞ」（別の返事）は最後まで読む
        cut = emotion.PreambleCut()
        cut.request(Obj(id='speech_1'))
        said, _ = await self.speak(cut, 'speech_2')
        self.assertEqual(len(said), 3)
        said, _ = await self.speak(emotion.PreambleCut(), None)
        self.assertEqual(len(said), 3)

    def test_tool_context_without_cut(self):
        cut_preamble(Obj(userdata=Obj()))   # 前置きを止める係が無くても失敗しない

    async def test_song_and_minutes_tools_ask_to_cut(self):
        cut = emotion.PreambleCut()
        song = Obj(start=lambda: 'started')
        context = Obj(userdata=Obj(song=song, preamble=cut), speech_handle=Obj(id='speech_7'))
        await start_listening_to_song(context)
        self.assertTrue(cut.stop('speech_7'))

        cut = emotion.PreambleCut()
        recorder = Obj(start=lambda lookback, template: service.STARTED,
                       status=lambda: {'recording': True, 'meeting_id': 'm1', 'latest_export': None})
        context = Obj(userdata=Obj(minutes=recorder, preamble=cut), speech_handle=Obj(id='speech_8'))
        await start_minutes(context)
        self.assertTrue(cut.stop('speech_8'))

        cut = emotion.PreambleCut()
        recorder = Obj(start=lambda lookback, template: service.UNKNOWN_TEMPLATE)
        context = Obj(userdata=Obj(minutes=recorder, preamble=cut), speech_handle=Obj(id='speech_9'))
        self.assertEqual(json.loads(await start_minutes(context))['status'], service.UNKNOWN_TEMPLATE)
        self.assertFalse(cut.stop('speech_9'))   # 会話モデルが返事をし直すときは止めない


if __name__ == '__main__':
    unittest.main()
