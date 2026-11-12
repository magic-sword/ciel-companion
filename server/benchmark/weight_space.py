"""Offline-validatable, stdlib-only LLM regression harness. Tools are fixtures only."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import time
import urllib.request
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).with_name('weight_space')
SCHEMA = 'ciel-weight-space-v1'
PROMPTS = ('character', 'ciel_self', 'app', 'tool_discovery', 'game')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_suite(path):
    suite = read(path)
    if suite.get('schema') != SCHEMA or not suite.get('cases'):
        raise ValueError('Invalid or empty suite')
    seen = set()
    for case in suite['cases']:
        if case['id'] in seen or case['split'] not in ('dev', 'holdout'):
            raise ValueError('Duplicate ID or invalid split')
        seen.add(case['id'])
        if 'dialogue' in case:
            if case.get('stage') not in (1, 2, 3, 4) or not case['dialogue']:
                raise ValueError('Dialogue requires stage 1..4 and turns')
            for turn in case['dialogue']:
                if (not isinstance(turn.get('user'), str)
                        or not any(ch.isalnum() for ch in turn['user']) or not turn.get('rubric')):
                    raise ValueError('Dialogue turn requires user and rubric')
                if not isinstance(turn.get('max_chars'), int) or turn['max_chars'] < 1:
                    raise ValueError('Dialogue turn requires positive max_chars')
                if 'loop_probe' in turn and turn['loop_probe'] not in ('forbidden', 'allowed'):
                    raise ValueError('Unknown loop probe mode')
            if any('loop_probe' in t for t in case['dialogue']):
                probe = case.get('loop_probe', {})
                for key in ('topic_pattern', 'question_pattern'):
                    if not isinstance(probe.get(key), str) or not probe[key]:
                        raise ValueError('Loop probe requires topic and question patterns')
                    re.compile(probe[key])
                units = probe.get('units', {})
                if not isinstance(units, dict):
                    raise ValueError('Loop units must be a mapping')
                for name, pattern in units.items():
                    if not re.fullmatch('[a-z_]+', name) or not isinstance(pattern, str) or not pattern:
                        raise ValueError('Invalid loop unit')
                    re.compile(pattern)
                units = probe.get('units', {})
                if not isinstance(units, dict):
                    raise ValueError('Loop units must be a mapping')
                for name, pattern in units.items():
                    if not re.fullmatch('[a-z_]+', name) or not isinstance(pattern, str) or not pattern:
                        raise ValueError('Invalid loop unit')
                    re.compile(pattern)
        if not case.get('messages') or not case.get('checks'):
            raise ValueError('Messages and checks required')
        if any(not isinstance(m.get('content'), str) or not any(ch.isalnum() for ch in m['content'])
               for m in case['messages']):
            raise ValueError('Empty or corrupted message text')
        for check in case['checks']:
            if check['type'] not in ('exact', 'regex', 'json', 'calls', 'no_calls', 'human'):
                raise ValueError('Unknown check')
            if check['type'] == 'regex':
                re.compile(check['pattern'])
        tools = {t['function']['name'] for t in case.get('tools', [])}
        for step in case.get('steps', []):
            if step['name'] not in tools:
                raise ValueError('Fixture tool must be declared')
    return suite


def percentile(values, fraction):
    values = sorted(v for v in values if v is not None and math.isfinite(v))
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def equal(a, b):
    """JSON equality with explicit scalar types (true is not 1, 8.0 is not integer 8)."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def score(case, messages, calls):
    text = '\n'.join(m.get('content') or '' for m in messages)
    results = []
    for check in case['checks']:
        kind = check['type']
        passed = None
        if kind == 'exact':
            passed = text.strip() == check['value']
        elif kind == 'regex':
            passed = bool(re.search(check['pattern'], text))
        elif kind == 'json':
            try:
                passed = equal(json.loads(text), check['value'])
            except (ValueError, TypeError):
                passed = False
        elif kind == 'no_calls':
            passed = not calls
        elif kind == 'calls':
            passed = equal(calls, [{'name': s['name'], 'arguments': s['arguments']} for s in case['steps']])
        results.append({'type': kind, 'pass': passed, 'rubric': check.get('rubric')})
    return results


def stream_chat(base_url, payload, timeout):
    """Assemble OpenAI SSE content/reasoning/tool fragments; never execute tools."""
    request = urllib.request.Request(base_url.rstrip('/') + '/chat/completions',
        data=json.dumps(dict(payload, stream=True, stream_options={'include_usage': True})).encode(),
        headers={'Content-Type': 'application/json', 'X-Ciel-Work-Class': 'foreground'})
    started = time.monotonic()
    first_content = first_event = None
    content, reasoning, tools = [], [], {}
    finish, usage, timings = None, {}, {}
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            if time.monotonic() - started > timeout:
                raise TimeoutError('Generation deadline exceeded')
            if not raw.startswith(b'data:'):
                continue
            value = raw[5:].strip()
            if value == b'[DONE]':
                break
            event = json.loads(value)
            usage = event.get('usage') or usage
            timings = event.get('timings') or timings
            for choice in event.get('choices', []):
                delta = choice.get('delta', {})
                if any(delta.get(k) for k in ('content', 'reasoning_content', 'tool_calls')) and first_event is None:
                    first_event = (time.monotonic() - started) * 1000
                if delta.get('content'):
                    if first_content is None:
                        first_content = (time.monotonic() - started) * 1000
                    content.append(delta['content'])
                if delta.get('reasoning_content'):
                    reasoning.append(delta['reasoning_content'])
                for fragment in delta.get('tool_calls', []):
                    item = tools.setdefault(fragment['index'], {'id': '', 'type': 'function',
                        'function': {'name': '', 'arguments': ''}})
                    if fragment.get('id'):
                        item['id'] = fragment['id']
                    for field in ('name', 'arguments'):
                        item['function'][field] += fragment.get('function', {}).get(field, '')
                finish = choice.get('finish_reason') or finish
    if finish is None:
        raise ValueError('SSE ended without finish_reason')
    message = {'role': 'assistant', 'content': ''.join(content)}
    if tools:
        message['tool_calls'] = [tools[i] for i in sorted(tools)]
    return message, {'first_event_ms': first_event, 'first_content_ms': first_content,
        'total_ms': (time.monotonic() - started) * 1000, 'finish_reason': finish,
        'usage': usage, 'timings': timings, 'reasoning': ''.join(reasoning)}


def run_case(case, system, args, seed, chat=stream_chat):
    if 'dialogue' in case:
        return run_dialogue(case, system, args, seed, chat)
    history = [{'role': 'system', 'content': system + '\n' + case.get('context', '')}] + copy.deepcopy(case['messages'])
    generated, calls, measurements = [], [], []
    steps = case.get('steps', [])
    visible = [copy.deepcopy(t) for t in case.get('tools', [])
               if t['function']['name'] in case.get('initial_tools', [x['function']['name'] for x in case.get('tools', [])])]
    started = time.monotonic()
    result = {'id': case['id'], 'category': case['category'], 'seed': seed, 'status': 'ok'}
    try:
        for turn in range(len(steps) + 1):
            remaining = args.timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('Case deadline exceeded')
            payload = dict(model=args.model, messages=history, temperature=args.temperature,
                           seed=seed, max_tokens=args.max_tokens,
                           chat_template_kwargs={'enable_thinking': args.thinking})
            if visible:
                payload.update(tools=visible, tool_choice='auto')
            message, timing = chat(args.base_url, payload, remaining)
            generated.append(message)
            measurements.append(timing)
            history.append(message)
            if timing['finish_reason'] == 'length':
                result['status'] = 'token_limit'
                break
            emitted = message.get('tool_calls', [])
            if not emitted:
                break
            for call in emitted:
                parsed = {'name': call['function']['name'], 'arguments': json.loads(call['function']['arguments'])}
                calls.append(parsed)
                index = len(calls) - 1
                if (index >= len(steps) or not equal(parsed, {k: steps[index][k] for k in ('name', 'arguments')})
                        or parsed['name'] not in {t['function']['name'] for t in visible}):
                    raise ValueError('Unexpected tool or arguments; fixture refused')
                step = steps[index]
                history.append({'role': 'tool', 'tool_call_id': call['id'],
                                'content': json.dumps(step['result'], ensure_ascii=False)})
                if 'next_tools' in step:
                    visible = copy.deepcopy(step['next_tools'])
            if turn == len(steps):
                raise ValueError('Tool turn budget exceeded')
    except Exception as exc:
        result.update(status='error', error=type(exc).__name__ + ': ' + str(exc))
    checks = score(case, generated, calls)
    result.update(messages=generated, calls=calls, measurements=measurements, checks=checks,
                  total_ms=(time.monotonic() - started) * 1000,
                  automatic_pass=result['status'] == 'ok' and all(c['pass'] for c in checks if c['type'] != 'human'),
                  human_pending=any(c['type'] == 'human' for c in checks))
    return result


def response_metrics(text, previous):
    """Literal repetition signals only; semantic repetition needs human review."""
    sentences = [s.strip() for s in re.split(r'[。！？!?\n]+', text) if s.strip()]
    normalized = [re.sub(r'\s+', '', s) for s in sentences]
    eligible = [s for s in normalized if len(s) >= 8]
    old = {re.sub(r'\s+', '', s.strip()) for reply in previous
           for s in re.split(r'[。！？!?\n]+', reply) if s.strip()}
    return dict(chars=len(text), sentences=len(sentences),
                repeated_sentences=len(eligible) - len(set(eligible)),
                reused_sentences=sum(s in old for s in eligible))


def run_dialogue(case, system, args, seed, chat):
    history = copy.deepcopy(case['messages'])
    generated, measurements, calls, turns = [], [], [], []
    started = time.monotonic()
    status = 'ok'
    error = None
    for index, turn in enumerate(case['dialogue']):
        remaining = args.timeout - (time.monotonic() - started)
        if remaining <= 0:
            status = 'error'
            error = 'TimeoutError: Dialogue deadline exceeded'
            break
        history.append({'role': 'user', 'content': turn['user']})
        child = dict(id=case['id'], category=case['category'], messages=history,
                     context=case.get('context', ''), checks=[{'type': 'no_calls'}])
        child_args = copy.copy(args)
        child_args.timeout = remaining
        row = run_case(child, system, child_args, seed + index, chat)
        text = '\n'.join(m.get('content') or '' for m in row['messages'])
        metrics = response_metrics(text, [m.get('content') or '' for m in generated])
        turns.append(dict(index=index, user=turn['user'], response=row['messages'],
                          rubric=turn['rubric'], max_chars=turn['max_chars'],
                          over_length=metrics['chars'] > turn['max_chars'], metrics=metrics,
                          status=row['status'], error=row.get('error'), ratings=None, evidence=None))
        generated.extend(row['messages'])
        measurements.extend(row['measurements'])
        calls.extend(row['calls'])
        history.extend(row['messages'])
        if not row['automatic_pass'] or not text.strip():
            status = row['status'] if row['status'] != 'ok' else 'error'
            error = row.get('error') or ('Empty response' if not text.strip() else row['status'])
            break
    checks = score(case, generated, calls)
    return dict(id=case['id'], category=case['category'], stage=case['stage'], seed=seed,
                status=status, error=error, messages=generated, calls=calls, measurements=measurements,
                turns=turns, checks=checks, human_pending=True,
                total_ms=(time.monotonic() - started) * 1000,
                automatic_pass=status == 'ok' and len(turns) == len(case['dialogue'])
                    and all(c['pass'] for c in checks if c['type'] != 'human'))


def summary(trials):
    groups = {}
    for category in sorted({r['category'] for r in trials}):
        rows = [r for r in trials if r['category'] == category]
        latency = [r['total_ms'] for r in rows if r['status'] == 'ok']
        groups[category] = dict(n=len(rows), automatic_pass=sum(r['automatic_pass'] for r in rows),
            errors=sum(r['status'] != 'ok' for r in rows), human_pending=sum(r['human_pending'] for r in rows),
            latency_n=len(latency), p50_ms=percentile(latency, .5), p95_ms=percentile(latency, .95))
        turns = [t for r in rows for t in r.get('turns', [])]
        if turns:
            groups[category]['conversation'] = dict(
                observed_turns=len(turns),
                over_length_turns=sum(t['over_length'] for t in turns),
                repeated_sentences=sum(t['metrics']['repeated_sentences'] for t in turns),
                reused_sentences=sum(t['metrics']['reused_sentences'] for t in turns),
                chars_p50=percentile([t['metrics']['chars'] for t in turns], .5),
                chars_p95=percentile([t['metrics']['chars'] for t in turns], .95))
        for key in ('first_event_ms', 'first_content_ms'):
            values = [m.get(key) for r in rows for m in r.get('measurements', []) if m.get(key) is not None]
            groups[category][key] = dict(n=len(values), p50=percentile(values, .5), p95=percentile(values, .95))
    return groups


def probe(base, path):
    try:
        with urllib.request.urlopen(base.rstrip('/') + path, timeout=5) as response:
            return json.load(response)
    except Exception as exc:
        return {'error': type(exc).__name__}


def provenance():
    def git(*args):
        return subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(), *args],
                                       cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    try:
        return {'commit': git('rev-parse', 'HEAD'), 'dirty': bool(git('status', '--porcelain'))}
    except (OSError, subprocess.CalledProcessError):
        return {'commit': None, 'dirty': None}


def compare(base, candidate, *, change='weights'):
    if change not in ('weights', 'prompt'):
        raise ValueError('Unknown comparison change')
    if any(r.get('schema') != SCHEMA or r.get('completion') != 'complete' for r in (base, candidate)):
        return {'decision': 'incomplete'}
    fields = ('suite_sha256', 'runner_sha256', 'prompt_sha256', 'split', 'sampling', 'case_ids', 'rounds', 'prompt_mode')
    mismatches = [k for k in fields if base.get(k) != candidate.get(k)]
    if change == 'prompt':
        mismatches = [k for k in mismatches if k != 'prompt_sha256']
        for key in ('model_id', 'weights_sha256'):
            if base['conditions'].get(key) != candidate['conditions'].get(key):
                mismatches.append('conditions.' + key)
    for key in ('hardware', 'runtime', 'shared_load'):
        if base['conditions'].get(key) != candidate['conditions'].get(key):
            mismatches.append('conditions.' + key)
    modes = [base.get('before', {}).get('mode', {}).get('mode'), base.get('after', {}).get('mode'),
             candidate.get('before', {}).get('mode', {}).get('mode'), candidate.get('after', {}).get('mode')]
    if None in modes or len(set(modes)) != 1:
        mismatches.append('observed_mode')
    if mismatches:
        return {'decision': 'incomparable', 'mismatches': mismatches}
    a = {(r['id'], r['repeat']): r for r in base['trials']}
    b = {(r['id'], r['repeat']): r for r in candidate['trials']}
    if a.keys() != b.keys() or len(a) != len(base['trials']) or len(b) != len(candidate['trials']):
        return {'decision': 'incomplete'}
    expected = {(id, repeat) for id in base['case_ids'] for repeat in range(base['rounds'])}
    if a.keys() != expected:
        return {'decision': 'incomplete'}
    regressions = [list(k) for k in a if a[k]['automatic_pass'] and not b[k]['automatic_pass']]
    errors = sum(r['status'] != 'ok' for r in b.values())
    return {'decision': 'reject' if regressions or errors else 'review_required',
            'change': change,
            'automatic_regressions': regressions, 'candidate_errors': errors,
            'baseline': summary(list(a.values())), 'candidate': summary(list(b.values())),
            'note': 'Human persona, statistical non-inferiority, live voice and real MCP/body checks remain required.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('validate', 'preflight', 'run', 'compare'))
    parser.add_argument('--suite', type=Path, default=DATA / 'suite.json')
    parser.add_argument('--base-url', default='http://127.0.0.1:8094/v1')
    parser.add_argument('--control-url', default='http://127.0.0.1:8095')
    parser.add_argument('--model', default='local')
    parser.add_argument('--conditions', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--change', choices=('weights', 'prompt'), default='weights')
    parser.add_argument('--prompt-dir', type=Path, default=ROOT / 'server/agent/config/prompts')
    parser.add_argument('--split', choices=('dev', 'holdout'), default='dev')
    parser.add_argument('--prompt-mode', choices=('deployed', 'minimal'), default='deployed')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--seed', type=int, default=1729)
    parser.add_argument('--temperature', type=float, default=0)
    parser.add_argument('--max-tokens', type=int, default=512)
    parser.add_argument('--thinking', action='store_true', help='Enable reasoning; default off matches models.py')
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--case', action='append', dest='selected', help='Exact case ID; repeat to select several')
    args = parser.parse_args()
    if (args.rounds < 1 or args.max_tokens < 1 or not math.isfinite(args.timeout) or args.timeout <= 0
            or not math.isfinite(args.temperature) or args.temperature < 0 or (args.limit is not None and args.limit < 1)):
        parser.error('Invalid generation settings')
    if args.mode == 'compare':
        if not args.baseline or not args.candidate:
            parser.error('compare requires --baseline and --candidate report.json')
        result = compare(read(args.baseline), read(args.candidate), change=args.change)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['decision'] == 'review_required' else 1
    suite = load_suite(args.suite)
    if args.mode == 'validate':
        print(json.dumps({'schema': SCHEMA, 'cases': len(suite['cases']),
                          'suite_sha256': digest(args.suite)}, indent=2))
        return 0
    if urlparse(args.base_url).hostname not in ('localhost', '127.0.0.1', '::1'):
        parser.error('Use a loopback API or authenticated SSH tunnel; no cloud endpoint fallback')
    if urlparse(args.control_url).hostname not in ('localhost', '127.0.0.1', '::1'):
        parser.error('Control URL must also be loopback')
    state = {'models': probe(args.base_url, '/models'), 'mode': probe(args.control_url, '/mode')}
    if args.mode == 'preflight':
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return int(any('error' in v for v in state.values()))
    if not args.conditions or not args.output:
        parser.error('run requires --conditions and new --output directory')
    conditions = read(args.conditions)
    required = ('model_id', 'weights_sha256', 'hardware', 'runtime', 'shared_load')
    if any(not conditions.get(k) or 'REPLACE' in str(conditions[k]) for k in required):
        parser.error('Replace all required condition template values')
    if not re.fullmatch('[0-9a-f]{64}', conditions['weights_sha256']):
        parser.error('weights_sha256 must be an actual SHA-256')
    if any('error' in v for v in state.values()) or not state['mode'].get('ready'):
        parser.error('Model/control preflight unavailable or not ready')
    cases = [c for c in suite['cases'] if c['split'] == args.split]
    if args.selected:
        if set(args.selected) - {c['id'] for c in cases}:
            parser.error('Selected case not found in split')
        cases = [c for c in cases if c['id'] in args.selected]
    if args.limit:
        cases = cases[:args.limit]
    prompt_files = [args.prompt_dir / (p + '.md') for p in PROMPTS]
    system = ('\n'.join(p.read_text(encoding='utf-8') for p in prompt_files)
              if args.prompt_mode == 'deployed' else 'あなたはシエルです。日本語で答えてください。')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=SCHEMA, created_utc=datetime.now(timezone.utc).isoformat(),
        **provenance(), suite_sha256=digest(args.suite), runner_sha256=digest(__file__),
        prompt_sha256=hashlib.sha256(system.encode()).hexdigest(), prompt_mode=args.prompt_mode,
        prompt_chars=len(system),
        split=args.split, sampling=dict(temperature=args.temperature, max_tokens=args.max_tokens,
            timeout=args.timeout, seed=args.seed, thinking=args.thinking), rounds=args.rounds, case_ids=[c['id'] for c in cases],
        conditions=conditions, before=state, completion='running', trials=[])
    write(args.output / 'report.json', report)
    reviews = []
    for repeat in range(args.rounds):
        ordered = cases[:]
        random.Random(args.seed + repeat).shuffle(ordered)
        for case in ordered:
            row = run_case(case, system, args, args.seed + repeat)
            row['repeat'] = repeat
            report['trials'].append(row)
            if row['human_pending']:
                reviews.append(dict(id=row['id'], repeat=repeat, messages=case['messages'],
                    response=row['messages'], rubrics=[c['rubric'] for c in row['checks'] if c['type'] == 'human'],
                    ratings=None, evidence=None))
                if 'turns' in row:
                    reviews[-1]['turns'] = row['turns']
            report['summary'] = summary(report['trials'])
            write(args.output / 'report.json', report)
            write(args.output / 'human-review.json', reviews)
            print(case['id'], repeat, row['status'], flush=True)
    report.update(completion='complete', after=probe(args.control_url, '/mode'))
    write(args.output / 'report.json', report)
    return int(any(not r['automatic_pass'] for r in report['trials']))


if __name__ == '__main__':
    raise SystemExit(main())
