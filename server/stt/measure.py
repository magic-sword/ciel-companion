"""Synthetic Japanese CPU ASR benchmark: unpaced throughput + real-time chunk input."""
import audioop
import hashlib
import json
from pathlib import Path
import platform
import resource
import time
import unicodedata
import urllib.request
import wave
from vosk_engine import Decoder, load_model

PHRASES = ['こんにちは、シエル。今日は何をして遊びましょうか。', '近くの木を調べて、原木を三個集めてください。', '石のツルハシを作ってください。材料がなければ、作業を止めてください。']
SR = 16000
OUT = Path('/results')
MODEL = '/models/vosk-model-small-ja-0.22'

def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFKC', s) if not c.isspace() and not unicodedata.category(c).startswith('P'))

def errors(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1):
            nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]

def fixture(i, phrase):
    file=OUT/f'phrase-{i}.wav'
    if file.exists():
        with wave.open(str(file),'rb') as wav:
            assert (wav.getframerate(),wav.getnchannels(),wav.getsampwidth())==(SR,1,2)
            return wav.readframes(wav.getnframes())
    request=urllib.request.Request('http://127.0.0.1:8766/synthesize',
        data=json.dumps({'text':phrase,'session_id':'vosk-cpu-evaluation','request_id':f'vosk-{time.time_ns()}'}).encode(),
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=90) as response:
        data=response.read()
        rate=int(response.headers.get('X-Sample-Rate','48000'))
    if rate!=SR:
        data,_=audioop.ratecv(data,2,1,rate,SR,None)
    with wave.open(str(file),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(SR);wav.writeframes(data)
    return data

def recognize(audio, paced):
    decoder=Decoder(MODEL)
    # Trailing silence tests the recognizer's normal endpoint, not only EOF flush.
    data=audio+b'\0'*(SR*2*2)
    chunk=SR//10*2
    began=time.perf_counter();cpu=time.process_time();compute=0;last='';first=None;first_offset=None
    updates=0;finals=[];natural=[];max_block=0
    for offset in range(0,len(data),chunk):
        part=data[offset:offset+chunk]
        available=(offset+len(part))/(SR*2)
        if paced:
            time.sleep(max(0,began+available-time.perf_counter()))
        start=time.perf_counter();final,text=decoder.feed(part)
        duration=time.perf_counter()-start;compute+=duration;max_block=max(max_block,duration)
        now=time.perf_counter()-began
        if text and not final and text!=last:
            updates+=1
            if first is None:
                first=now;first_offset=available
        if final and text:
            finals.append(text);natural.append(now)
        last='' if final else text
    start=time.perf_counter();end=decoder.finish();compute+=time.perf_counter()-start
    if end: finals.append(end)
    elapsed=time.perf_counter()-began
    return dict(text=''.join(finals),mode='paced' if paced else 'unpaced',
        input_seconds=len(data)/(SR*2),speech_file_seconds=len(audio)/(SR*2),wall_seconds=elapsed,
        compute_seconds=compute,cpu_seconds=time.process_time()-cpu,compute_rtf=compute/(len(data)/(SR*2)),
        first_partial_ms=first*1000 if first is not None else None,first_partial_audio_offset_seconds=first_offset,
        partial_updates=updates,natural_final_count=len(natural),eof_text_present=bool(end),
        last_natural_final_after_speech_file_ms=(natural[-1]-len(audio)/(SR*2))*1000 if natural else None,
        max_chunk_compute_ms=max_block*1000)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    fixtures=[fixture(i,p) for i,p in enumerate(PHRASES)]
    start=time.perf_counter();load_model(MODEL);cold=time.perf_counter()-start
    rows=[]
    for i,(phrase,audio) in enumerate(zip(PHRASES,fixtures)):
        for paced in (False,True):
            row=recognize(audio,paced)
            expected,actual=normalize(phrase),normalize(row['text'])
            row.update(phrase_id=i,expected=phrase,audio_sha256=hashlib.sha256(audio).hexdigest(),
                       character_errors=errors(expected,actual),reference_characters=len(expected))
            row['cer']=row['character_errors']/max(1,len(expected))
            rows.append(row)
    report=dict(version=1,engine='vosk',engine_version='0.3.45',model=Path(MODEL).name,
        input='Irodori synthetic Japanese; 16kHz mono PCM16; 100ms chunks; 2s trailing silence',
        gpu_used=False,platform=platform.platform(),cpu_count=__import__('os').cpu_count(),
        model_cold_load_seconds=cold,peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        trials=rows,limits='Synthetic samples only, not a human microphone or end-to-end Ciel latency test')
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
