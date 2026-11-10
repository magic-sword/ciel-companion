"""Home-server orchestration; local models, named development worker, no redeploy."""
import argparse
import audioop
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import shutil
import struct
import subprocess
import tarfile
import time
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[2]
DEV = 'ciel-dev-agent-dev-1'
MODEL = Path.home()/'models/vosk/vosk-model-small-ja-0.22'
CAPTION = '落ち着いた低めの声の30代の男性。ふつうの速さで、親しい相手に話しかける自然な話し方。'
PHRASES = [('greeting', ['おはよう、シエル。']),
           ('number', ['今日は三十分くらい散歩したよ。']),
           ('negation', ['今日は出かけないで家にいるよ。']),
           ('pause', ['明日はね、午前中は買い物で、', '午後は映画を見るよ。'])]


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def inspect(name):
    return json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]


def get(port, path):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/{path}', timeout=10) as response:
        return json.load(response)


def snapshot():
    runtime = inspect(DEV)
    env = dict(v.split('=', 1) for v in runtime['Config']['Env'] if '=' in v)
    assert env.get('CIEL_LLM_BACKEND') == 'local' and env.get('CIEL_INPUT') == 'voice'
    assert env.get('CIEL_AGENT_NAME') == 'ciel-dev' and env.get('CIEL_MEMORY_SCOPE') == 'dev'
    assert env.get('CIEL_MODEL') == 'pipeline' and env.get('CIEL_VOICE') == 'irodori'
    assert env.get('CIEL_STT_BACKEND', '') in ('', 'vosk')
    safe_keys = ['CIEL_MODEL', 'CIEL_INPUT', 'CIEL_LLM_BACKEND', 'CIEL_STT_BACKEND', 'CIEL_VOICE',
                 'CIEL_AGENT_NAME', 'CIEL_MEMORY_SCOPE', 'CIEL_VOSK_MODEL_PATH', 'CIEL_LOCAL_LLM_URL']
    code = "import hashlib,json; from pathlib import Path; print(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/app').glob('*.py')}))"
    hashes = json.loads(subprocess.check_output(['docker', 'exec', DEV, 'python', '-c', code], text=True))
    return dict(worker=DEV, image=runtime['Image'], environment={k: env.get(k) for k in safe_keys},
                source_sha256=hashes, shared_api=get(8095, 'mode'),
                load_average=os.getloadavg(), cpu_count=os.cpu_count(),
                gpu=subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.used,utilization.gpu', '--format=csv,noheader'], text=True).strip(),
                containers={name:dict(image=c['Image'], started=c['State']['StartedAt'], restarts=c['RestartCount'])
                            for name in ['ciel-agent-1', DEV, 'ciel-local-llm-1', 'ciel-tts-1'] for c in [inspect(name)]})


def prepare():
    folder = ROOT/'results'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder.mkdir(parents=True, exist_ok=False)
    (ROOT/'latest.txt').write_text(str(folder))
    rows = []
    for identity, parts in PHRASES:
        chunks = []
        for part in parts:
            request = urllib.request.Request('http://127.0.0.1:8766/synthesize',
                data=json.dumps(dict(text=part, caption=CAPTION)).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=120) as response:
                pcm = response.read()
                rate = int(response.headers.get('X-Sample-Rate', '48000'))
            if rate != 16000:
                pcm, _ = audioop.ratecv(pcm, 2, 1, rate, 16000, None)
            chunks.append(pcm)
        pcm = bytes(19200).join(chunks)  # 0.6 seconds between clauses
        speech_end = 0
        for offset in range(0, len(pcm)-1, 640):
            frame = pcm[offset:offset+640]
            if audioop.rms(frame, 2)/32768 >= .005:
                speech_end = (offset+len(frame))/32000
        if not speech_end:
            raise ValueError('Synthesizer returned no audible speech')
        path = folder/f'{identity}.wav'
        with wave.open(str(path), 'wb') as wav:
            wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            wav.writeframes(pcm)
        rows.append(dict(id=identity, audio=path.name, reference=''.join(parts), source='synthetic', speaker='irodori-male',
                         condition='mid-turn-pause' if len(parts)>1 else 'clean', speech_end_seconds=speech_end,
                         annotation='last 20ms frame with RMS >= .005; synthesized request is reference, not human-verified'))
        print('PREPARED', identity, flush=True)
    with wave.open(str(folder/'silence.wav'), 'wb') as wav:
        wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        wav.writeframes(bytes(16000*2*3))
    rows.append(dict(id='silence', audio='silence.wav', reference='', source='synthetic', speaker='none',
                     condition='silence', speech_end_seconds=3))
    for name, selected in [('corpus.jsonl', rows), ('smoke.jsonl', rows[:1])]:
        (folder/name).write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in selected), encoding='utf-8')
    state = snapshot()
    dump(folder/'before.json', state)
    dump(folder/'conditions.json', dict(stt_model='vosk-model-small-ja-0.22; per-file hashes in STT report',
         llm_model=state['shared_api'], tts_model=dict(image=state['containers']['ciel-tts-1']['image'], caption=CAPTION),
         hardware='i7-13700 / 24 logical CPUs; client/STT container limited to 2 CPUs and 3GiB; existing worker unlimited',
         shared_load='Existing services retained; no cache reset or controlled competing load; before/after snapshots saved',
         runtime_config=state,
         corpus_limits='Synthetic speech only; energy-based end annotation; synthesis request is the reference. Not human microphone accuracy.'))
    print('RESULTS', folder, flush=True)


def run(mode, rounds, smoke, settled=False):
    folder = Path((ROOT/'latest.txt').read_text())
    label = mode+('-settled' if settled else '')+('-smoke' if smoke else '')
    output = folder/label
    if output.exists():
        raise FileExistsError(output)
    provenance = json.loads((ROOT/'source-provenance.json').read_text())
    with tarfile.open(folder/(label+'-source.tar.gz'), 'w:gz') as archive:
        archive.add(ROOT/'source-provenance.json', arcname='source-provenance.json')
        for name, expected in provenance['source_sha256'].items():
            path = ROOT/name
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f'Source snapshot hash mismatch: {name}')
            archive.add(path, arcname=name)
    worker = inspect(DEV)
    env = dict(v.split('=', 1) for v in worker['Config']['Env'] if '=' in v)
    command = ['docker', 'run', '--rm', '--name', 'ciel-voice-eval-'+str(time.time_ns()), '--network', 'host',
               '--user', f'{os.getuid()}:{os.getgid()}', '--cpus', '2', '--memory', '3g',
               '-v', str(ROOT)+':/eval', '-v', str(MODEL.parent)+':/models:ro', '--workdir', '/eval',
               '--entrypoint', 'python']
    child_env = os.environ.copy()
    # Pass credential values through process environment, not argv or stored reports.
    if mode == 'live':
        for key in ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET']:
            child_env[key] = env[key]
            command += ['-e', key]
    command += [worker['Image'], '-B', '/eval/scripts/server/benchmark-voice.py', mode,
                '--corpus', '/eval/'+str((folder/('smoke.jsonl' if smoke else 'corpus.jsonl')).relative_to(ROOT)),
                '--conditions', '/eval/'+str((folder/'conditions.json').relative_to(ROOT)),
                '--source-provenance', '/eval/source-provenance.json',
                '--output', '/eval/'+str(output.relative_to(ROOT)), '--rounds', str(rounds)]
    command += ['--model', '/models/'+MODEL.name] if mode == 'stt' else ['--agent', 'ciel-dev']
    if mode == 'live' and settled:
        command += ['--greeting-timeout', '60']
    stop = __import__('threading').Event()
    def monitor():
        with (folder/(label+'-load.jsonl')).open('w') as stream:
            while not stop.is_set():
                try:
                    row = dict(t=time.time(), api=get(8095, 'mode'), load=os.getloadavg(),
                               processing_slots=sum(bool(s.get('is_processing')) for s in get(8094, 'slots')))
                    stream.write(json.dumps(row)+'\n'); stream.flush()
                except Exception as exc:
                    stream.write(json.dumps(dict(t=time.time(), error=type(exc).__name__))+'\n')
                stop.wait(2)
    thread = __import__('threading').Thread(target=monitor, daemon=True)
    thread.start()
    try:
        result = subprocess.run(command, env=child_env, timeout=1800)
    finally:
        stop.set(); thread.join(timeout=12)
        dump(folder/(label+'-after.json'), snapshot())
        if mode == 'live' and (output/'report.json').exists():
            debug = output/'debug'
            debug.mkdir(exist_ok=True)
            report = json.loads((output/'report.json').read_text())
            logs = Path.home()/'work/ciel-companion-dev/server/agent/data/debug'
            for row in report['trials']:
                room = row.get('room')
                if room and room.startswith('voice-bench-'):
                    for path in logs.glob('*-'+room+'.jsonl'):
                        shutil.copy2(path, debug/path.name)
        if mode == 'live' and (output/'report.json').exists():
            debug = output/'debug'
            debug.mkdir(exist_ok=True)
            report = json.loads((output/'report.json').read_text())
            logs = Path.home()/'work/ciel-companion-dev/server/agent/data/debug'
            for row in report['trials']:
                room = row.get('room')
                if room and room.startswith('voice-bench-'):
                    for path in logs.glob('*-'+room+'.jsonl'):
                        shutil.copy2(path, debug/path.name)
    dump(folder/(label+'-exit.json'), dict(code=result.returncode))
    return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'stt', 'live', 'status'])
    parser.add_argument('--rounds', type=int, default=1)
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--settled', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'status':
        print(json.dumps(snapshot(), indent=2))
    else:
        raise SystemExit(run(args.action, args.rounds, args.smoke, args.settled))
