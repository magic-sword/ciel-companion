"""Pair continuation trials and export anonymous, unscored review material."""
import argparse
import hashlib
import json
from pathlib import Path
import random


def measurements(trace):
    turns = trace['turns']
    usage = [t.get('usage') or {} for t in turns]
    # Completion time is not first-token or speech latency.
    return dict(requests=len(turns), output_tokens=sum(u.get('completion_tokens', 0) for u in usage),
        elapsed_ms=round(sum(t['elapsed_ms'] for t in turns), 2),
        tool_calls=len(trace['calls']),
        spoken_turns=sum(bool(t.get('spoken')) for t in turns),
        phase1_spoken_turns=sum(bool(t.get('spoken')) for t in turns if t['phase'] == 1))


def compare(report, baseline='baseline', candidate='loop'):
    indexed = {}
    for trace in report['trials']:
        key = (trace['case'], trace['repeat'], trace['variant'])
        if key in indexed:
            raise ValueError('Duplicate trial identity: ' + str(key))
        indexed[key] = trace
    keys = sorted({key[:2] for key in indexed if key[2] in (baseline, candidate)})
    pairs = []
    for case, repeat in keys:
        left, right = (indexed.get((case, repeat, v)) for v in (baseline, candidate))
        row = dict(case=case, repeat=repeat, comparable=bool(left and right
            and left['status'] == right['status'] == 'complete'))
        row['baseline_status'] = left['status'] if left else 'missing'
        row['candidate_status'] = right['status'] if right else 'missing'
        row['baseline'] = measurements(left) if left else None
        row['candidate'] = measurements(right) if right else None
        row['delta'] = {k: round(row['candidate'][k]-row['baseline'][k], 2)
                        for k in row['baseline']} if row['comparable'] else None
        pairs.append(row)
    return dict(suite_sha256=report['suite_sha256'], conditions=report['conditions'],
                stopped=report.get('stopped'), pairs=pairs,
                comparable_pairs=sum(p['comparable'] for p in pairs),
                missing_or_failed_pairs=sum(not p['comparable'] for p in pairs), quality=None)


def review_material(report, seed=20261117):
    """Hide next/memo and variant identity; retain actual tool evidence for review."""
    trials = list(report['trials'])
    random.Random(seed).shuffle(trials)
    review, key = [], []
    for index, trace in enumerate(trials):
        identity = f'S{index+1:03}'
        events = []
        # Source user/event messages only; omit runner status and private JSON output.
        for msg in trace['transcript']:
            if msg['role'] == 'user' and not msg['content'].startswith('SYSTEM: {'):
                events.append(msg['content'])
        conversation = []
        for phase, event in enumerate(events):
            entries = [dict(spoken=t.get('spoken', ''), tool_result=t.get('tool_result'),
                            operation=t.get('decision', {}).get('act') if 'tool_result' in t else None)
                       for t in trace['turns'] if t['phase'] == phase]
            conversation.append(dict(phase=phase, input=event, outputs=entries))
        review.append(dict(sample=identity, conversation=conversation,
                           status=trace['status'], reviewer=None, rubric='continuation-v1',
                           scores=None, evidence=None))
        key.append(dict(sample=identity, case=trace['case'], repeat=trace['repeat'],
                        variant=trace['variant'], trace_sha256=trace['trace_sha256']))
    return review, key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', default='baseline')
    parser.add_argument('--candidate', default='loop')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = json.loads(args.report.read_text(encoding='utf-8'))
    comparison = compare(report, args.baseline, args.candidate)
    comparison['report_sha256'] = hashlib.sha256(args.report.read_bytes()).hexdigest()
    review, key = review_material(report)
    for name, value in [('comparison.json', comparison), ('review.json', review), ('review-key.json', key)]:
        (args.output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: comparison[k] for k in ('comparable_pairs', 'missing_or_failed_pairs', 'quality')}))


if __name__ == '__main__':
    main()
