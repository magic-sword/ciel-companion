#!/usr/bin/env python3
"""Save real-model replies to ambiguous ASR text for explicit human rubric review."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prompt-dir', type=Path, required=True)
    p.add_argument('--voice-prompt', type=Path, required=True)
    p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--rounds', type=int, default=1)
    a = p.parse_args()
    if a.output.exists() or a.rounds < 1: p.error('New output and positive rounds required')
    names = ['character','emotion','ciel_self','touch','talker','tasks']
    system = '\n\n'.join((a.prompt_dir/(n+'.md')).read_text(encoding='utf8').strip() for n in names)
    system += '\n\n'+a.voice_prompt.read_text(encoding='utf8').strip()
    report = dict(prompt_sha256=hashlib.sha256(system.encode()).hexdigest(),
                  cases_sha256=hashlib.sha256(a.cases.read_bytes()).hexdigest(),
                  limits='Direct text after ASR; not recognition accuracy or live voice latency; rubric requires review', trials=[])
    with urllib.request.urlopen('http://127.0.0.1:8095/mode',timeout=10) as r:report['before']=json.load(r)
    if not report['before'].get('ready'):raise RuntimeError('Model not ready')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    for repeat in range(a.rounds):
        for case in json.loads(a.cases.read_text(encoding='utf8')):
            body = dict(model='local',messages=[dict(role='system',content=system),dict(role='user',content=case['text'])],
                        temperature=0,seed=1729,max_tokens=128,chat_template_kwargs=dict(enable_thinking=False))
            req=urllib.request.Request('http://127.0.0.1:8094/v1/chat/completions',
                data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            start=time.monotonic()
            with urllib.request.urlopen(req,timeout=60) as r:value=json.load(r)
            trial=dict(case,repeat=repeat,reply=value['choices'][0]['message']['content'],usage=value.get('usage'),
                       elapsed_ms=(time.monotonic()-start)*1000,review=None)
            report['trials'].append(trial)
            a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            print(json.dumps(trial,ensure_ascii=False),flush=True)
    with urllib.request.urlopen('http://127.0.0.1:8095/mode',timeout=10) as r:report['after']=json.load(r)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
