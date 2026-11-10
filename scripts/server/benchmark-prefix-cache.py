#!/usr/bin/env python3
"""Probe prefix reuse across changed conversation suffixes on an existing local API."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prompt-dir', type=Path, required=True)
    p.add_argument('--base-url', default='http://127.0.0.1:8094')
    p.add_argument('--control-url', default='http://127.0.0.1:8095')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--prefix-tag', default='', help='Same fresh prefix tag for all compared configurations')
    args = p.parse_args()
    if args.rounds < 1 or args.output.exists():
        p.error('Positive rounds and a new output file required')
    names = ['character', 'emotion', 'ciel_self', 'touch', 'talker', 'tasks', 'voice_first_sentence']
    system = '\n\n'.join((args.prompt_dir/(name+'.md')).read_text(encoding='utf-8').strip() for name in names)
    if args.prefix_tag:
        system = args.prefix_tag+'\n\n'+system
    def get(url):
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.load(response)
    report = dict(schema='ciel-prefix-probe-v1', prompt_sha256=hashlib.sha256(system.encode()).hexdigest(),
                  before=get(args.control_url+'/mode'), props=get(args.base_url+'/props'), trials=[])
    if not report['before'].get('ready'):
        raise RuntimeError('Shared API not ready')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for repeat in range(args.rounds):
        # First request primes a slot. Later requests change only a suffix of the system.
        # This is a cache diagnosis, not an end-to-end voice/performance score.
        for phase, notice in [('prime', ''), ('context-a', '\n\nCurrent turn: A.'),
                              ('context-b', '\n\nCurrent turn: B.')]:
            body = dict(model='local', messages=[dict(role='system', content=system+notice),
                        dict(role='user', content='Hello.')], temperature=0, seed=1729,
                        max_tokens=1, stream=False, id_slot=0, cache_prompt=True,
                        chat_template_kwargs=dict(enable_thinking=False))
            started = time.monotonic()
            req = urllib.request.Request(args.base_url+'/v1/chat/completions',
                data=json.dumps(body).encode(), headers={'Content-Type':'application/json',
                                                       'X-Ciel-Work-Class':'foreground'})
            with urllib.request.urlopen(req, timeout=60) as response:
                value = json.load(response)
            report['trials'].append(dict(repeat=repeat, phase=phase,
                elapsed_ms=round((time.monotonic()-started)*1000, 2),
                usage=value.get('usage'), timings=value.get('timings')))
            args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    report['after'] = get(args.control_url+'/mode')
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('schema', 'prompt_sha256', 'before', 'trials', 'after')}))


if __name__ == '__main__':
    main()
