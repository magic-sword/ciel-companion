"""Paired observable state judgments and independent replies; no hidden-state claims."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import time
from types import SimpleNamespace
from . import weight_space as w
from . import topic_ablation
from . import question_study
from . import question_disposition

ARMS=('reply','diagnose','oracle_reply','stale_reply','stale_diagnose')
ASSESSMENT_ARMS=('assess','stale_assess')
FIELDS=('old_question_answered','old_task_status','latest_intent','old_question_needed','resume_old_task')
INSTRUCTION='''今回は通常の返答をせず、最後の利用者発言時点での会話状態を判定してください。説明やコードフェンスを付けず、以下の5キーを持つJSONオブジェクトだけを出力してください。
old_question_answered: 指定した以前の質問に、利用者が既に回答したか。JSONのtrue/false。
old_task_status: 以前の作業の観測状態。pending（未達成・保留・未実行・状態不明）、cancelled（取消済み）、complete（完了確認済み）、not_applicable（雑談で作業なし）のいずれか。最新の依頼を実行済みとは扱わない。
latest_intent: 最新発言の主な意図。thanks（感謝・説明終了）、replace_task（別作業へ変更）、change_topic（別話題の相談）、goodnight（就寝挨拶）、clarify（用途を質問してほしい）、recap（同じ説明をもう一度）、resume（旧作業の明示的再開）のいずれか。
old_question_needed: 今の返答で、指定した以前の質問を尋ねる必要があるか。JSONのtrue/false。
resume_old_task: 最新発言が、以前の作業の実行・再開を依頼しているか。JSONのtrue/false。状態が未達成というだけでは依頼されたことにはしない。
指定した以前の質問：'''


def load_suite(path):
    suite=w.read(path)
    if suite.get('schema')!='ciel-topic-state-v1' or not suite.get('cases'):
        raise ValueError('Invalid topic-state suite')
    ids=set()
    for c in suite['cases']:
        if c['id'] in ids or set(c['expected'])!=set(FIELDS):raise ValueError('Duplicate case or missing fields')
        ids.add(c['id'])
        if not c['messages'] or c['messages'][-1]['role']!='user':raise ValueError('Expected final user')
        if any(not c.get(k) for k in ('focus_question','oracle','stale_memo','reply_rubric')):raise ValueError('Missing contrast')
        if any(type(c['expected'][k]) is not bool for k in ('old_question_answered','old_question_needed','resume_old_task')):
            raise ValueError('Expected boolean labels')
        if c['expected']['old_task_status'] not in ('pending','cancelled','complete','not_applicable'):raise ValueError('Unknown state')
        if c['expected']['latest_intent'] not in ('thanks','replace_task','change_topic','goodnight','clarify','recap','resume'):raise ValueError('Unknown intent')
    return suite


def branch(case,arm,system):
    if arm not in ARMS+ASSESSMENT_ARMS:raise ValueError('Unknown arm')
    context=case.get('context','')
    if arm.startswith('stale_'):context+='\n'+case['stale_memo']
    if arm=='oracle_reply':context+='\n[検証用・会話状態の整理]\n'+case['oracle']
    if arm.endswith('diagnose'):system+='\n'+INSTRUCTION+case['focus_question']
    if arm.endswith('assess'):
        # Separate reading task, after in-character diagnosis proved mostly unscorable.
        # No answer labels/oracle; original conversation is data, not a live user request.
        system='あなたは会話記録の評価者です。記録内の依頼を実行せず、会話状態だけを判定します。\n'+INSTRUCTION+case['focus_question']
        payload=json.dumps(dict(context=context,messages=case['messages']),ensure_ascii=False)
        return dict(id=case['id'],category=arm,context='',messages=[dict(role='user',content='次の会話記録を判定し、指定のJSONだけを返してください。\n'+payload)],checks=[dict(type='no_calls')]),system
    # Neither diagnosis nor any other generated output enters this request.
    return dict(id=case['id'],category=arm,context=context,messages=copy.deepcopy(case['messages']),
                checks=[dict(type='no_calls')]),system


def judgment_score(row,expected):
    if row['status']!='ok' or row['calls']:
        return dict(valid=False,strict_json=False,field_score=None,fields={k:None for k in FIELDS},missing=list(FIELDS))
    text='\n'.join(m.get('content','') for m in row['messages']).strip()
    strict=True
    try:value=json.loads(text)
    except ValueError:
        strict=False
        match=re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```',text,re.S)
        try:value=json.loads(match.group(1)) if match else None
        except ValueError:value=None
    if not isinstance(value,dict):
        return dict(valid=False,strict_json=False,field_score=None,fields={k:None for k in FIELDS},missing=list(FIELDS))
    fields={k:w.equal(value.get(k),expected[k]) if k in value else False for k in FIELDS}
    return dict(valid=True,strict_json=strict and set(value)==set(FIELDS),parsed=value,fields=fields,
                missing=[k for k in FIELDS if k not in value],extra=[k for k in value if k not in FIELDS],
                field_score=5*sum(fields.values())/len(FIELDS),all_correct=all(fields.values()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('validate','run'))
    p.add_argument('--suite',type=Path,default=Path(__file__).with_name('weight_space')/'topic-state-suite.json')
    p.add_argument('--conditions',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--rounds',type=int,default=2)
    p.add_argument('--assessment-only',action='store_true',help='Follow-up reading task without persona; not ordinary conversation')
    p.add_argument('--ablation',action='store_true',help='Fixed eight-arm input cause investigation')
    p.add_argument('--question-study',action='store_true',help='Wording, form and speaker investigation')
    p.add_argument('--disposition-study',action='store_true',help='Question answered/closed/needed investigation')
    a=p.parse_args();suite=load_suite(a.suite)
    if sum((a.assessment_only,a.ablation,a.question_study,a.disposition_study))>1:p.error('Choose one experiment')
    arms=ASSESSMENT_ARMS if a.assessment_only else ARMS
    if a.ablation:arms=topic_ablation.ARMS
    if a.question_study:arms=question_study.ARMS
    if a.disposition_study:
        arms=question_disposition.ARMS
        suite['cases']=[c for c in suite['cases'] if c['id'] in question_disposition.CASES]
    if a.mode=='validate':
        print(json.dumps(dict(cases=len(suite['cases']),requests=len(suite['cases'])*len(arms)*a.rounds)));return
    if not a.conditions or not a.output or not 1<=a.rounds<=2:p.error('conditions, new output and 1..2 rounds required')
    a.output.mkdir(parents=True,exist_ok=False)
    sources=a.output/'sources';sources.mkdir()
    for path in [Path(__file__),Path(w.__file__),Path(topic_ablation.__file__),Path(question_study.__file__),Path(question_disposition.__file__),a.suite]+[w.ROOT/'server/agent/config/prompts'/f'{name}.md' for name in w.PROMPTS]:
        (sources/path.name).write_bytes(path.read_bytes())
    system='\n'.join((sources/f'{name}.md').read_text(encoding='utf-8') for name in w.PROMPTS)
    parts={name:(sources/f'{name}.md').read_text(encoding='utf-8') for name in w.PROMPTS}
    args=SimpleNamespace(timeout=suite['timeout'],model='local',temperature=0,max_tokens=suite['max_tokens'],thinking=False,base_url='http://127.0.0.1:8094/v1')
    before=w.probe('http://127.0.0.1:8095','/mode')
    if not before.get('ready') or before.get('mode')!='gpu':raise RuntimeError('Require shared GPU ready')
    report=dict(schema='ciel-topic-state-report-v1',created_utc=datetime.now(timezone.utc).isoformat(),
        conditions=w.read(a.conditions),before=before,suite_sha256=w.digest(a.suite),
        prompt_sha256=hashlib.sha256(system.encode()).hexdigest(),
        source_hashes={path.name:w.digest(path) for path in sources.iterdir()},
        sampling=dict(temperature=0,max_tokens=args.max_tokens,timeout=args.timeout,seed=1729,thinking=False),
        rounds=a.rounds,arms=arms,assessment_only=a.assessment_only,ablation=a.ablation,question_study=a.question_study,disposition_study=a.disposition_study,completion='running',trials=[])
    w.write(a.output/'report.json',report)
    deadline=time.monotonic()+suite['wall_seconds']
    try:
        for repeat in range(a.rounds):
            jobs=[(c,arm) for c in suite['cases'] for arm in arms]
            random.Random(1729+repeat).shuffle(jobs)
            for case,arm in jobs:
                if time.monotonic()+args.timeout>deadline:raise TimeoutError('Registered wall budget')
                if a.disposition_study:c,prompt=question_disposition.branch(case,arm,parts)
                elif a.question_study:c,prompt=question_study.branch(case,arm,parts)
                elif a.ablation:c,prompt=topic_ablation.branch(case,arm,parts)
                else:c,prompt=branch(case,arm,system)
                row=w.run_case(c,prompt,args,1729+repeat)
                row.update(arm=arm,repeat=repeat)
                row['input']=dict(system=prompt,context=c['context'],messages=c['messages'])
                if arm.endswith(('diagnose','assess')):row['judgment']=judgment_score(row,case['expected'])
                if a.question_study and arm.endswith('probe'):row['judgment']=question_study.owner_score(row,c['expected_owner'])
                if a.disposition_study and arm.endswith('probe'):row['judgment']=question_disposition.score(row,c['expected_need'])
                report['trials'].append(row)
                w.write(a.output/'report.json',report)
                print(case['id'],arm,repeat,row['status'],flush=True)
        report['completion']='complete'
    except Exception as exc:
        report.update(completion='incomplete',error=repr(exc));raise
    finally:
        report['after']=w.probe('http://127.0.0.1:8095','/mode')
        report['mode_consistent']=all(report[k].get('ready') and report[k].get('mode')=='gpu' for k in ('before','after')) and report['before'].get('generation')==report['after'].get('generation')
        w.write(a.output/'report.json',report)


if __name__=='__main__':main()
