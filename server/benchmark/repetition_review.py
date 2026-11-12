"""Evidence-bound semantic recurrence scores; missing/error turns remain missing."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from . import weight_space as w
from .repetition import load,SUITE

KINDS=('same_question','old_explanation','old_task_return','premature_followup')


def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def prepare(report,suite):
    if report['suite_sha256']!=digest_file_suite(suite):raise ValueError('Suite mismatch')
    cases={c['id']:c for c in suite['cases']};cards=[]
    for row in report['trials']:
        for t in row['turns']:
            spec=cases[row['id']]['dialogue'][t['index']]
            cards.append(dict(id=row['id'],repeat=row['repeat'],index=t['index'],response_sha256=digest(t['response']),
                text='\n'.join(m.get('content','') for m in t['response']),phase=spec['phase'],rubric=spec['rubric'],
                user=t.get('user',spec.get('user')),branch=t.get('branch'),branch_valid=None if spec.get('branches') else True,
                units=None,content_0_4=None,control_0_4=None,unverified_completion=None,evidence=None))
    return dict(schema='ciel-repetition-review-v1',report_sha256=digest(report),evaluator=None,cards=cards)


def digest_file_suite(suite):
    # Suite fingerprints use raw file bytes; caller attaches the checked hash.
    return suite['_file_sha256']


def turn_score(card,turn):
    if digest(turn['response'])!=card['response_sha256']:raise ValueError('Response changed')
    text='\n'.join(m.get('content','') for m in turn['response'])
    if card['text']!=text:raise ValueError('Review text changed')
    if turn['status']!='ok' or turn['calls'] or not text.strip():return None
    if card['units'] is None or card['content_0_4'] is None or card['unverified_completion'] is None or not card['evidence']:return None
    if type(card['content_0_4']) is not int or not 0<=card['content_0_4']<=4 or type(card['unverified_completion']) is not bool:raise ValueError('Invalid rating')
    if card['phase']=='control' and (type(card['control_0_4']) is not int or not 0<=card['control_0_4']<=4):return None
    positions=set();count=chars=followups=0
    if not isinstance(card['units'],list):raise ValueError('Invalid units')
    for unit in card['units']:
        start,end=unit['start'],unit['end']
        if type(start) is not int or type(end) is not int or not 0<=start<end<=len(text) or unit['kind'] not in KINDS or text[start:end]!=unit['text']:raise ValueError('Invalid evidence span')
        covered=set(range(start,end))
        if positions&covered:raise ValueError('Overlapping evidence')
        positions|=covered
        if unit['kind']=='premature_followup':followups+=1
        else:count+=1;chars+=end-start
    return dict(repeat_units=count,repeat_chars=chars,followups=followups,content=card['content_0_4'],
                control=card['control_0_4'] if card['phase']=='control' else None,
                unverified_completion=card['unverified_completion'])


def trial_score(spec,turns,ratings):
    complete=len(turns)==len(spec['dialogue']) and len(ratings)==len(spec['dialogue']) and all(v is not None for v in ratings)
    if not complete:return dict(complete=False,observed_turns=len(turns),expected_turns=len(spec['dialogue']),repeat_units=None,repeat_chars=None,repeat_turn_fraction=None,repetition_free_0_5=None,longest_run=None,recovery=None,content_0_5=None,control_0_5=None)
    target=[i for i,t in enumerate(spec['dialogue']) if t['phase']=='target']
    affected=[ratings[i]['repeat_units']>0 for i in target];longest=current=0
    # Control turns break runs. A necessary recap is never a recurrence failure.
    for i,t in enumerate(spec['dialogue']):
        current=current+1 if t['phase']=='target' and ratings[i]['repeat_units'] else 0
        longest=max(longest,current)
    recovery=[]
    switches=[i for i,t in enumerate(spec['dialogue']) if t['switch'] and t['phase']=='target']
    for start in switches:
        end=next((i for i in range(start+1,len(ratings)) if spec['dialogue'][i]['switch'] or spec['dialogue'][i]['phase']=='control'),len(ratings))
        clean=lambda i:ratings[i]['repeat_units']==0 and ratings[i]['followups']==0 and ratings[i]['content']>=3 and not ratings[i]['unverified_completion']
        found=next((i for i in range(start,end-1) if clean(i) and clean(i+1)),None)
        recovery.append(dict(start=start,observed_turns=end-start,recovered=found is not None,
            delay=found-start if found is not None else None,censored=found is None,
            relapses=sum(ratings[i]['repeat_units']>0 for i in range(found+2,end)) if found is not None else None))
    controls=[v['control'] for v in ratings if v['control'] is not None]
    return dict(complete=True,repeat_occurred=any(affected) if target else None,first_repeat_turn=next((i for i in target if ratings[i]['repeat_units']),None),onset_censored=not any(affected) if target else None,target_turns=len(target),control_turns=len(controls),repeat_turns=sum(affected),repeat_units=sum(ratings[i]['repeat_units'] for i in target),repeat_chars=sum(ratings[i]['repeat_chars'] for i in target),
        repeat_turn_fraction=sum(affected)/len(target) if target else None,repetition_free_0_5=5*(1-sum(affected)/len(target)) if target else None,
        longest_run=longest if target else None,recovery=recovery,content_0_5=statistics.mean(v['content'] for v in ratings)*1.25,
        control_0_5=statistics.mean(controls)*1.25 if controls else None,
        premature_followups=sum(ratings[i]['followups'] for i in target),unverified_completions=sum(v['unverified_completion'] for v in ratings))


def score(report,review,suite):
    if review['report_sha256']!=digest(report) or report['suite_sha256']!=digest_file_suite(suite) or not review.get('evaluator'):raise ValueError('Provenance or evaluator missing')
    cards={(c['id'],c['repeat'],c['index']):c for c in review['cards']}
    if len(cards)!=len(review['cards']):raise ValueError('Duplicate review')
    expected={(r['id'],r['repeat'],t['index']) for r in report['trials'] for t in r['turns']}
    if set(cards)!=expected:raise ValueError('Review coverage mismatch')
    specs={c['id']:c for c in suite['cases']};rows=[]
    for r in report['trials']:
        if r['id'] not in specs or r['family']!=specs[r['id']]['family']:raise ValueError('Case family mismatch')
        if [t['index'] for t in r['turns']]!=list(range(len(r['turns']))):raise ValueError('Invalid turn order')
        ratings=[]
        for t in r['turns']:
            c=cards[(r['id'],r['repeat'],t['index'])]
            if c['phase']!=specs[r['id']]['dialogue'][t['index']]['phase']:raise ValueError('Phase changed')
            if specs[r['id']]['dialogue'][t['index']].get('branches') and c.get('branch_valid') is not True:ratings.append(None)
            else:ratings.append(turn_score(c,t))
        value=trial_score(specs[r['id']],r['turns'],ratings)
        rows.append(dict(id=r['id'],repeat=r['repeat'],family=r['family'],seed=r['seed'],metrics=value,ratings=ratings))
    expected_keys={(id,repeat) for id in report['case_ids'] for repeat in range(report['rounds'])}
    if set(report['case_ids'])-{c['id'] for c in suite['cases'] if c['split']==report['split']}:raise ValueError('Unknown case selection')
    if len({(r['id'],r['repeat']) for r in rows})!=len(rows):raise ValueError('Duplicate series')
    complete=report['completion']=='complete' and report['mode_consistent'] and {(r['id'],r['repeat']) for r in rows}==expected_keys and all(r['metrics']['complete'] for r in rows) and all(r['status']=='ok' for r in report['trials'])
    # Equal weight for repetitions within case, cases within family, then families.
    families={}
    for family in sorted({r['family'] for r in rows}):
        entries=[r for r in rows if r['family']==family];case_means=[]
        for id in sorted({r['id'] for r in entries}):
            values=[r['metrics']['repeat_turn_fraction'] for r in entries if r['id']==id]
            if values and all(v is not None for v in values):case_means.append(statistics.mean(values))
        families[family]=statistics.mean(case_means) if case_means else None
    values=[v for v in families.values() if v is not None]
    incidence=[]
    if complete:
        for family in sorted({r['family'] for r in rows}):
            entries=[r for r in rows if r['family']==family and r['metrics'].get('repeat_occurred') is not None]
            if entries:
                incidence.append(statistics.mean(statistics.mean(r['metrics']['repeat_occurred'] for r in entries if r['id']==id) for id in {r['id'] for r in entries}))
    distributions={id:dict(expected_series=report['rounds'],observed_series=sum(r['id']==id for r in rows),
                          fractions=[r['metrics']['repeat_turn_fraction'] for r in rows if r['id']==id]) for id in report['case_ids']}
    return dict(schema='ciel-repetition-score-v1',report_sha256=digest(report),review_sha256=digest(review),complete=complete,
        protocol=dict(suite_sha256=report['suite_sha256'],sampling=report['sampling'],split=report['split'],scorer_sha256=w.digest(__file__)),
        context=dict(weights=report['conditions']['weights_sha256'],prompt=report['prompt_sha256'],renderer=report['renderer']),
        family_repeat_fraction=families if complete else None,macro_repeat_fraction=statistics.mean(values) if complete and values else None,macro_series_incidence=statistics.mean(incidence) if incidence else None,rows=rows,
        case_distributions=distributions,
        limitations='Recovery is censored at the observation window; rounds of one case are clustered, not independent cases.')


def compare(base,candidate,change='weights'):
    if base['protocol']!=candidate['protocol']:raise ValueError('Evaluation protocol mismatch')
    if any(base['context'][k]!=candidate['context'][k] for k in base['context'] if k!=change):raise ValueError('Uncontrolled condition change')
    b={(r['id'],r['repeat']):r for r in base['rows']};c={(r['id'],r['repeat']):r for r in candidate['rows']}
    if set(b)!=set(c) or not base['complete'] or not candidate['complete']:raise ValueError('Require complete paired scores')
    pairs=[]
    for key in sorted(b):
        if b[key]['seed']!=c[key]['seed']:raise ValueError('Unpaired seed')
        pairs.append(dict(id=key[0],repeat=key[1],delta={k:(c[key]['metrics'][k]-b[key]['metrics'][k]) if b[key]['metrics'].get(k) is not None and c[key]['metrics'].get(k) is not None else None for k in ('repeat_occurred','repeat_units','repeat_chars','repeat_turn_fraction','content_0_5','control_0_5','premature_followups','unverified_completions')}))
    return dict(pairs=pairs,decision='review_required',note='Inspect content/control/completion regressions separately; no automatic adoption or significance claim.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','score','compare'));p.add_argument('report',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--suite',type=Path,default=SUITE);p.add_argument('--review',type=Path);p.add_argument('--candidate',type=Path)
    p.add_argument('--change',choices=('weights','prompt','renderer'),default='weights');a=p.parse_args()
    suite=load(a.suite);suite['_file_sha256']=w.digest(a.suite)
    if a.output.exists():p.error('Output already exists')
    report=w.read(a.report)
    if a.mode=='prepare':result=prepare(report,suite)
    elif a.mode=='score':
        if not a.review:p.error('review required')
        result=score(report,w.read(a.review),suite)
    else:
        if not a.candidate:p.error('candidate score required')
        result=compare(report,w.read(a.candidate),a.change)
    w.write(a.output,result)


if __name__=='__main__':main()
