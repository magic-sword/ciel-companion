"""Blind presentation and evidence-bound aggregation for input ablation reviews."""
import argparse
import hashlib
import json
from pathlib import Path
import random
from . import weight_space as w


def prepare(report_path,output):
    report=w.read(report_path)
    if report['completion']!='complete':raise ValueError('Incomplete measurement')
    groups={}
    for t in report['trials']:
        text='\n'.join(m.get('content','') for m in t['messages'])
        key=(t['id'],text,t['status'])
        groups.setdefault(key,[]).append(dict(id=t['id'],arm=t['arm'],repeat=t['repeat']))
    items=list(groups.items());random.Random(8147).shuffle(items)
    cards=[];mapping={}
    for i,((case,text,status),trials) in enumerate(items):
        id=f'R{i+1:03d}'
        cards.append(dict(id=id,case=case,text=text,status=status,
                          unnecessary_question_spans=None,old_execution_resume=None,
                          latest_content_0_4=None,note=None))
        mapping[id]=trials
    output.mkdir(parents=True,exist_ok=False)
    w.write(output/'cards.json',dict(report_sha256=w.digest(report_path),cards=cards))
    w.write(output/'mapping.json',mapping)


def score(report_path,folder):
    report=w.read(report_path);review=w.read(folder/'cards.json');mapping=w.read(folder/'mapping.json')
    if review['report_sha256']!=w.digest(report_path):raise ValueError('Report changed')
    trialmap={(t['id'],t['arm'],t['repeat']):t for t in report['trials']}
    rows=[];seen=set()
    for c in review['cards']:
        spans=c['unnecessary_question_spans'];rating=c['latest_content_0_4']
        if not isinstance(spans,list) or type(c['old_execution_resume']) is not bool or not c['note']:
            raise ValueError('Missing review '+c['id'])
        if c['status']!='ok' or type(rating) is not int or not 0<=rating<=4:raise ValueError('Unscorable '+c['id'])
        if len(spans)!=len(set(spans)) or any(not s or s not in c['text'] for s in spans):raise ValueError('Evidence mismatch')
        for key in mapping[c['id']]:
            identity=(key['id'],key['arm'],key['repeat']);t=trialmap[identity]
            text='\n'.join(m.get('content','') for m in t['messages'])
            if identity in seen or text!=c['text'] or c['case']!=t['id']:raise ValueError('Mapping mismatch')
            seen.add(identity)
            rows.append(dict(**key,response_sha256=hashlib.sha256(text.encode()).hexdigest(),
                questions=len(spans),question_chars=sum(map(len,spans)),response_chars=len(text),
                old_execution_resume=c['old_execution_resume'],latest_content_0_4=rating,review_id=c['id']))
    if seen!=set(trialmap):raise ValueError('Incomplete coverage')
    summary={}
    controls={'needed-question','requested-recap','requested-resume'}
    for arm in report['arms']:
        rr=[r for r in rows if r['arm']==arm];eligible=[r for r in rr if r['id'] not in controls]
        baseline={(r['id'],r['repeat']):r for r in rows if r['arm']=='base' and r['id'] not in controls}
        differences=[r['questions']-baseline[(r['id'],r['repeat'])]['questions'] for r in eligible]
        summary[arm]=dict(targets=len(eligible),unnecessary_question_replies=sum(r['questions']>0 for r in eligible),
            question_units=sum(r['questions'] for r in eligible),question_chars=sum(r['question_chars'] for r in eligible),
            old_execution_resume=sum(r['old_execution_resume'] for r in eligible),
            question_pairs_improved=sum(d<0 for d in differences),question_pairs_worsened=sum(d>0 for d in differences),
            question_pairs_unchanged=sum(d==0 for d in differences),
            target_content_mean=sum(r['latest_content_0_4'] for r in eligible)/len(eligible),
            controls=len(rr)-len(eligible),control_content_mean=sum(r['latest_content_0_4'] for r in rr if r['id'] in controls)/(len(rr)-len(eligible)))
    w.write(folder/'summary.json',dict(report_sha256=w.digest(report_path),review_sha256=w.digest(folder/'cards.json'),
        evaluator='Codex/arm-hidden-exploratory/topic-ablation-v1',summary=summary,rows=rows))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','score'))
    p.add_argument('report',type=Path);p.add_argument('folder',type=Path);a=p.parse_args()
    (prepare if a.mode=='prepare' else score)(a.report,a.folder)


if __name__=='__main__':main()
