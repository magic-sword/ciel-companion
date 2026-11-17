"""Bounded local-LLM experiment. All tools are deterministic fixtures, never services.

Run from the repository root with .venv/Scripts/python.exe. This is an ablation
control, not a replay of the production Initiative scheduler or a voice test.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import tomllib
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server/agent'))
# This script has the same basename: load the agent module under an explicit alias.
import importlib.util
spec = importlib.util.spec_from_file_location('agent_continuation', ROOT / 'server/agent/continuation.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
from persona import load_persona, DEFAULT_CONFIG

SUITE = Path(__file__).with_name('continuation_cases.json')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_cases():
    cases = json.loads(SUITE.read_text(encoding='utf-8'))
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate case IDs')
    return cases


class FixtureCatalog:
    loader = SimpleNamespace(id='load_capabilities')
    executor = SimpleNamespace(id='execute_capability')

    def __init__(self, fixture):
        self.fixture = fixture
        self.allowed = {'search_fixture'} if fixture else set()
        self.loaded = False
        self.calls = []

    def available(self):
        return [SimpleNamespace(id='research', name='research')] if self.allowed else []

    def service_for(self, name):
        return 'research'

    def can_execute(self, name):
        return name in self.allowed and self.loaded

    def definition(self, name):
        if not self.can_execute(name):
            return None
        return dict(version='1', schema=dict(parameters=dict(type='object', additionalProperties=False,
            properties={'query': {'type': 'string', 'minLength': 1, 'maxLength': 200}}, required=['query'])))

    def target(self, call):
        return json.loads(call.arguments).get('tool_id', call.name)

    def execute(self, call):
        args = json.loads(call.arguments)
        if call.name == self.loader.id:
            self.loaded = True
            return dict(status='ok', tool_id='search_fixture', **self.definition('search_fixture'))
        assert call.name == self.executor.id and args['version'] == '1'
        self.calls.append(args)
        return self.fixture


def fixed_prompt(variant, catalog, baseline_ref=None):
    persona = load_persona()
    instructions = persona.tool_decide_instructions.split('今回の進行状態：')[0].strip()
    parts = [persona.instructions, persona.self_instructions, instructions]
    if catalog.allowed:
        parts.append('利用できるサービスは research（Web検索）。定義をロードしてから検索する。')
    config = tomllib.loads(DEFAULT_CONFIG.read_text(encoding='utf-8'))
    if variant != 'control':
        if variant == 'baseline':
            if not baseline_ref:
                raise ValueError('baseline variant requires --baseline-ref')
            parts.append(subprocess.check_output(['git', 'show',
                baseline_ref + ':server/agent/config/prompts/continuation.md'], cwd=ROOT).decode('utf-8'))
        else:
            parts.append((DEFAULT_CONFIG.parent / config['continuation_experiment_file']).read_text(encoding='utf-8'))
    if variant == 'memo':
        parts.append((DEFAULT_CONFIG.parent / config['continuation_memo_experiment_file']).read_text(encoding='utf-8'))
    if variant == 'chunked':
        parts.append((DEFAULT_CONFIG.parent / config['continuation_chunk_experiment_file']).read_text(encoding='utf-8'))
    parts.append(persona.reply_frame)
    return '\n\n'.join(parts)


async def sample(client, args, case, variant, repeat, deadline):
    catalog = FixtureCatalog(case.get('fixture'))
    visible = {x.id: x for x in (catalog.loader, catalog.executor)}
    loop = runtime.Continuation(enabled=variant != 'control', memo=variant == 'memo', max_steps=args.max_steps,
                                turn_first=variant != 'baseline', speech_chars=120 if variant == 'chunked' else None,
                                terminal_wait=variant == 'chunked')
    system = fixed_prompt(variant, catalog, getattr(args, 'baseline_ref', None))
    messages = [dict(role='system', content=system)]
    trace = dict(case=case['id'], variant=variant, repeat=repeat, prompt_sha256=digest(system),
                 turns=[], status='running', quality=None, calls=[])
    try:
        for phase, event in enumerate(case['events']):
            messages.append(dict(role=event['role'], content=event['content']))
            token = loop.wake()
            while not loop.waiting:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('experiment_budget_exhausted')
                schema = loop.schema(catalog, visible)
                # Append-only metadata; never rewrite the system prefix or old decisions.
                messages.append(dict(role='user', content='SYSTEM: ' + loop.chain.context() + '\n' + loop.chain.menu(schema)))
                request = dict(model=args.model, messages=messages, temperature=args.temperature, seed=1729 + repeat,
                    max_tokens=args.max_tokens, stream=False, cache_prompt=True,
                    chat_template_kwargs={'enable_thinking': False},
                    response_format={'type': 'json_schema', 'json_schema': {'name': 'decision', 'schema': schema}})
                started = time.monotonic()
                response = await client.post(args.base_url.rstrip('/') + '/v1/chat/completions', json=request,
                    timeout=min(90, remaining), headers={'X-Ciel-Work-Class': 'background'})
                response.raise_for_status()
                data = response.json()
                choice = data['choices'][0]
                row = dict(phase=phase, elapsed_ms=round(1000 * (time.monotonic()-started), 2),
                           usage=data.get('usage'), timings=data.get('timings'),
                           finish_reason=choice.get('finish_reason'), raw=choice['message'].get('content'),
                           request_sha256=digest(request))
                trace['turns'].append(row)
                if choice.get('finish_reason') == 'length':
                    raise RuntimeError('generation_truncated')
                value = json.loads(row['raw'])
                text, call = loop.accept(token, value, schema, catalog, visible)
                row.update(decision=value, spoken=text)
                messages.append(dict(role='assistant', content=row['raw']))
                if call is not None:
                    result = catalog.execute(call)
                    target = catalog.target(call)
                    loop.chain.observe(target, result)
                    row['tool_result'] = result
                    messages.append(dict(role='user', content='SYSTEM: ' + json.dumps(
                        {'tool': target, 'result': result}, ensure_ascii=False)))
                # Text delivery is immediate in this fixture. No TTS latency is claimed.
                continued = loop.finish(token)
                row['continued'] = continued
                row['terminal_override'] = (call is None and value.get('next') == 'continue'
                    and value['act']['kind'] in ('clarify', 'blocked', 'accepted') and not continued)
        trace['status'] = 'complete'
    except Exception as error:
        trace['status'] = 'failed'
        trace['error'] = type(error).__name__ + ': ' + str(error)[:300]
    trace['calls'] = catalog.calls
    trace['checks'] = dict(
        operation_expected=bool(case.get('fixture')) and case['id'] != 'no_search',
        operation_issued=bool(catalog.calls),
        load_observed=any(t.get('decision', {}).get('act', {}).get('kind') == 'load' for t in trace['turns']),
        successful_result_observed=any(t.get('decision', {}).get('act', {}).get('kind') == 'call'
            and t.get('tool_result', {}).get('status') == 'ok' for t in trace['turns']),
        first_phase_spoken_turns=sum(bool(t.get('spoken')) for t in trace['turns'] if t['phase'] == 0))
    trace['transcript'] = messages
    trace['trace_sha256'] = digest(trace['turns'])
    return trace


def summarize(report):
    rows = []
    for trace in report['trials']:
        turns = trace['turns']
        usage = [t.get('usage') or {} for t in turns]
        cached = [(u.get('prompt_tokens_details') or {}).get('cached_tokens') for u in usage]
        rows.append(dict(case=trace['case'], variant=trace['variant'], repeat=trace['repeat'],
            status=trace['status'], requests=len(turns), tool_calls=len(trace['calls']),
            spoken_turns=sum(bool(t.get('spoken')) for t in turns),
            elapsed_ms=round(sum(t['elapsed_ms'] for t in turns), 2),
            output_tokens=sum(u.get('completion_tokens', 0) for u in usage),
            cached_tokens=sum(cached) if cached and all(x is not None for x in cached) else None,
            quality=None))
    return rows


async def run(args):
    if args.output.exists():
        raise ValueError('Output exists; choose a new report path')
    cases = load_cases()
    if args.cases:
        wanted = set(args.cases.split(','))
        unknown = wanted - {c['id'] for c in cases}
        if unknown:
            raise ValueError('Unknown cases: ' + ','.join(sorted(unknown)))
        cases = [c for c in cases if c['id'] in wanted]
    else:
        cases = [c for c in cases if c['split'] == 'dev']
    variants = args.variants.split(',')
    if not variants or len(set(variants)) != len(variants) or any(v not in ('control', 'loop', 'memo', 'baseline', 'chunked') for v in variants):
        raise ValueError('Unique variants: control,loop,memo,baseline,chunked')
    baseline_ref = getattr(args, 'baseline_ref', None)
    if 'baseline' in variants:
        if not baseline_ref:
            raise ValueError('baseline requires --baseline-ref')
        args.baseline_ref = subprocess.check_output(['git', 'rev-parse', '--verify', baseline_ref + '^{commit}'],
            cwd=ROOT, text=True).strip()
    sources = [Path(__file__), SUITE, ROOT/'server/agent/continuation.py', ROOT/'server/agent/tool_decision.py']
    report = dict(schema='ciel-continuation-v1', suite_sha256=digest(cases),
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        conditions=dict(model=args.model, repeats=args.repeats, temperature=args.temperature, seed=1729,
                        max_tokens=args.max_tokens, max_steps=args.max_steps, budget_seconds=args.budget,
                        baseline_ref=getattr(args, 'baseline_ref', None),
                        fixtures=True, production_baseline=False, audio=False), trials=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    deadline = time.monotonic() + args.budget
    async with httpx.AsyncClient() as client:
        for path in ('health', 'props', 'slots'):
            try:
                result = await client.get(args.base_url.rstrip('/')+'/'+path, timeout=5)
                result.raise_for_status()
                report[path] = result.json()
            except Exception as error:
                report[path] = {'unavailable': type(error).__name__}
        for repeat in range(args.repeats):
            for index, case in enumerate(cases):
                order = variants if (index + repeat) % 2 == 0 else list(reversed(variants))
                for variant in order:
                    if time.monotonic() >= deadline:
                        report['stopped'] = 'experiment_budget_exhausted'
                        save()
                        return 2
                    trace = await sample(client, args, case, variant, repeat, deadline)
                    report['trials'].append(trace)
                    save()
                    print(json.dumps({k: trace[k] for k in ('case', 'variant', 'repeat', 'status')}, ensure_ascii=True), flush=True)
    report['summary'] = summarize(report)
    report['quality_review'] = [dict(case=t['case'], variant=t['variant'], repeat=t['repeat'],
        trace_sha256=t['trace_sha256'], reviewer=None, rubric='continuation-v1',
        scores=None, evidence=None) for t in report['trials']]
    save()
    return 2 if any(t['status'] != 'complete' for t in report['trials']) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:18094')
    parser.add_argument('--model', default='local')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases')
    parser.add_argument('--variants', default='control,loop')
    parser.add_argument('--baseline-ref', help='Commit containing the previous continuation prompt; uses say/act/next order')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--temperature', type=float, default=0)
    parser.add_argument('--max-steps', type=int, default=8)
    parser.add_argument('--max-tokens', type=int, default=300)
    parser.add_argument('--budget', type=int, default=600)
    args = parser.parse_args()
    if min(args.repeats, args.max_steps, args.max_tokens, args.budget) <= 0:
        parser.error('All limits must be positive')
    raise SystemExit(asyncio.run(run(args)))


if __name__ == '__main__':
    main()
