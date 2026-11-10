"""Scoring edge cases and replay timing without models, credentials or audio APIs."""
import importlib.util
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import wave

from voice_benchmark import corpus, distribution, normalize, score, summarize

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('benchmark_voice', ROOT/'scripts/server/benchmark-voice.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class VoiceBenchmarkTest(unittest.TestCase):
    def test_staged_provenance_checks_the_actual_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'source.json'
            files = ('scripts/server/benchmark-voice.py', 'server/agent/voice_benchmark.py', 'server/agent/vosk_engine.py')
            data = dict(git_commit='a'*40, git_dirty=True,
                        source_sha256={name: runner.sha256(ROOT/name) for name in files})
            path.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(runner.source_identity(path)['git_commit'], 'a'*40)
            data['source_sha256'][files[0]] = '0'*64
            path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                runner.source_identity(path)

    def test_japanese_normalization_and_errors(self):
        self.assertEqual(normalize(' ＡＢＣ、シエル。 '), 'abcシエル')
        self.assertEqual(score('あいう', 'あえう')['cer'], 1/3)
        self.assertEqual(score('あ', 'あいう')['cer'], 2)
        # Do not silently equate homophones or erase negation/numbers.
        self.assertFalse(score('橋', '箸')['exact_match'])
        self.assertFalse(score('止めない', '止めて')['exact_match'])
        self.assertFalse(score('三個', '3個')['exact_match'])

    def test_silence_and_micro_average_exclude_unavailable_transcripts(self):
        rows = [dict(status='ok', **score('あいう', 'あえう')),
                dict(status='ok', **score('あ', '')),
                dict(status='ok', **score('', '幻覚')),
                dict(status='error')]
        result = summarize(rows)
        self.assertEqual(result['cer'], .5)
        self.assertEqual(result['scored_trials'], 3)
        self.assertEqual(result['failures'], 1)
        self.assertEqual(result['silence_false_positive_rate'], 1)
        self.assertIsNone(score('', '')['cer'])
        self.assertIsNone(summarize([dict(status='error')])['cer'])

    def test_percentiles_include_timeout_denominator_separately(self):
        self.assertEqual(distribution([10, None, 30, 20]), dict(n=3, p50=20, p95=30, maximum=30))
        self.assertEqual(summarize([dict(status='timeout')])['failures'], 1)

    def fixture(self, folder):
        audio = Path(folder)/'human.wav'
        with wave.open(str(audio), 'wb') as wav:
            wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            wav.writeframes(bytes(32000))
        row = dict(id='one', audio='human.wav', reference='シエル', speaker='test',
                   condition='quiet', source='human', speech_end_seconds=.8)
        manifest = Path(folder)/'corpus.jsonl'
        manifest.write_text(json.dumps(row), encoding='utf-8')
        return manifest, row

    def test_corpus_hashes_validation_and_duplicate_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, row = self.fixture(folder)
            result = corpus(manifest)[0]
            self.assertEqual(result['audio_seconds'], 1)
            self.assertEqual(len(result['audio_sha256']), 64)
            for bad in [dict(row, speech_end_seconds=float('nan')), dict(row, speech_end_seconds=2), dict(row, source='unknown')]:
                manifest.write_text(json.dumps(bad), encoding='utf-8')
                with self.assertRaises(ValueError):
                    corpus(manifest)
            manifest.write_text(json.dumps(row)+'\n'+json.dumps(row), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                corpus(manifest)

    def test_replay_distinguishes_natural_final_from_eof_flush(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest, _ = self.fixture(folder)
            row = corpus(manifest)[0]
            args = SimpleNamespace(model='unused', tail_seconds=0, chunk_ms=100, unpaced=True)
            decoder = SimpleNamespace(feed=lambda pcm: (True, 'シエル'), finish=lambda: '')
            with patch('vosk_engine.Decoder', return_value=decoder):
                result = runner.stt_trial(row, args)
            self.assertEqual(len(result['natural_finals']), 10)
            self.assertIsNone(result['natural_final_ms'])  # unpaced is throughput only
            decoder.finish = lambda: 'シエル'
            decoder.feed = lambda pcm: (False, 'シ')
            args.unpaced = False
            with patch('vosk_engine.Decoder', return_value=decoder), patch.object(runner.time, 'sleep'):
                result = runner.stt_trial(row, args)
            self.assertEqual(result['cer'], 0)
            self.assertTrue(result['eof_text_present'])
            self.assertIsNone(result['natural_final_ms'])

    def test_live_connection_failure_removes_test_room_and_closes_client(self):
        # Use the installed SDK interface, but never connect to a service.
        from livekit import api, rtc
        room = MagicMock()
        room.connect = AsyncMock(side_effect=RuntimeError('offline'))
        room.disconnect = AsyncMock()
        client = MagicMock()
        client.room.create_room = AsyncMock()
        client.room.delete_room = AsyncMock()
        client.aclose = AsyncMock()
        token = MagicMock()
        token.with_identity.return_value = token
        token.with_name.return_value = token
        token.with_grants.return_value = token
        token.to_jwt.return_value = 'test-token'
        args = SimpleNamespace(agent='ciel-voice-bench')
        with patch.object(api, 'LiveKitAPI', return_value=client), patch.object(api, 'AccessToken', return_value=token), \
             patch.object(rtc, 'Room', return_value=room), patch.dict(runner.os.environ, {'LIVEKIT_URL': 'ws://invalid'}):
            with self.assertRaisesRegex(RuntimeError, 'offline'):
                asyncio.run(runner.live_trial({}, args))
        room.disconnect.assert_awaited_once()
        client.room.delete_room.assert_awaited_once()
        client.aclose.assert_awaited_once()
        created = client.room.create_room.call_args.args[0]
        deleted = client.room.delete_room.call_args.args[0]
        self.assertEqual(created.name, deleted.room)
        self.assertEqual(created.agents[0].agent_name, 'ciel-voice-bench')

    def test_live_requires_greeting_before_publishing_input_when_requested(self):
        from livekit import api, rtc
        handlers = {}
        room = MagicMock()
        room.on.side_effect = lambda name: lambda callback: handlers.setdefault(name, callback)
        async def connect(*args):
            handlers['track_subscribed'](SimpleNamespace(kind=rtc.TrackKind.KIND_AUDIO),
                                         SimpleNamespace(name='agent'), None)
        room.connect = AsyncMock(side_effect=connect)
        room.disconnect = AsyncMock()
        client = MagicMock()
        client.room.create_room = AsyncMock()
        client.room.delete_room = AsyncMock()
        client.aclose = AsyncMock()
        token = MagicMock()
        token.with_identity.return_value = token
        token.with_name.return_value = token
        token.with_grants.return_value = token
        async def silence(*args, **kwargs):
            # Actual SDK data uses int16 memoryview, not a byte-oriented view.
            yield SimpleNamespace(frame=rtc.AudioFrame(bytes(640), 16000, 1, 320))
        args = SimpleNamespace(agent='test', timeout=.01, connect_timeout=.01, require_ready=False, settle_seconds=0,
                               greeting_timeout=.001, rms_threshold=.01)
        with patch.object(api, 'LiveKitAPI', return_value=client), patch.object(api, 'AccessToken', return_value=token), \
             patch.object(rtc, 'Room', return_value=room), patch.object(rtc, 'AudioStream', side_effect=silence), \
             patch.object(rtc, 'AudioSource') as source, patch.dict(runner.os.environ, {'LIVEKIT_URL': 'ws://invalid'}):
            with self.assertRaisesRegex(TimeoutError, 'greeting'):
                asyncio.run(runner.live_trial({}, args))
            source.assert_not_called()
        client.room.delete_room.assert_awaited_once()
        client.aclose.assert_awaited_once()


    def test_live_refuses_unsupported_ready_version_before_input(self):
        from livekit import api, rtc
        handlers = {}
        room = MagicMock()
        room.on.side_effect = lambda name: lambda callback: handlers.setdefault(name, callback)
        async def connect(*args):
            handlers['data_received'](SimpleNamespace(topic='ciel.event',
                data=json.dumps({'v':2,'type':'voice.ready','ready':True}).encode()))
        room.connect = AsyncMock(side_effect=connect)
        room.disconnect = AsyncMock()
        room.local_participant.publish_data = AsyncMock()
        client = MagicMock()
        client.room.create_room = AsyncMock()
        client.room.delete_room = AsyncMock()
        client.aclose = AsyncMock()
        token = MagicMock()
        token.with_identity.return_value = token
        token.with_name.return_value = token
        token.with_grants.return_value = token
        args = SimpleNamespace(agent='test', require_ready=True, connect_timeout=.1)
        with patch.object(api,'LiveKitAPI',return_value=client), patch.object(api,'AccessToken',return_value=token), \
             patch.object(rtc,'Room',return_value=room), patch.object(rtc,'AudioSource') as source, \
             patch.dict(runner.os.environ,{'LIVEKIT_URL':'ws://invalid'}):
            with self.assertRaisesRegex(ValueError,'readiness'):
                asyncio.run(runner.live_trial({},args))
            source.assert_not_called()
        client.room.delete_room.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
