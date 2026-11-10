#!/usr/bin/env python3
"""Replay synthetic pipeline snapshots; prepare all capability prefixes before requests."""
import argparse
import asyncio
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time

spec = importlib.util.spec_from_file_location('fixture', Path(__file__).with_name('benchmark-conversation-tools.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def key(request):
    return json.dumps({'fixed':request['fixed'], 'tools':request['payload'].get('tools',[])},sort_keys=True)


def tagged(request, marker):
    request = copy.deepcopy(request)
    if request['loaded']:
        request['fixed'] = marker+request['fixed']
        request['payload']['messages'][0]['content'] = marker+request['payload']['messages'][0]['content']
    return request


async def run(args):
    if args.output.exists():
        raise ValueError('Output must be new')
    source = json.loads(args.capture.read_text(encoding='utf8'))
    trials = {t['case']:t for t in source['trials']}
    cases = ['minutes','name','history','status']
    for case in cases:
        if not trials[case]['passed'] or len(trials[case]['requests']) != 2:
            raise ValueError('Capture must contain a successful two-step selection for every case')
    profiles = {}
    for case in cases:
        request = trials[case]['requests'][1]
        profiles.setdefault(key(request), request)
    result = {'scope':'Synthetic request replay; capability inventory prepared without user messages; no tools executed',
              'capture_sha256':hashlib.sha256(args.capture.read_bytes()).hexdigest(),
              'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'profiles':len(profiles),'rounds':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    client = fixture.models.create_client('mind')
    async def call(payload, tokens=180):
        return await client.chat.completions.create(model=fixture.models.LOCAL_MODEL,
            temperature=0, seed=1729, max_tokens=tokens, timeout=60,
            extra_body={'chat_template_kwargs':{'enable_thinking':False}}, **payload)
    try:
        for repeat in range(args.rounds):
            for mode in (['unprepared','bank'] if repeat%2==0 else ['bank','unprepared']):
                marker = 'Evaluation bank ID: '+hashlib.sha256(f'{args.output.resolve()}/{repeat}/{mode}'.encode()).hexdigest()[:16]+'\n\n'
                row = {'repeat':repeat,'mode':mode,'preparations':[],'trials':[]}
                result['rounds'].append(row)
                if mode == 'bank':
                    for profile in profiles.values():
                        request = tagged(profile, marker)
                        started = time.monotonic()
                        preparation = {'profile':hashlib.sha256(key(profile).encode()).hexdigest()}
                        try:
                            response = await call({'messages':[{'role':'system','content':request['fixed']},
                                {'role':'user','content':request['warmup']}],
                                'tools':request['payload'].get('tools',[])},1)
                            preparation['usage'] = response.usage.model_dump()
                        except Exception as error:
                            preparation['error'] = type(error).__name__
                        preparation['seconds'] = time.monotonic()-started
                        row['preparations'].append(preparation);save()
                # All preparations finish before any user request. Intervening capability
                # requests and the ordinary routing pass may evict the prepared state.
                for case in cases:
                    started = time.monotonic()
                    trial = {'case':case,'requests':[],'passed':True}
                    try:
                        for original in trials[case]['requests']:
                            request = tagged(original, marker)
                            began = time.monotonic()
                            response = await call(request['payload'])
                            selected = response.choices[0].message.tool_calls or []
                            actual = [{'name':c.function.name,'arguments':json.loads(c.function.arguments)} for c in selected]
                            schemas = {t['function']['name']:t['function']['parameters'] for t in request['payload'].get('tools',[])}
                            for c in actual:
                                fixture.jsonschema.validate(c['arguments'], schemas[c['name']])
                            trial['requests'].append({'seconds':time.monotonic()-began,'loaded':request['loaded'],
                                'usage':response.usage.model_dump(),'calls':actual})
                            if actual != original['expected_calls']:
                                trial['passed'] = False
                                break  # Never replay a continuation after a different route.
                    except Exception as error:
                        trial.update(passed=False,error=type(error).__name__)
                    trial['seconds'] = time.monotonic()-started
                    row['trials'].append(trial);save()
                    print(repeat,mode,case,trial['passed'],round(trial['seconds'],3),flush=True)
    finally:
        await client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,default=3)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('rounds must be positive')
    asyncio.run(run(args))
