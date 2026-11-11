"""Offline, paired progress scoring for existing WSP reports; no model calls.

Semantic quality requires attributed, evidence-backed review. Automatic distances
are diagnostic axes, never a substitute for correctness or content quality.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

VERSION = 'conversation-progress-v1'
RATINGS = ('content', 'relevance', 'non_repetition', 'naturalness', 'instruction_following')
LOOP_LABELS = {'unwanted_question': 'lower', 'stale_task_continuation': 'lower',
               'current_request_met': 'higher'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def distance(a, b):
    previous = list(range(len(b)+1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(current[-1]+1, previous[j]+1, previous[j-1]+(left != right)))
        previous = current
    return previous[-1]


def leaves(value, path=()):
    if isinstance(value, dict) and value:
        return {k: v for key, item in value.items() for k, v in leaves(item, path+(key,)).items()}
    if isinstance(value, list) and value:
        return {k: v for i, item in enumerate(value) for k, v in leaves(item, path+(i,)).items()}
    return {path: value}


def structure(expected, actual):
    a, b = leaves(expected), leaves(actual)
    keys = a.keys() | b.keys()
    correct = sum(k in a and k in b and type(a[k]) is type(b[k]) and a[k] == b[k] for k in keys)
    return correct, len(keys)


def metric(value, direction, unit):
    return dict(value=value, direction=direction, unit=unit)


def diagnostics(case, row):
    text = '\n'.join(m.get('content') or '' for m in row.get('messages', []))
    result = {}
    for i, check in enumerate(case['checks']):
        if row['status'] != 'ok' and (check['type'] != 'calls' or not row.get('calls')):
            continue
        prefix = f"check_{i}_{check['type']}"
        if check['type'] == 'exact':
            d = distance(text.strip(), check['value'])
            result[prefix+'_edit_distance'] = metric(d, 'lower', 'characters')
        elif check['type'] == 'json':
            try:
                actual = json.loads(text)
            except (ValueError, TypeError):
                result[prefix+'_fields'] = metric(None, 'higher', 'score_0_5')
            else:
                correct, total = structure(check['value'], actual)
                result[prefix+'_fields'] = metric(5*correct/total, 'higher', 'score_0_5')
                result[prefix+'_wrong_fields'] = metric(total-correct, 'lower', 'fields')
        elif check['type'] == 'calls':
            expected = [dict(name=s['name'], arguments=s['arguments']) for s in case.get('steps', [])]
            actual = row.get('calls', [])
            correct, total = structure(expected, actual)
            result[prefix+'_structure'] = metric(5*correct/total, 'higher', 'score_0_5')
            result[prefix+'_wrong_fields'] = metric(total-correct, 'lower', 'fields')
        elif check['type'] == 'no_calls':
            result[prefix+'_unwanted_calls'] = metric(len(row.get('calls', [])), 'lower', 'calls')
    return result


def score_report(report, suite, reviews=None):
    from server.benchmark.loop_probe import metrics as loop_metrics
    cases = {c['id']: c for c in suite['cases']}
    if len(cases) != len(suite['cases']):
        raise ValueError('Duplicate case IDs')
    if reviews and (reviews.get('report_hash') != fingerprint(report)
                    or reviews.get('version') != VERSION or not reviews.get('evaluator')):
        raise ValueError('Review version, report hash and evaluator required')
    annotations = {}
    for item in (reviews or {}).get('items', []):
        if item['key'] in annotations:
            raise ValueError('Duplicate review key')
        annotations[item['key']] = item
    seen, observations, template = set(), [], []
    for row in report['trials']:
        case = cases[row['id']]
        key = f"{row['id']}:{row['repeat']}"
        if key in seen:
            raise ValueError('Duplicate trial')
        seen.add(key)
        loop_totals, loop_turns = loop_metrics(case, row)
        observations.append(dict(key=key, case=row['id'], category=row['category'],
                                 status=row['status'], metrics={**diagnostics(case, row),
                                     **{k: metric(*v) for k, v in loop_totals.items()}}))
        turns = row.get('turns')
        if turns is None:
            turns = [dict(index=0, response=row.get('messages', []), status=row['status'],
                          rubric='; '.join(c.get('rubric', '') for c in case['checks'] if c['type']=='human'))]
        for turn in turns:
            turn_key = f"{key}:turn:{turn['index']}"
            text = '\n'.join(m.get('content') or '' for m in turn['response'])
            valid = turn['status'] == 'ok' and bool(text.strip())
            measures = {}
            loop = loop_turns.get(turn['index'], {})
            measures.update({k: metric(*v) for k, v in loop.get('metrics', {}).items()})
            measures['chars'] = metric(len(text) if valid else None, 'neutral', 'characters')
            if 'metrics' in turn:
                measures['reused_sentences'] = metric(turn['metrics'].get('reused_sentences') if valid else None,
                                                      'neutral', 'sentences')
            if 'max_chars' in turn:
                excess = max(0, len(text)-turn['max_chars'])
                measures['excess_chars'] = metric(excess if valid else None, 'lower', 'characters')
                measures['length_budget'] = metric(5/(1+excess/turn['max_chars']) if valid else None, 'higher', 'score_0_5')
            sentences = [re.sub(r'\s+', '', s) for s in re.split(r'[。！？!?\n]+',text)]
            eligible = [s for s in sentences if len(s)>=8]
            duplicated = len(eligible)-len(set(eligible))
            measures['literal_duplicate_sentences'] = metric(duplicated if valid else None, 'lower', 'sentences')
            measures['questions'] = metric(len(re.findall('[?？]',text)) if valid else None, 'neutral', 'questions')
            item = dict(key=turn_key, response_hash=fingerprint(turn['response']),
                        case_messages=case['messages'], previous_turns=turns[:turn['index']],
                        user=turn.get('user'), response=turn['response'], rubric=turn.get('rubric'),
                        ratings={name: None for name in RATINGS}, evidence={})
            if loop:
                item['loop_diagnostic'] = loop['evidence']
                item['loop_labels'] = {name: None for name in LOOP_LABELS}
                item['loop_evidence'] = {}
            annotation = annotations.pop(turn_key, None)
            if annotation and annotation.get('response_hash') != item['response_hash']:
                raise ValueError('Review response mismatch')
            if loop:
                for name, direction in LOOP_LABELS.items():
                    label = (annotation or {}).get('loop_labels', {}).get(name)
                    if label is not None and (type(label) is not int or label not in (0, 1)
                            or not (annotation or {}).get('loop_evidence', {}).get(name)):
                        raise ValueError('Loop labels require 0/1 and per-label evidence')
                    measures['review_loop_'+name] = metric(label if valid else None, direction, 'turns')
            for name in RATINGS:
                rating = (annotation or {}).get('ratings', {}).get(name)
                if rating is not None:
                    if (type(rating) not in (int, float) or not math.isfinite(rating)
                            or not 0<=rating<=4 or not (annotation or {}).get('evidence', {}).get(name)):
                        raise ValueError('Ratings require 0..4 and per-axis evidence')
                measures['review_'+name] = metric(5*rating/4 if valid and rating is not None else None, 'higher', 'score_0_5')
            template.append(item)
            observations.append(dict(key=turn_key, case=row['id'], category=row['category'],
                                     status=turn['status'], metrics=measures))
    if annotations:
        raise ValueError('Unknown review keys')
    return (dict(version=VERSION, source=report, observations=observations,
                 evaluator=(reviews or {}).get('evaluator')),
            dict(version=VERSION, report_hash=fingerprint(report), evaluator=None, items=template))


def compare_scores(base, candidate, change='weights'):
    from server.benchmark.weight_space import compare
    if base['version'] != VERSION or candidate['version'] != VERSION:
        raise ValueError('Scoring version mismatch')
    compatibility = compare(base['source'], candidate['source'], change=change)
    if compatibility['decision'] in ('incomparable', 'incomplete'):
        return compatibility
    if base.get('evaluator') != candidate.get('evaluator'):
        raise ValueError('Use the same reviewer protocol for paired semantic scores')
    a = {r['key']:r for r in base['observations']}
    b = {r['key']:r for r in candidate['observations']}
    pairs, groups = [], defaultdict(list)
    for key in sorted(a.keys() | b.keys()):
        left, right = a.get(key), b.get(key)
        for name in sorted(set((left or {}).get('metrics', {})) | set((right or {}).get('metrics', {}))):
            x = (left or {}).get('metrics', {}).get(name)
            y = (right or {}).get('metrics', {}).get(name)
            source = left or right
            valid = x and y and x['value'] is not None and y['value'] is not None
            if x and y and (x['unit'],x['direction']) != (y['unit'],y['direction']):
                raise ValueError('Metric definition mismatch')
            delta = y['value']-x['value'] if valid else None
            direction = (x or y)['direction']
            improvement = delta * (1 if direction=='higher' else -1) if valid and direction!='neutral' else None
            pair = dict(key=key, case=source['case'], category=source['category'], metric=name,
                        baseline=x['value'] if x else None, candidate=y['value'] if y else None,
                        delta=delta, improvement=improvement, unit=(x or y)['unit'])
            pairs.append(pair)
            groups[(source['category'],name)].append(pair)
    summary = []
    for (category,name), rows in sorted(groups.items()):
        valid = [r for r in rows if r['delta'] is not None]
        by_case = defaultdict(list)
        for r in valid:
            by_case[r['case']].append(r)
        means = {field: (sum(sum(r[field] for r in rs)/len(rs) for rs in by_case.values())/len(by_case)
                         if by_case else None) for field in ('baseline','candidate','delta')}
        summary.append(dict(category=category, metric=name, **means, paired=len(valid),
                            missing=len(rows)-len(valid), cases=len(by_case),
                            improved=sum(r['improvement'] is not None and r['improvement']>0 for r in valid),
                            worsened=sum(r['improvement'] is not None and r['improvement']<0 for r in valid)))
    return dict(version=VERSION, decision=compatibility['decision'], summary=summary, pairs=pairs,
                note='Macro averages by case; semantic gaps remain missing. No overall quality score.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('score','compare'))
    for name in ('report','suite','reviews','baseline','candidate','output'):
        p.add_argument('--'+name, type=Path, required=name=='output')
    p.add_argument('--change', choices=('weights','prompt'), default='weights')
    a=p.parse_args()
    read=lambda path: json.loads(path.read_text(encoding='utf-8'))
    if a.output.exists():
        p.error('Output directory must be new')
    if a.mode=='score':
        if not a.report or not a.suite:
            p.error('score requires report and original suite')
        report=read(a.report)
        if report.get('suite_sha256') != hashlib.sha256(a.suite.read_bytes()).hexdigest():
            p.error('Suite differs from measured suite')
        result, template=score_report(report,read(a.suite),read(a.reviews) if a.reviews else None)
    else:
        if not a.baseline or not a.candidate:
            p.error('compare requires baseline and candidate scored reports')
        result=compare_scores(read(a.baseline),read(a.candidate),a.change)
    a.output.mkdir(parents=True)
    (a.output/'progress.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if a.mode=='score':
        (a.output/'review-template.json').write_text(json.dumps(template,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result.get('summary', {'observations':len(result.get('observations',[]))}),ensure_ascii=False))


if __name__=='__main__':
    main()
