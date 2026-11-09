"""Actual SDK + actual Vosk, using the synthetic fixture from measure.py. No LiveKit room/API."""
import asyncio
import json
from pathlib import Path
import time
import wave
from livekit import rtc
from livekit.agents import APIConnectOptions, stt
from vosk_stt import VoskSTT

async def main():
    with wave.open('/results/phrase-0.wav','rb') as wav:
        assert (wav.getframerate(),wav.getnchannels(),wav.getsampwidth())==(16000,1,2)
        audio=wav.readframes(wav.getnframes())+bytes(16000*2*2)
    engine=VoskSTT('/models/vosk-model-small-ja-0.22')
    stream=engine.stream(conn_options=APIConnectOptions(max_retry=0))
    began=time.perf_counter();events=[];ended=False;beats=[]
    async def consume():
        async for event in stream:
            events.append((event.type.value,time.perf_counter()-began,ended))
    async def heartbeat():
        while True:
            start=time.perf_counter();await asyncio.sleep(.02);beats.append(time.perf_counter()-start)
    consumer=asyncio.create_task(consume());heart=asyncio.create_task(heartbeat())
    try:
        for offset in range(0,len(audio),3200):
            chunk=audio[offset:offset+3200]
            await asyncio.sleep(max(0,began+(offset+len(chunk))/32000-time.perf_counter()))
            stream.push_frame(rtc.AudioFrame(chunk,16000,1,len(chunk)//2))
        ended=True;stream.end_input();await asyncio.wait_for(consumer,10)
        interim=[e for e in events if e[0]==stt.SpeechEventType.INTERIM_TRANSCRIPT.value]
        final=[e for e in events if e[0]==stt.SpeechEventType.FINAL_TRANSCRIPT.value]
        assert interim and not interim[0][2], 'No live interim result before EOF'
        assert final, 'No confirmed result'
        result={'provider':engine.provider,'model':engine.model,'interim_count':len(interim),'final_count':len(final),
                'first_interim_ms':interim[0][1]*1000,'max_event_loop_tick_ms':max(beats)*1000,
                'first_interim_before_eof':not interim[0][2],'openai_calls':0,
                'scope':'actual SDK and native decoder; synthetic fixture; no room, no tool execution'}
        Path('/results/livekit-integration.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result))
    finally:
        heart.cancel();await asyncio.gather(heart,return_exceptions=True);await stream.aclose()

if __name__=='__main__':asyncio.run(main())
