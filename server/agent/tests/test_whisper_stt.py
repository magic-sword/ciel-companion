"""Local ASR stays offline, preserves transcript semantics, and resamples correctly."""
import os
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import patch, Mock

import numpy as np
from livekit import rtc
from livekit.agents import stt
import speech_input
import whisper_engine
from whisper_stt import WhisperSTT


class WhisperTest(unittest.IsolatedAsyncioTestCase):
    def test_subsecond_full_hint_echo_is_dropped_but_name_and_long_speech_survive(self):
        prompt = 'シエル、マインクラフト、議事録。'
        model = Mock()
        with patch('whisper_engine.load_model', return_value=model):
            for seconds, text, expected in [(.6, prompt, ''), (.6, 'シエル。', 'シエル。'),
                                            (3, prompt, prompt), (.6, '議事録を始めないで', '議事録を始めないで')]:
                model.transcribe.return_value = (iter([Obj(text=text)]), None)
                self.assertEqual(whisper_engine.recognize('offline', np.zeros(int(16000*seconds)), prompt), expected)
            model.transcribe.return_value = (iter([Obj(text='シエル')]), None)
            self.assertEqual(whisper_engine.recognize('offline', np.zeros(9600), 'シエル'), 'シエル')
            model.transcribe.return_value = (iter([Obj(text=prompt)]), None)
            self.assertEqual(whisper_engine.recognize('offline', np.zeros(9600), prompt+'\n田中'), '')

    async def test_resamples_without_rewriting_names_or_negation(self):
        engine = WhisperSTT('/offline/small', 'vocabulary')
        frames = [rtc.AudioFrame(bytes(4800*2), 48000, 1, 4800) for _ in range(2)]
        with patch('whisper_engine.recognize', return_value='シールは貼らない。') as recognize:
            event = await engine.recognize(frames)
        self.assertEqual(event.type, stt.SpeechEventType.FINAL_TRANSCRIPT)
        self.assertEqual(event.alternatives[0].text, 'シールは貼らない。')
        path, audio, prompt = recognize.call_args.args
        self.assertEqual((path, prompt), ('/offline/small', 'vocabulary'))
        self.assertFalse(recognize.call_args.kwargs['vad_filter'])
        self.assertEqual(audio.dtype, np.float32)
        self.assertLessEqual(abs(len(audio)-3200), 2)

    async def test_empty_speech_stays_empty(self):
        with patch('whisper_engine.recognize', return_value=''):
            event = await WhisperSTT('/offline/small').recognize(rtc.AudioFrame(bytes(320),16000,1,160))
        self.assertEqual(event.alternatives[0].text, '')

    def test_cpu_model_never_downloads_or_enables_gpu(self):
        factory = Mock(return_value=Obj(transcribe=Mock(return_value=(iter([Obj(text='三個ではない')]),None))))
        with patch.dict('sys.modules', {'faster_whisper':Obj(WhisperModel=factory)}), patch.dict(whisper_engine._models, {}, clear=True):
            self.assertEqual(whisper_engine.recognize('/offline/small','audio','names'), '三個ではない')
            whisper_engine.load_model('/offline/small')
        factory.assert_called_once_with('/offline/small',device='cpu',compute_type='int8',cpu_threads=4,num_workers=1,local_files_only=True)
        kwargs=factory.return_value.transcribe.call_args.kwargs
        self.assertFalse(kwargs['condition_on_previous_text'])
        self.assertTrue(kwargs['vad_filter'])

    def test_explicit_backend_and_missing_model(self):
        with patch.dict(os.environ, {'CIEL_STT_BACKEND':'whisper','CIEL_WHISPER_MODEL_PATH':'missing-whisper-directory'},clear=True):
            self.assertEqual(speech_input.settings(True), ('voice','whisper'))
            with self.assertRaises(FileNotFoundError):speech_input.local_stt(vad=Mock())
        with patch.dict(os.environ, {'CIEL_STT_BACKEND':'whisper'},clear=True), patch('whisper_engine.load_model') as load:
            speech_input.prepare()
            load.assert_called_once_with('/models-whisper/small')

    def test_stream_adapter_uses_same_vad_and_keeps_vocabulary_separate(self):
        vad=Mock()
        with patch.dict(os.environ, {'CIEL_STT_BACKEND':'whisper'},clear=True), patch('pathlib.Path.is_dir',return_value=True), \
             patch('persona.load_persona',return_value=Obj(stt_vocabulary='シエル')):
            adapter=speech_input.local_stt(vad=vad,names=['田中','田中'])
        self.assertIs(adapter._vad,vad)
        self.assertEqual(adapter.wrapped_stt.prompt,'シエル\n田中')
        self.assertFalse(adapter.capabilities.interim_results)
