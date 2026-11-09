"""Offline streaming contracts. Native decoder speed/accuracy is measured on the home server."""
import ast
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
from livekit import rtc
from livekit.agents import APIConnectOptions, stt
import speech_input
import vosk_stt
from vosk_engine import text

class SettingsTest(unittest.TestCase):
    def test_local_defaults_to_cpu_voice_and_text_is_explicit(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(speech_input.settings(True), ('voice','vosk'))
            self.assertEqual(speech_input.settings(False), ('voice','openai'))
        with mock.patch.dict(os.environ, {'CIEL_INPUT':'text'}, clear=True):
            self.assertEqual(speech_input.settings(True), ('text','vosk'))

    def test_no_paid_voice_fallback_in_local_mode(self):
        with mock.patch.dict(os.environ, {'CIEL_STT_BACKEND':'openai'}, clear=True):
            with self.assertRaisesRegex(ValueError,'fallback'):
                speech_input.settings(True)

    def test_invalid_settings_and_missing_model_fail_explicitly(self):
        with mock.patch.dict(os.environ, {'CIEL_STT_BACKEND':'unknown'}, clear=True):
            with self.assertRaises(ValueError):speech_input.settings(True)
        with mock.patch.dict(os.environ, {'CIEL_VOSK_MODEL_PATH':'not-present-vosk-model'}, clear=True):
            with self.assertRaises(FileNotFoundError):speech_input.local_stt()

    def test_japanese_token_spaces_do_not_break_stop_requests(self):
        self.assertEqual(text('作業 を 止め て'), '作業を止めて')
        self.assertEqual(text('stone pickaxe'), 'stone pickaxe')

    def test_pipeline_local_branch_never_constructs_openai_stt(self):
        # Execute the actual factory without starting the agent worker/server.
        tree=ast.parse((Path(__file__).parents[1]/'agent.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='make_pipeline')
        namespace=dict(TEXT_ONLY=False,STT_BACKEND='vosk',speech_input=mock.Mock(),openai=mock.Mock(),
            inference=mock.Mock(),ENDPOINT_MODE='dynamic',ENDPOINT_MIN=.6,ENDPOINT_MAX=1.5,
            interruptions=SimpleNamespace(CONFIRM_SECONDS=.5))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'agent.py','exec'),namespace)
        result=namespace['make_pipeline']([])
        namespace['openai'].STT.assert_not_called()
        self.assertIs(result['stt'],namespace['speech_input'].local_stt.return_value)
        namespace['TEXT_ONLY']=True
        self.assertEqual(namespace['make_pipeline']([]), {'turn_detection':'manual'})

class StreamTest(unittest.IsolatedAsyncioTestCase):
    async def test_interim_arrives_before_eof_and_final_is_not_duplicated(self):
        decoder=mock.Mock()
        decoder.feed.side_effect=[(False,'止め'),(False,'止め'),(True,'止めて')]
        decoder.finish.return_value=''
        with mock.patch.object(vosk_stt,'Decoder',return_value=decoder):
            engine=vosk_stt.VoskSTT('/model')
            stream=engine.stream(conn_options=APIConnectOptions(max_retry=0))
            events=[]
            async def consume():
                async for e in stream:events.append(e)
            consumer=asyncio.create_task(consume())
            try:
                stream.push_frame(rtc.AudioFrame(bytes(320),16000,1,160))
                for _ in range(100):
                    if any(e.type==stt.SpeechEventType.INTERIM_TRANSCRIPT for e in events):break
                    await asyncio.sleep(.005)
                self.assertTrue(any(e.type==stt.SpeechEventType.INTERIM_TRANSCRIPT for e in events))
                for _ in range(2):stream.push_frame(rtc.AudioFrame(bytes(320),16000,1,160))
                stream.end_input();await asyncio.wait_for(consumer,3)
                finals=[e.alternatives[0].text for e in events if e.type==stt.SpeechEventType.FINAL_TRANSCRIPT]
                self.assertEqual(finals,['止めて'])
                self.assertEqual(sum(e.type==stt.SpeechEventType.INTERIM_TRANSCRIPT for e in events),1)
                self.assertEqual(sum(e.type==stt.SpeechEventType.END_OF_SPEECH for e in events),1)
            finally:await stream.aclose()

    async def test_eof_flush_delivers_only_confirmed_tail(self):
        decoder=mock.Mock();decoder.feed.return_value=(False,'作業');decoder.finish.return_value='作業を止めて'
        with mock.patch.object(vosk_stt,'Decoder',return_value=decoder):
            stream=vosk_stt.VoskSTT('/model').stream(conn_options=APIConnectOptions(max_retry=0))
            try:
                stream.push_frame(rtc.AudioFrame(bytes(320),16000,1,160));stream.end_input()
                events=[e async for e in stream]
                self.assertEqual([e.alternatives[0].text for e in events if e.type==stt.SpeechEventType.FINAL_TRANSCRIPT],['作業を止めて'])
            finally:await stream.aclose()
