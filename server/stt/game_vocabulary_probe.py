"""Paired synthetic-audio CPU Whisper vocabulary probe, not human/live accuracy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import wave
import numpy as np
from livekit import rtc
sys.path.insert(0,'/app')
import whisper_engine
from persona import load_persona
from voice_benchmark import score
from speech_vocabulary import terms

CASES=[
    ('stone-shovel','石のシャベルを一つ準備して。','石のシャベル'),
    ('stone-pickaxe','石のツルハシを一つ作って。','石のツルハシ'),
    ('iron-shovel','鉄のシャベルを作ってくれるかな。','鉄のシャベル'),
    ('birch-log','シラカバの原木を三つ集めて。','シラカバの原木'),
    ('level','この辺を整地して、穴を埋め戻して。','整地'),
    ('chat-weather','今日はいい天気だから散歩に行きたいね。',None),
    ('chat-reading','昨日読んだ本の話をしよう。',None),
    ('negation','今は何も作らないで、ここで待っていて。',None),
]

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--vocabulary',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--audio-dir',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    new=terms(json.loads(a.vocabulary.read_text()));old=terms(json.loads(a.baseline.read_text()))
    if not new or not old:raise ValueError('Invalid vocabulary')
    base=load_persona().stt_vocabulary
    prompts={'none':base,'old21':base+'\n'+'、'.join(old),'expanded':base+'\n'+'、'.join(new)}
    model=os.getenv('CIEL_WHISPER_MODEL_PATH','/models-whisper/small')
    report=dict(schema='ciel-game-vocabulary-probe-v1',source='synthetic Irodori, one voice, one recording per sentence',
                model=model,model_hashes={p.name:digest(p) for p in Path(model).iterdir() if p.is_file()},
                options=dict(device='cpu',compute_type='int8',cpu_threads=4,beam_size=1,vad_filter=False,temperature=0),
                prompts=prompts,vocabulary_sha256=digest(a.vocabulary),baseline_sha256=digest(a.baseline),
                runner_sha256=digest(__file__),engine_sha256=digest(whisper_engine.__file__),trials=[])
    loaded=whisper_engine.load_model(model)
    report['prompt_tokens']={k:len(loaded.hf_tokenizer.encode(v).ids) for k,v in prompts.items()}
    if max(report['prompt_tokens'].values())>223:raise ValueError('Prompt would be truncated')
    for index,(id,text,target) in enumerate(CASES):
        wav=a.output/(id+'.wav')
        if a.audio_dir:
            wav.write_bytes((a.audio_dir/(id+'.wav')).read_bytes())
            with wave.open(str(wav),'rb') as source:
                if (source.getframerate(),source.getnchannels(),source.getsampwidth())!=(16000,1,2):raise ValueError('Invalid reused audio')
                raw=source.readframes(source.getnframes())
        else:
            raw=synthesize(text,id)
            with wave.open(str(wav),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(raw)
        audio=np.frombuffer(raw,dtype=np.int16).astype(np.float32)/32768
        names=list(prompts);names=names[index%3:]+names[:index%3]
        for name in names:
            started=time.monotonic();hyp=whisper_engine.recognize(model,audio,prompts[name],vad_filter=False)
            row=dict(id=id,condition=name,reference=text,target=target,hypothesis=hyp,
                     target_present=target in hyp if target else None,audio_sha256=digest(wav),
                     decode_ms=(time.monotonic()-started)*1000,**score(text,hyp))
            report['trials'].append(row)
            (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps(row,ensure_ascii=False),flush=True)
    report['summary']={}
    for name in prompts:
        rows=[r for r in report['trials'] if r['condition']==name]
        report['summary'][name]=dict(cer=sum(r['character_errors'] for r in rows)/sum(r['reference_characters'] for r in rows),
            target_hits=sum(r['target_present'] is True for r in rows),target_count=5,
            control_cer=sum(r['character_errors'] for r in rows if r['target'] is None)/sum(r['reference_characters'] for r in rows if r['target'] is None))
    (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report['summary']))


def synthesize(text,id):
        request=urllib.request.Request('http://127.0.0.1:8766/synthesize',
            data=json.dumps({'text':text,'caption':'落ち着いた自然な声。','session_id':'vocabulary-probe','request_id':id}).encode(),
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=60) as response:
            pcm=response.read();rate=int(response.headers.get('X-Sample-Rate','48000'))
        frame=rtc.AudioFrame(pcm,rate,1,len(pcm)//2)
        if rate!=16000:
            resampler=rtc.AudioResampler(rate,16000)
            frame=rtc.combine_audio_frames([*resampler.push(frame),*resampler.flush()])
        return bytes(frame.data)

if __name__=='__main__':main()
