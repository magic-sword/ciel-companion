#!/usr/bin/env python3
"""Stage, run and retrieve voice measurements on the configured home server."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('benchmark_home', Path(__file__).with_name('benchmark-home.py'))
home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)
sys.path.insert(0, str(ROOT/'server/agent'))
from voice_benchmark import sha256

FILES = ['scripts/server/benchmark-voice.py', 'server/agent/voice_benchmark.py',
         'server/agent/vosk_engine.py', 'server/stt/voice_measure_home.py',
         'server/benchmark/voice/conversation-corpus.json', 'scripts/server/benchmark-prefix-cache.py']
FILES += ['scripts/server/benchmark-whisper.py', 'server/agent/config/prompts/stt_vocabulary.md']
FILES += ['scripts/server/benchmark-voice-text.py', 'server/benchmark/voice/text-cases.json']
FILES += ['server/agent/whisper_engine.py', 'server/agent/whisper_stt.py']


def stage():
    import io
    sources = subprocess.check_output(['git', 'ls-files', '-z', 'server/agent'], cwd=ROOT).decode().split('\0')
    files = sorted(set(FILES + [p for p in sources if p and '/tests/' not in p
                                and not Path(p).name.startswith('.env')]
                       + ['server/agent/voice_preparation.py', 'server/agent/config/prompts/voice_warmup.md',
                          'server/agent/config/prompts/voice_first_sentence.md',
                          'server/stt/voice_fast_home.py', 'server/local-llm/gateway.py',
                          'server/local-llm/evaluation_gateway.py','server/benchmark/voice/contention.json']))
    metadata = dict(git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    git_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
                    source_sha256={p: sha256(ROOT/p) for p in files})
    process = subprocess.Popen(home.ssh_args()+['mkdir -p ~/work/ciel-voice-evaluation && tar -xf - -C ~/work/ciel-voice-evaluation'], stdin=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdin, mode='w|') as archive:
            for name in files:
                archive.add(ROOT/name, arcname=name)
            content = json.dumps(metadata).encode()
            item = tarfile.TarInfo('source-provenance.json')
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
    finally:
        process.stdin.close()
    if process.wait():
        raise RuntimeError('Voice evaluation staging failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'prepare', 'stt', 'live', 'status', 'pull'])
    parser.add_argument('--rounds', type=int, default=1)
    parser.add_argument('--smoke', action='store_true', help='Use only the greeting')
    parser.add_argument('--settled', action='store_true', help='Require initial greeting to finish before live input')
    parser.add_argument('--corpus-spec', help='prepare: staged synthesis specification, relative to evaluation root')
    parser.add_argument('--stt-model', choices=['vosk-model-small-ja-0.22', 'vosk-model-ja-0.22'])
    args = parser.parse_args()
    if args.action == 'stage':
        stage()
    elif args.action == 'pull':
        result = subprocess.run(home.ssh_args()+['tar -cf - -C ~/work/ciel-voice-evaluation results'], capture_output=True, check=True)
        output = ROOT/'server/benchmark/data/voice-home'
        output.mkdir(parents=True, exist_ok=True)
        import io
        with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
            for member in archive.getmembers():
                target = (output/member.name).resolve()
                if not target.is_relative_to(output.resolve()) or member.issym() or member.islnk():
                    raise ValueError('Unsafe result archive member')
            archive.extractall(output, filter='data')
        print(output)
    else:
        command = ['python3', 'work/ciel-voice-evaluation/server/stt/voice_measure_home.py',
                   args.action, '--rounds', str(args.rounds)]
        if args.smoke:
            command.append('--smoke')
        if args.settled:
            command.append('--settled')
        if args.stt_model:
            if args.action != 'stt':
                parser.error('stt-model applies only to stt')
            command += ['--stt-model', args.stt_model]
        if args.corpus_spec:
            if args.action != 'prepare' or Path(args.corpus_spec).is_absolute() or '..' in Path(args.corpus_spec).parts:
                parser.error('corpus-spec is a relative staged path for prepare only')
            command += ['--corpus-spec', 'work/ciel-voice-evaluation/'+args.corpus_spec]
        import shlex
        process = subprocess.run(home.ssh_args()+[shlex.join(command)])
        sys.exit(process.returncode)


if __name__ == '__main__':
    main()
