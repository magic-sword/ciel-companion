"""Versioned, dependency-free scoring and corpus validation for voice benchmarks."""
import hashlib
import json
import math
from pathlib import Path
import unicodedata
import wave

NORMALIZATION = 'ja-nfkc-casefold-no-space-punctuation-v1'


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold()
                   if not c.isspace() and not unicodedata.category(c).startswith('P'))


def distance(reference, hypothesis):
    row = list(range(len(hypothesis) + 1))
    for i, a in enumerate(reference, 1):
        nxt = [i]
        for j, b in enumerate(hypothesis, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j-1] + (a != b)))
        row = nxt
    return row[-1]


def score(reference, hypothesis):
    ref, hyp = normalize(reference), normalize(hypothesis)
    errors = distance(ref, hyp)
    return dict(character_errors=errors, reference_characters=len(ref),
                cer=errors / len(ref) if ref else None,
                exact_match=ref == hyp, silence_false_positive=not ref and bool(hyp))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def corpus(path):
    """One turn per WAV; human-annotated speech end excludes trailing silence."""
    path = Path(path).resolve()
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    seen = set()
    if not rows:
        raise ValueError('Empty corpus')
    for row in rows:
        if not isinstance(row.get('id'), str) or not row['id'] or row['id'] in seen:
            raise ValueError('Missing or duplicate corpus id')
        seen.add(row['id'])
        if not isinstance(row.get('reference'), str):
            raise ValueError('reference must be a string (empty for silence)')
        for key in ('speaker', 'condition', 'source'):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError(f'Missing {key}')
        if row['source'] not in ('human', 'synthetic'):
            raise ValueError('source must be human or synthetic')
        audio = (path.parent / row['audio']).resolve()
        with wave.open(str(audio), 'rb') as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) != (16000, 1, 2, 'NONE'):
                raise ValueError(f'{audio}: expected 16kHz mono PCM16 WAV')
            duration = wav.getnframes() / 16000
        end = row.get('speech_end_seconds')
        if duration <= 0 or not isinstance(end, (int, float)) or not math.isfinite(end) or not 0 <= end <= duration:
            raise ValueError(f'{audio}: invalid speech_end_seconds')
        row.update(audio_path=str(audio), audio_sha256=sha256(audio), audio_seconds=duration)
    return rows


def distribution(values):
    values = sorted(v for v in values if v is not None)
    def percentile(p):
        # Nearest rank; small corpora have correspondingly coarse tails.
        return values[max(0, math.ceil(p * len(values))-1)] if values else None
    return dict(n=len(values), p50=percentile(.5), p95=percentile(.95),
                maximum=values[-1] if values else None)


def summarize(rows):
    total = sum(r.get('reference_characters', 0) for r in rows)
    scored = [r for r in rows if 'exact_match' in r]
    silence = [r for r in scored if not r['reference_characters']]
    return dict(trials=len(rows), failures=sum(r.get('status') != 'ok' for r in rows),
                scored_trials=len(scored), reference_characters=total,
                cer=sum(r.get('character_errors', 0) for r in rows if r.get('reference_characters')) / total if total else None,
                exact_match_rate=sum(r['exact_match'] for r in scored) / len(scored) if scored else None,
                silence_trials=len(silence),
                silence_false_positive_rate=sum(r['silence_false_positive'] for r in silence) / len(silence) if silence else None,
                eof_text_trials=sum(bool(r.get('eof_text_present')) for r in rows),
                pre_end_reply_audio_trials=sum(bool(r.get('pre_end_reply_audio')) for r in rows),
                silence_response_trials=sum(not r.get('reference') and r.get('first_any_audio_ms') is not None for r in rows),
                metrics={key: distribution([r.get(key) for r in rows]) for key in
                         ('compute_rtf', 'first_partial_ms', 'natural_final_ms', 'first_any_audio_ms', 'first_reply_audio_ms')})


def grouped(rows):
    return {key: {value: summarize([r for r in rows if r[key] == value])
                  for value in sorted({r[key] for r in rows})}
            for key in ('condition', 'source', 'speaker')}
