import unittest
from types import SimpleNamespace as Obj
from unittest.mock import patch
from livekit import rtc
from speech_vocabulary import terms, game_terms
from whisper_stt import WhisperSTT


class VocabularyTests(unittest.IsolatedAsyncioTestCase):
    def test_untrusted_shape_and_limits(self):
        valid=dict(version=1,language='ja',terms=['原木','整地','原木'])
        self.assertEqual(terms(valid),('原木','整地'))
        for change in (dict(version=True),dict(version=2),dict(language='en'),dict(terms='原木'),
                       dict(terms=['a']*65),dict(terms=['x'*25]),dict(terms=['原木\n実行']),
                       dict(terms=[str(i)+'x'*20 for i in range(30)])):
            self.assertEqual(terms({**valid,**change}),())

    async def test_link_switch_disconnect_and_snapshot(self):
        game=Obj(linked=False,profile=dict(speech_vocabulary=dict(version=1,language='ja',terms=['原木'])))
        self.assertEqual(game_terms(game),())
        engine=WhisperSTT('/offline/small','base',vocabulary=lambda:game_terms(game))
        frame=rtc.AudioFrame(bytes(3200),16000,1,1600)
        async def decode(fn,path,audio,prompt,**kwargs):
            game.linked=False  # Disconnect while recognition is in flight.
            return prompt
        game.linked=True
        with patch('whisper_stt.asyncio.to_thread',side_effect=decode):
            event=await engine.recognize(frame)
            self.assertEqual(event.alternatives[0].text,'base\n原木')
            event=await engine.recognize(frame)
            self.assertEqual(event.alternatives[0].text,'base')
            game.linked=True
            game.profile=dict(speech_vocabulary=dict(version=1,language='ja',terms=['別ゲーム']))
            event=await engine.recognize(frame)
            self.assertEqual(event.alternatives[0].text,'base\n別ゲーム')
        self.assertEqual(game_terms(None),())

if __name__=='__main__':unittest.main()
