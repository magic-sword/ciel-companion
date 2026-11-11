#!/usr/bin/env python3
"""Export recorded G1/G2 input and replies for human review; never changes a grade."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('benchmark_home',Path(__file__).with_name('benchmark-home.py'))
home=importlib.util.module_from_spec(spec);spec.loader.exec_module(home)
from benchmark.stage1_intake import scenarios


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'server/benchmark/data')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();data=args.data.resolve();output=args.output or data/'stage1-human-review.txt'
    if output.exists():parser.error('Review output exists; refusing overwrite')
    g1=json.loads((data/'stage1-final-g1.json').read_text(encoding='utf-8'))
    g2=json.loads((data/'stage1-final-g2.json').read_text(encoding='utf-8'))
    name=g1['summary']['candidate']['matrix']
    roots=list(data.glob('home-import-*/results/'+name))
    if not roots:parser.error('Candidate G1 raw results are missing')
    root=max(roots,key=lambda p:p.stat().st_mtime)
    freeze=json.loads((root/'freeze.json').read_text())
    if home.provenance()['source_sha256']!=freeze['local_source_sha256']:
        parser.error('Local application differs from the frozen fixture source; use its archived source')
    fixtures=[c for c in scenarios()if c['split']=='development']+json.loads((root/'fresh-cases.json').read_text())
    by_id={c['id']:c for c in fixtures}
    lines=['段階1・人手レビュー用の記録','未採点。生成してもgate_complete/semantic_reviewは更新しません。',
           'G1は操作を記録する受付評価、G2は専用ワールドの実状態評価です。',
           '確認点：不足点の質問、否定・引用の非実行、範囲・材料・数量、完了と部分結果・停止理由の正確さ。','', 'G1：改修版48件']
    for row in g1['cases']['candidate']:
        case=by_id[row['id']];lines+=['',row['id']+' / '+row['split']+' / machine_passed='+str(row['passed'])]
        for index,text in enumerate(case['turns']):
            lines.append('入力'+str(index+1)+': '+text)
            reply=row['replies'][index]if index<len(row['replies'])else None
            lines.append('返答'+str(index+1)+': '+(reply or '通常会話へ引継ぎ'))
        lines.append('期待仕様: '+json.dumps(row.get('normalized_expected'),ensure_ascii=False,separators=(',',':')))
    lines+=['','G2：改修版の文字依頼42件']
    for row in g2['trials']:
        if row['variant']!='candidate'or row['mode']!='conversation':continue
        report=(data/row['source_report'].replace('\\','/')).resolve()
        if not report.is_relative_to(data):parser.error('Raw report path escapes the data directory')
        trace=report.parent/(row['task']+'-s'+str(row['seed'])+'-r'+str(row['repeat']))/'trace.jsonl'
        lines+=['',row['task']+' / '+row['condition']+' / '+row['source_matrix'],
                '実状態: '+row['status']+' / '+row['outcome']+' / '+row['reason']]
        seen=set()
        for line in trace.read_text(encoding='utf-8').splitlines():
            event=json.loads(line).get('event',{})
            if event.get('kind')=='item'and event.get('role')in('user','assistant'):
                identity=event.get('id')
                if identity and identity in seen:continue
                if identity:seen.add(identity)
                label='入力'if event['role']=='user'else '返答'
                lines.append(label+('（中断）'if event.get('interrupted')else '')+': '+event.get('text',''))
            if event.get('kind')=='game_call'and event.get('name')=='minecraft_prepare_region':
                lines.append('準備仕様: '+json.dumps(event['arguments'].get('spec'),ensure_ascii=False,separators=(',',':')))
    output.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Saved human review record:',output)


if __name__=='__main__':main()
