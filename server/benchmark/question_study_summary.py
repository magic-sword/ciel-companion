"""Aggregate speaker probes, excluding absent and ambiguously attributed targets."""
import argparse
import json
from pathlib import Path
from . import weight_space as w


def exclusion(trial):
    payload=json.loads(trial['input']['messages'][0]['content'])
    target=payload['target_question']
    if target is None:return 'no_target_question'
    roles={m['role'] for m in payload['messages'] if target in m.get('content','')}
    return 'ambiguous_multiple_speakers' if len(roles)!=1 else None


def summarize(report):
    out={}
    for arm in ('owner_probe','swapped_probe'):
        trials=[t for t in report['trials'] if t['arm']==arm]
        excluded=[dict(id=t['id'],repeat=t['repeat'],reason=exclusion(t)) for t in trials if exclusion(t)]
        eligible=[t for t in trials if not exclusion(t)];valid=[t for t in eligible if t['judgment']['valid']]
        out[arm]=dict(total=len(trials),eligible=len(eligible),scorable=len(valid),missing=len(eligible)-len(valid),excluded=excluded,
            all_correct=sum(t['judgment']['all_correct'] for t in valid),
            mean_score=sum(t['judgment']['field_score'] for t in valid)/len(valid) if valid else None,
            fields={k:sum(t['judgment']['fields'][k] for t in valid) for k in ('speaker','addressee','time')})
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    report=w.read(a.report)
    if report['completion']!='complete':raise ValueError('Incomplete run')
    result=dict(report_sha256=w.digest(a.report),summary=summarize(report))
    w.write(a.output,result);print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
