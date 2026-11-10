#!/usr/bin/env python3
"""CPU Whisper corpus accuracy and decode time; not live endpoint latency."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'server/agent'))
from voice_benchmark import score, sha256
import whisper_engine


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prompt', type=Path)
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--smoke', action='store_true')
    a = p.parse_args()
    if a.output.exists() or a.rounds < 1:
        p.error('New output and positive rounds required')
    prompt = a.prompt.read_text(encoding='utf8').strip() if a.prompt else None
    began = time.monotonic()
    whisper_engine.load_model(str(a.model))
    report = dict(schema='ciel-whisper-probe-v1', load_ms=(time.monotonic()-began)*1000,
        source_sha256={str(p.name):sha256(p) for p in [Path(__file__), Path(whisper_engine.__file__)]},
        corpus_sha256=sha256(a.corpus),
        model_sha256={x.name:sha256(x) for x in a.model.iterdir() if x.is_file()},
        versions={n:importlib.metadata.version(n) for n in ['faster-whisper','ctranslate2','onnxruntime']},
        prompt_sha256=hashlib.sha256((prompt or '').encode()).hexdigest(),
        options=dict(device='cpu', compute_type='int8', cpu_threads=4, beam_size=1,
                     language='ja', vad_filter=True, condition_on_previous_text=False),
        limits='Frozen synthetic corpus; inference after whole recording, not endpoint/live latency', trials=[])
    rows = [json.loads(line) for line in a.corpus.read_text(encoding='utf8').splitlines()]
    if a.smoke: rows = rows[:1]
    a.output.parent.mkdir(parents=True, exist_ok=True)
    for repeat in range(a.rounds):
        for row in rows:
            path = a.corpus.parent/row['audio']
            with wave.open(str(path)) as wav:
                duration = wav.getnframes()/wav.getframerate()
            start = time.monotonic()
            hypothesis = whisper_engine.recognize(str(a.model), str(path), prompt)
            elapsed = time.monotonic()-start
            result = dict(row, repeat=repeat, hypothesis=hypothesis, audio_sha256=sha256(path),
                          decode_ms=elapsed*1000, compute_rtf=elapsed/duration,
                          **score(row['reference'], hypothesis))
            report['trials'].append(result)
            a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
            print(json.dumps({k:result[k] for k in ['id','repeat','hypothesis','cer','decode_ms']},ensure_ascii=False),flush=True)
    trials = report['trials']
    report['cer'] = sum(t['character_errors'] for t in trials)/sum(t['reference_characters'] for t in trials)
    report['silence_false_positives'] = sum(t['silence_false_positive'] for t in trials)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(cer=report['cer'], trials=len(trials), silence_false_positives=report['silence_false_positives'])))


if __name__ == '__main__':
    main()
