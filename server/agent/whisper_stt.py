"""CPU Whisper recognition; LiveKit StreamAdapter supplies VAD-delimited speech."""
import asyncio
import time

import numpy as np
from livekit import rtc
from livekit.agents import stt
import debug_log
import whisper_engine


class WhisperSTT(stt.STT):
    def __init__(self, model_path, prompt=''):
        super().__init__(capabilities=stt.STTCapabilities(streaming=False, interim_results=False))
        self.model_path, self.prompt = model_path, prompt

    @property
    def model(self):
        return 'faster-whisper:' + self.model_path.rstrip('/').rsplit('/', 1)[-1]

    @property
    def provider(self):
        return 'faster-whisper-cpu'

    async def _recognize_impl(self, buffer, *, language=None, conn_options=None):
        frame = rtc.combine_audio_frames(buffer)
        if frame.num_channels != 1:
            raise ValueError('Whisper requires mono audio')
        if frame.sample_rate != 16000:
            resampler = rtc.AudioResampler(frame.sample_rate, 16000)
            frame = rtc.combine_audio_frames([*resampler.push(frame), *resampler.flush()])
        audio = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768
        started = time.perf_counter()
        # StreamAdapter has already selected speech with the session VAD. A second
        # VAD can discard short utterances after the first one trimmed their context.
        result = await asyncio.to_thread(whisper_engine.recognize, self.model_path, audio, self.prompt,
                                         vad_filter=False)
        debug_log.record('local_stt_result', final=True, model=self.model,
                         audio_seconds=round(len(audio)/16000, 3),
                         compute_ms=round((time.perf_counter()-started)*1000, 2))
        return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                              alternatives=[stt.SpeechData(language='ja', text=result)])
