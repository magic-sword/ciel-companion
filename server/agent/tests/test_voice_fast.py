"""Admission fairness, safe speech boundaries and real preparation ordering."""
import asyncio
import importlib.util
from pathlib import Path
import threading
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import emotion
import models
import voice_preparation

spec = importlib.util.spec_from_file_location('voice_gateway', Path(__file__).parents[2]/'local-llm/gateway.py')
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class AdmissionTest(unittest.TestCase):
    def test_background_reserves_capacity_and_foreground_overtakes_waiter(self):
        gate = gateway.Admission(2)
        gate.acquire('background')
        bg_started = threading.Event()
        def background():
            gate.acquire('background', timeout=2)
            bg_started.set()
            gate.release('background')
        thread = threading.Thread(target=background)
        thread.start()
        gate.acquire('foreground', timeout=.2)
        self.assertEqual((gate.active, gate.background), (2, 1))
        self.assertFalse(bg_started.is_set())
        gate.release('foreground')
        gate.release('background')
        thread.join(2)
        self.assertTrue(bg_started.is_set())
        self.assertEqual(gate.active, 0)

    def test_timeout_removes_ticket_and_unknown_classes_are_refused(self):
        gate = gateway.Admission(1)
        gate.acquire('foreground')
        with self.assertRaises(TimeoutError):
            gate.acquire('background', timeout=.001)
        self.assertFalse(gate.waiting)
        gate.release('foreground')
        with self.assertRaises(ValueError):
            gate.acquire('urgent')
        gate.acquire('background', timeout=.01)
        gate.release('background')

    def test_only_local_background_roles_receive_background_class(self):
        with patch('models.is_local', return_value=True), patch.dict('os.environ', {'CIEL_VOICE_FAST':'1'}):
            self.assertEqual(models.options('thought')['extra_headers']['X-Ciel-Work-Class'], 'background')
            self.assertEqual(models.options('listener')['extra_headers']['X-Ciel-Work-Class'], 'foreground')
        with patch('models.is_local', return_value=False):
            self.assertNotIn('extra_headers', models.options('thought'))


class ClauseTest(unittest.TestCase):
    def test_early_clause_is_lossless_and_does_not_split_numbers_or_negation(self):
        text = '[happy]今日はたくさん歩いたから、少し休もう。'
        parts, tail = emotion.split_sentences(text, early=True)
        self.assertEqual(len(parts), 2)
        self.assertEqual(''.join(parts)+tail, text)
        for text in ['予算は1,234円、', '今日は出かけないで、', '[happy', '佐藤さん、鈴木さん、']:
            parts, tail = emotion.split_sentences(text, early=True)
            self.assertEqual(parts, [])
            self.assertEqual(tail, text)


class PreparationTest(unittest.IsolatedAsyncioTestCase):
    async def test_preparation_never_records_a_user_turn_or_plays_audio(self):
        client = Obj(chat=Obj(completions=Obj(create=AsyncMock())), close=AsyncMock())
        agent = Obj(persona=Obj(voice_warmup='fixture speech', fingerprint='fixture'),
                    talker_instructions_for=lambda *args: 'fixture system')
        with patch('voice_preparation.models.create_client', return_value=client), \
             patch('voice_preparation.mode_snapshot', AsyncMock(return_value={'model':'fixture','mode':'gpu','generation':'1'})), \
             patch('vosk_engine.load_model', return_value=object()), \
             patch('voice_preparation.irodori_tts.request_audio', AsyncMock(return_value=(bytes(640),16000))):
            result = await voice_preparation.prepare(agent, Obj())
        self.assertTrue(result['ready'])
        self.assertEqual(set(result['stages']), {'stt','llm','tts'})
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs['max_tokens'], 1)
        self.assertEqual(kwargs['extra_headers']['X-Ciel-Work-Class'], 'background')
        client.close.assert_awaited_once()

    async def test_failed_encoder_never_claims_ready(self):
        task = asyncio.create_task(asyncio.sleep(0))
        with patch('voice_preparation.mode_snapshot', AsyncMock(return_value={})), self.assertRaisesRegex(RuntimeError, 'encoder'):
            await voice_preparation.prepare(Obj(), Obj(encoder=None), task)

    async def test_mode_change_invalidates_readiness_without_silently_rewarming(self):
        original = {'ready':True, 'inference':{'generation':'old'}}
        with patch('voice_preparation.mode_snapshot', AsyncMock(return_value={'generation':'new'})):
            result = await voice_preparation.validate(original)
        self.assertFalse(result['ready'])
        self.assertTrue(original['ready'])
        self.assertEqual(result['reason'], 'inference_generation_changed')
