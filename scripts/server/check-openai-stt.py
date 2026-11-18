#!/usr/bin/env python3
"""One synthetic Japanese streaming smoke in the agent environment (paid STT).

Run inside the candidate agent with /app on PYTHONPATH. No microphone, room,
conversation, or game input is used. This does not measure human ASR accuracy.
"""
import asyncio
import json
import time

import aiohttp
from livekit import rtc
from livekit.agents import APIConnectOptions, inference, stt
from livekit.plugins import openai
from irodori_tts import request_audio


async def smoke():
    async with aiohttp.ClientSession() as http:
        pcm, rate = await request_audio(http, {'text': 'シエル、今日はいい天気ですね。'})
    vad = inference.VAD()
    engine = openai.STT(model='gpt-live-transcribe', language='ja', vad=vad,
                        keywords=['シエル', '議事録'])
    stream = engine.stream(conn_options=APIConnectOptions(max_retry=0, timeout=15))
    events = []
    started = time.monotonic()
    done = asyncio.Event()

    async def receive():
        async for event in stream:
            if event.type in (stt.SpeechEventType.INTERIM_TRANSCRIPT, stt.SpeechEventType.FINAL_TRANSCRIPT):
                events.append({'type': event.type.name, 'seconds': round(time.monotonic()-started, 3),
                               'text': event.alternatives[0].text})
                if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
                    done.set()

    reader = asyncio.create_task(receive())
    try:
        audio = pcm + bytes(rate * 2 * 2)
        step = rate // 50 * 2
        for offset in range(0, len(audio), step):
            chunk = audio[offset:offset+step]
            stream.push_frame(rtc.AudioFrame(chunk, rate, 1, len(chunk)//2))
            await asyncio.sleep(.02)
        await asyncio.wait_for(done.wait(), 20)
        finals = [e for e in events if e['type'] == 'FINAL_TRANSCRIPT']
        assert any(e['text'].strip() for e in finals), 'No nonempty final transcript'
        assert any(e['type'] == 'INTERIM_TRANSCRIPT' for e in events), 'No streaming partial transcript'
        print(json.dumps({'model': 'gpt-live-transcribe', 'synthetic': True,
                          'audio_seconds': len(pcm)/2/rate, 'events': events}, ensure_ascii=False))
    finally:
        await stream.aclose()
        await reader
        await engine.aclose()


async def main():
    from livekit.agents.utils import http_context
    async with http_context.open():
        await smoke()


if __name__ == '__main__':
    asyncio.run(main())
