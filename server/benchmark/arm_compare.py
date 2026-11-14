"""Compare body variants (for example with and without the !obtainItem plan executor) trial by trial.

Usage: python -m benchmark.arm_compare BASELINE_DIR CANDIDATE_DIR [...]
Each directory holds a report.json from run.py. Runs are paired by task and layout seed; only
trials scored in every run (passed or failed) enter the paired table. Infrastructure errors
and skipped trials are counted, never treated as failures.
"""
import argparse
import json
from pathlib import Path

SAME = ('policy', 'mode', 'model_id', 'suite_sha256', 'progress_rule')


def load(directory):
    report = json.loads((Path(directory)/'report.json').read_text(encoding='utf-8'))
    manifest = report['manifest']
    label = 'blocked ' + ','.join(manifest['body_blocked_actions']) if manifest.get('body_blocked_actions') else 'default'
    trials = {(t['task'], t['seed'], t.get('repeat', 0)): t for t in report['trials']}
    return {'label': label, 'manifest': manifest, 'trials': trials}


def value(trial):
    metrics = trial.get('metrics') or {}
    progress = trial.get('progress') or {}
    return {'passed': trial['status'] == 'passed', 'seconds': trial.get('time_to_goal_seconds'),
            'llm_calls': metrics.get('llm_calls'), 'milestones': progress.get('milestones'),
            'false_goal_done': bool(trial.get('false_goal_done')), 'reason': trial.get('reason')}


def mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values)/len(values), 2) if values else None


def compare(runs):
    mismatched = {k: [r['manifest'].get(k) for r in runs] for k in SAME
                  if len({json.dumps(r['manifest'].get(k)) for r in runs}) > 1}
    keys = sorted(set().union(*(r['trials'] for r in runs)))
    scored = [k for k in keys if all(r['trials'].get(k, {}).get('status') in ('passed', 'failed') for r in runs)]
    unscored = {r['label']: sum(1 for k in keys if r['trials'].get(k, {}).get('status') not in ('passed', 'failed'))
                for r in runs}
    tasks = sorted({k[0] for k in scored})
    summary = []
    for task in tasks:
        for run in runs:
            rows = [value(run['trials'][k]) for k in scored if k[0] == task]
            summary.append({'task': task, 'arm': run['label'], 'passed': sum(r['passed'] for r in rows), 'scored': len(rows),
                            'mean_seconds_passed': mean(r['seconds'] for r in rows if r['passed']),
                            'mean_llm_calls': mean(r['llm_calls'] for r in rows),
                            'mean_milestones': mean(r['milestones'] for r in rows),
                            'false_goal_done': sum(r['false_goal_done'] for r in rows)})
    paired = [{'task': k[0], 'seed': k[1], 'repeat': k[2], **{run['label']: value(run['trials'][k]) for run in runs}}
              for k in scored]
    return {'mismatched_conditions': mismatched, 'unscored': unscored, 'summary': summary, 'paired': paired}


def markdown(result, labels):
    lines = []
    if result['mismatched_conditions']:
        lines += ['**Conditions differ:** ' + json.dumps(result['mismatched_conditions'], ensure_ascii=False), '']
    lines += ['| Task | Arm | Passed / scored | Mean s (passed) | Mean LLM calls | Mean milestones | False done |',
              '|---|---|---:|---:|---:|---:|---:|']
    for row in result['summary']:
        lines.append(f"| {row['task']} | {row['arm']} | {row['passed']} / {row['scored']} | {row['mean_seconds_passed']} | "
                     f"{row['mean_llm_calls']} | {row['mean_milestones']} | {row['false_goal_done']} |")
    lines += ['', '| Task | Seed | ' + ' | '.join(labels) + ' |', '|---|---:|' + '---|'*len(labels)]
    for row in result['paired']:
        cells = []
        for label in labels:
            v = row[label]
            cells.append(f"{'pass' if v['passed'] else 'fail ('+str(v['reason'])+')'} {v['seconds']}s, {v['llm_calls']} calls, m={v['milestones']}")
        lines.append(f"| {row['task']} | {row['seed']} | " + ' | '.join(cells) + ' |')
    lines += ['', 'Unscored trials (infrastructure / skipped): ' + json.dumps(result['unscored'], ensure_ascii=False)]
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('runs', nargs='+')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    runs = [load(d) for d in args.runs]
    if len({r['label'] for r in runs}) != len(runs):
        ap.error('Each run must be a different body variant')
    result = compare(runs)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else markdown(result, [r['label'] for r in runs]))


if __name__ == '__main__':
    main()
