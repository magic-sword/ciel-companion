"""Evidence-based metrics for synthetic skill lifecycle runs (no LLM judge)."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

SERVICES = {'start_minutes': '5', 'read_minutes': '5', 'choose_minutes_destination': '5',
            'search_conversation': '6'}


def metrics(row):
    expected = row['expected']
    proposed, selected, definitions = [], [], 0
    for request in row['requests']:
        for call in request['selected']:
            try:
                args = json.loads(call['arguments'])
                if call['name'] == 'load_capabilities':
                    selected.extend(args.get('service_ids', []))
                else:
                    proposed.append(args.get('tool_id') if call['name'] == 'execute_capability' else call['name'])
            except (ValueError, TypeError, AttributeError):
                proposed.append('invalid_arguments')
    first = row['requests'][0] if row['requests'] else {}
    for message in first.get('messages', []):
        if message['role'] == 'tool' and '"definitions"' in message['content']:
            definitions += len(message['content'])
    completed = Counter(o['name'] for o in row['outputs'])
    operations = []
    for call in row['calls']:
        if call['name'] != 'load_capabilities' and completed[call['name']]:
            operations.append(call)
            completed[call['name']] -= 1
    requested = [c for c in operations if c['name'] == expected]
    arguments_ok = any(all(c['arguments'].get(k, 0 if k == 'lookback_minutes' else None) == v
                           for k, v in row['required'].items()) for c in requested)
    goal = False
    for output in row['outputs']:
        if output['name'] != expected:
            continue
        try:
            data = json.loads(output['value'])
            if expected == 'start_minutes':
                goal |= data.get('recording') is True
            elif expected == 'finish_minutes':
                goal |= data.get('recording') is False and data.get('status') == 'finished'
            elif expected == 'choose_minutes_destination':
                goal |= data.get('destination') == row['required']['name']
            elif expected in ('search_conversation', 'read_minutes'):
                goal |= 'オーロラ' in output['value'] and (expected != 'read_minutes' or data.get('status') == 'ok')
        except (ValueError, TypeError, AttributeError):
            pass
    extra = [c for c in operations if c['name'] not in {expected, 'get_minutes_status'}]
    success = (goal and arguments_ok and not extra and not row['errors']) if expected else not operations and not row['errors']
    return dict(required=bool(expected), selected_services=selected,
        missed_service=bool(expected in SERVICES and SERVICES[expected] not in selected),
        unnecessary_load=bool(not expected and selected),
        wrong_service_load=bool(selected and any(s != SERVICES.get(expected) for s in selected)),
        missing_operation=bool(expected and expected not in proposed),
        undesired_proposal=bool(not expected and proposed),
        arguments_ok=arguments_ok if expected else None,
        operation_success=success, strict_trajectory=row['fixture_success'],
        unexpected_operations=len(extra) if expected else len(operations),
        requests=len(row['requests']), seconds=row['seconds'],
        input_tokens=sum(r['usage']['prompt_tokens'] for r in row['requests']),
        initial_definition_chars=definitions, initial_loaded=len(first.get('loaded', [])),
        errors=len(row['errors']),
        incomplete_dispatches=max(0, len(row['calls']) - len(row['outputs'])))


def summarize(rows):
    data = [metrics(r) for r in rows]
    return dict(n=len(data), required=sum(d['required'] for d in data),
        required_success=sum(d['required'] and d['operation_success'] for d in data),
        no_operation_success=sum(not d['required'] and d['operation_success'] for d in data),
        false_positive_turns=sum(not d['required'] and (d['unnecessary_load'] or d['undesired_proposal']) for d in data),
        counts={key: sum(d[key] for d in data) for key in (
            'missed_service', 'unnecessary_load', 'wrong_service_load', 'missing_operation',
            'undesired_proposal', 'operation_success', 'strict_trajectory', 'unexpected_operations', 'errors')},
        median={key: statistics.median(d[key] for d in data) for key in ('seconds', 'input_tokens', 'requests')},
        initial_loaded=sum(d['initial_loaded'] for d in data),
        turns_with_initial_loaded=sum(bool(d['initial_loaded']) for d in data),
        initial_definition_chars=sum(d['initial_definition_chars'] for d in data))


def compare(before, after):
    if before['suite'] != after['suite']:
        raise ValueError('Different suites cannot be paired')
    for setting in ('temperature', 'seed'):
        if before.get(setting) != after.get(setting):
            raise ValueError(f'Different {setting} cannot be paired')
    def index(run):
        entries = {(r['repeat'], r['sequence'], r['case']): r for r in run['trials']}
        if len(entries) != len(run['trials']):
            raise ValueError('Duplicate trial IDs')
        return entries
    a, b = index(before), index(after)
    keys = sorted(a.keys() & b.keys())
    pairs = [dict(id=key, before=metrics(a[key]), after=metrics(b[key])) for key in keys]
    successful = [p for p in pairs if p['before']['required'] and
                  p['before']['operation_success'] and p['after']['operation_success']]
    return dict(before=summarize(before['trials']), after=summarize(after['trials']),
        matched=len(keys), missing_before=len(b.keys()-a.keys()), missing_after=len(a.keys()-b.keys()),
        improved=sum(not p['before']['operation_success'] and p['after']['operation_success'] for p in pairs),
        regressed=sum(p['before']['operation_success'] and not p['after']['operation_success'] for p in pairs),
        identical_initial_messages=sum(bool(a[k]['requests'] and b[k]['requests']) and
            a[k]['requests'][0]['messages'] == b[k]['requests'][0]['messages'] for k in keys),
        successful_operation_pairs=dict(n=len(successful),
            median_seconds={side: statistics.median(p[side]['seconds'] for p in successful) if successful else None
                            for side in ('before', 'after')}),
        sequences={s: {'before': summarize([a[k] for k in keys if k[1] == s]),
                       'after': summarize([b[k] for k in keys if k[1] == s])}
                   for s in sorted({k[1] for k in keys})}, pairs=pairs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.before.read_text(encoding='utf8')), json.loads(args.after.read_text(encoding='utf8')))
    if args.output.exists():
        raise ValueError('Output must be new')
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k != 'pairs'}, ensure_ascii=False, indent=2))
