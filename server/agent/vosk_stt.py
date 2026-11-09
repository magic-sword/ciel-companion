"""LiveKit streaming STT using a CPU decoder. No remote API or cloud fallback."""
import asyncio
import time

from livekit.agents import APIConnectOptions, stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
import debug_log
from vosk_engine import Decoder

class VoskSTT(stt.STT):
    def __init__(self, model_path):
        super().__init__(capabilities=stt.STTCapabilities(streaming=True, interim_results=True, offline_recognize=False))
        self.model_path = model_path

    @property
    def model(self):
        return 'vosk:' + self.model_path.rstrip('/').rsplit('/', 1)[-1]

    @property
    def provider(self):
        return 'vosk-cpu'

    async def _recognize_impl(self, buffer, *, language=None, conn_options=None):
        raise NotImplementedError('Use streaming recognition')

    def stream(self, *, language=None, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS):
        return _Stream(stt=self, conn_options=conn_options, sample_rate=16000)

class _Stream(stt.RecognizeStream):
    async def _run(self):
        started = time.perf_counter()
        decoder = await asyncio.to_thread(Decoder, self._stt.model_path)
        debug_log.record('local_stt_ready', model=self._stt.model, load_ms=round((time.perf_counter()-started)*1000, 2))
        last = ''
        speaking = False
        seconds = 0.0
        async for frame in self._input_ch:
            began = time.perf_counter()
            if isinstance(frame, self._FlushSentinel):
                final, result = True, await asyncio.to_thread(decoder.finish)
            else:
                if frame.num_channels != 1:
                    raise ValueError('Vosk requires mono audio')
                seconds += frame.samples_per_channel / frame.sample_rate
                final, result = await asyncio.to_thread(decoder.feed, frame.data.tobytes())
            if result and not speaking:
                speaking = True
                self._event_ch.send_nowait(stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH))
            if result and (final or result != last):
                self._event_ch.send_nowait(stt.SpeechEvent(
                    type=stt.SpeechEventType.FINAL_TRANSCRIPT if final else stt.SpeechEventType.INTERIM_TRANSCRIPT,
                    alternatives=[stt.SpeechData(language='ja', text=result)]))
                # Timing only; do not duplicate conversation text in operational logs.
                debug_log.record('local_stt_result', final=final, audio_seconds=round(seconds, 3),
                                 compute_ms=round((time.perf_counter()-began)*1000, 2))
            last = '' if final else result
            if final and speaking:
                self._event_ch.send_nowait(stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH))
                speaking = False
        if seconds:
            self._event_ch.send_nowait(stt.SpeechEvent(type=stt.SpeechEventType.RECOGNITION_USAGE,
                recognition_usage=stt.RecognitionUsage(audio_duration=seconds)))
