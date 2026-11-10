#!/usr/bin/env python3
"""Replay an annotated WAV corpus through Vosk or a named LiveKit test agent.

See docs/testing/voice-benchmark-ja.md. No dotenv loading or cloud fallback.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server/agent'))
from voice_benchmark import NORMALIZATION, corpus, grouped, score, sha256, summarize


def stt_trial(row, args):
    from vosk_engine import Decoder
    decoder = Decoder(args.model)
    with wave.open(row['audio_path'], 'rb') as wav:
        pcm = wav.readframes(wav.getnframes())
    # Append silence to observe natural endpoints, then flush separately.
    pcm += bytes(round(args.tail_seconds * 16000) * 2)
    step = args.chunk_ms * 16 * 2
    started = time.perf_counter()
    compute = 0
    partial = None
    finals = []
    events = []
    for offset in range(0, len(pcm), step):
        chunk = pcm[offset:offset+step]
        available = (offset + len(chunk)) / 32000
        if not args.unpaced:
            time.sleep(max(0, started + available - time.perf_counter()))
        began = time.perf_counter()
        final, text = decoder.feed(chunk)
        compute += time.perf_counter() - began
        elapsed = time.perf_counter() - started
        if text and not final and partial is None:
            partial = elapsed * 1000
        if final and text:
            finals.append(text)
            events.append(dict(seconds=elapsed, audio_offset_seconds=available, text=text))
    began = time.perf_counter()
    tail = decoder.finish()
    compute += time.perf_counter() - began
    hypothesis = ''.join(finals) + tail
    # Require a natural final covering speech end. A mid-utterance segment is not the final turn.
    complete = events[-1] if events and not tail and events[-1]['audio_offset_seconds'] >= row['speech_end_seconds'] else None
    return dict(status='ok', hypothesis=hypothesis, **score(row['reference'], hypothesis),
                compute_rtf=compute / (len(pcm) / 32000), compute_seconds=compute,
                wall_seconds=time.perf_counter()-started, first_partial_ms=partial if not args.unpaced else None,
                natural_final_ms=(complete['seconds']-row['speech_end_seconds'])*1000
                if complete and not args.unpaced else None,
                eof_text_present=bool(tail), natural_finals=events)


async def live_trial(row, args):
    """Fresh room per turn. Audio arrival is observed, not physical speaker playback."""
    import math
    import struct
    from livekit import api, rtc
    name = 'voice-bench-' + uuid.uuid4().hex[:12]
    identity = 'voice-bench-user'
    lk = api.LiveKitAPI()
    room = rtc.Room()
    tasks = []
    observations = []
    transcripts = {}
    origin = None
    closing = False

    async def listen(track, track_name):
        loud = False
        async for event in rtc.AudioStream(track, sample_rate=16000, num_channels=1):
            if origin is None:
                continue
            samples = struct.unpack('<' + 'h' * (len(event.frame.data)//2), event.frame.data)
            rms = math.sqrt(sum(x*x for x in samples) / max(1, len(samples))) / 32768
            active = rms >= args.rms_threshold
            if active and not loud:
                observations.append((time.perf_counter(), track_name))
            loud = active

    @room.on('track_subscribed')
    def subscribed(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO and not closing:
            tasks.append(asyncio.create_task(listen(track, publication.name)))

    @room.on('transcription_received')
    def transcribed(segments, participant, publication):
        if origin is not None and participant and participant.identity == identity:
            for segment in segments:
                if segment.final:
                    transcripts[segment.id] = segment.text

    try:
        await lk.room.create_room(api.CreateRoomRequest(name=name,
            agents=[api.RoomAgentDispatch(agent_name=args.agent)]))
        token = (api.AccessToken().with_identity(identity).with_name('voice benchmark')
                 .with_grants(api.VideoGrants(room_join=True, room=name)).to_jwt())
        await room.connect(os.environ['LIVEKIT_URL'], token)
        deadline = time.perf_counter() + args.timeout
        while not tasks:
            if time.perf_counter() > deadline:
                raise TimeoutError('No agent audio track')
            await asyncio.sleep(.05)
        # Greeting is outside the scored window. Require a configured settling interval.
        await asyncio.sleep(args.settle_seconds)
        source = rtc.AudioSource(16000, 1, queue_size_ms=100)
        try:
            track = rtc.LocalAudioTrack.create_audio_track('voice-bench-mic', source)
            await room.local_participant.publish_track(track,
                rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
            with wave.open(row['audio_path'], 'rb') as wav:
                pcm = wav.readframes(wav.getnframes())
            pcm += bytes(round(args.tail_seconds * 16000) * 2)
            origin = time.perf_counter()
            for offset in range(0, len(pcm), 640):
                chunk = pcm[offset:offset+640].ljust(640, b'\0')
                await source.capture_frame(rtc.AudioFrame(chunk, 16000, 1, 320))
                await asyncio.sleep(max(0, origin + (offset+640)/32000 - time.perf_counter()))
            await source.wait_for_playout()
            await asyncio.sleep(args.timeout)
            for task in tasks:
                if task.done() and not task.cancelled() and task.exception() is not None:
                    raise RuntimeError('Audio receiver failed') from task.exception()
        finally:
            await source.aclose()
        end = origin + row['speech_end_seconds']
        any_audio = next((t for t, _ in observations if t >= end), None)
        reply = next((t for t, name in observations if t >= end and name != 'ciel-aizuchi'), None)
        hypothesis = ''.join(transcripts.values()) if transcripts else None
        expected_reply = bool(row['reference'])
        return dict(status='timeout' if expected_reply and reply is None else 'ok',
                    hypothesis=hypothesis,
                    **(score(row['reference'], hypothesis) if hypothesis is not None else {}),
                    transcript_available=hypothesis is not None,
                    first_any_audio_ms=(any_audio-end)*1000 if any_audio else None,
                    first_reply_audio_ms=(reply-end)*1000 if reply else None,
                    pre_end_reply_audio=any(t < end and name != 'ciel-aizuchi' for t, name in observations),
                    room=name, audio_observations=len(observations))
    finally:
        closing = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await room.disconnect()
        finally:
            try:
                await lk.room.delete_room(api.DeleteRoomRequest(room=name))
            finally:
                await lk.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['stt', 'live'])
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--conditions', type=Path, required=True, help='JSON: model/config/load/device identifiers')
    parser.add_argument('--output', type=Path, required=True, help='New directory; never overwritten')
    parser.add_argument('--model', help='Vosk model directory (stt)')
    parser.add_argument('--agent', help='Explicit named test worker (live)')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--chunk-ms', type=int, default=20)
    parser.add_argument('--tail-seconds', type=float, default=2)
    parser.add_argument('--unpaced', action='store_true', help='Throughput only; endpoint latency is null')
    parser.add_argument('--timeout', type=float, default=30, help='Post-input observation window / track wait')
    parser.add_argument('--settle-seconds', type=float, default=10)
    parser.add_argument('--rms-threshold', type=float, default=.01)
    args = parser.parse_args()
    if (not all(math.isfinite(v) for v in (args.tail_seconds, args.timeout, args.settle_seconds, args.rms_threshold))
            or args.rounds < 1 or args.chunk_ms < 1 or args.tail_seconds < 0 or args.timeout <= 0
            or args.settle_seconds < 0 or not 0 < args.rms_threshold < 1):
        parser.error('Invalid trial count or timing/threshold setting')
    if args.mode == 'stt' and (not args.model or not Path(args.model).is_dir()):
        parser.error('stt requires an existing --model directory')
    if args.mode == 'live' and (not args.agent or not args.agent.strip() or args.unpaced):
        parser.error('live requires an explicit named --agent and paced audio')
    rows = corpus(args.corpus)
    conditions = json.loads(args.conditions.read_text(encoding='utf-8'))
    required = ('stt_model', 'llm_model', 'tts_model', 'hardware', 'shared_load', 'runtime_config')
    if not isinstance(conditions, dict) or any(not conditions.get(k) for k in required):
        parser.error('conditions requires: ' + ', '.join(required))
    args.output.mkdir(parents=True, exist_ok=False)
    def git(*command):
        return subprocess.check_output(['git', *command], cwd=ROOT, text=True).strip()
    report = dict(schema='ciel-voice-benchmark-v1', normalization=NORMALIZATION,
                  mode=args.mode, created_utc=datetime.now(timezone.utc).isoformat(),
                  git_commit=git('rev-parse', 'HEAD'), git_dirty=bool(git('status', '--porcelain')),
                  runner_sha256=sha256(__file__), scorer_sha256=sha256(ROOT/'server/agent/voice_benchmark.py'),
                  corpus_sha256=sha256(args.corpus), conditions=conditions,
                  platform=platform.platform(), python=sys.version, options={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                  trials=[])
    if args.mode == 'stt':
        from vosk_engine import load_model
        report['model_files'] = {str(p.relative_to(args.model)): sha256(p)
                                 for p in sorted(Path(args.model).rglob('*')) if p.is_file()}
        began = time.perf_counter()
        load_model(args.model)
        report.update(model_load_seconds=time.perf_counter()-began, vosk_version=importlib.metadata.version('vosk'),
                      decoder_sha256=sha256(ROOT/'server/agent/vosk_engine.py'))
    def save():
        report['summary'] = summarize(report['trials'])
        report['groups'] = grouped(report['trials'])
        (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for repeat in range(args.rounds):
        for row in rows:
            trial = {k: v for k, v in row.items() if k != 'audio_path'}
            trial['repeat'] = repeat
            try:
                trial.update(stt_trial(row, args) if args.mode == 'stt' else asyncio.run(live_trial(row, args)))
            except Exception as exc:
                trial.update(status='error', error=type(exc).__name__ + ': ' + str(exc))
            report['trials'].append(trial)
            save()
            print(f"{row['id']} repeat={repeat}: {trial['status']}", flush=True)
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
    return int(report['summary']['failures'] > 0)


if __name__ == '__main__':
    sys.exit(main())
