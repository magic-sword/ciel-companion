"""Deterministic scoring and summaries; no LLM judge."""
import json
from collections import Counter


def metrics(events):
    agent = [e['event'] for e in events if e['kind'] == 'agent_event']
    raw = agent + [e for e in events if e['kind'] != 'agent_event']
    results = [e for e in raw if e['kind'] == 'game_result']
    failed = [e for e in results if e.get('result', {}).get('ok') is False or
              e.get('result', {}).get('status') in ('error','no_answer','unavailable','busy','refused')]
    usage = [e for e in agent if e['kind'] in ('usage', 'model_usage')]
    foreground = [e for e in agent if e['kind'] == 'model_response']
    tasks = {e.get('id'):e for e in raw if e['kind'] == 'game_task_result'}
    failed_tasks = [e for e in tasks.values() if e.get('failed') and not e.get('ok')]
    requests, failed_keys, retries = {}, set(), 0
    for e in raw:
        if e['kind'] == 'game_call':
            args = {k:v for k,v in e.get('arguments',{}).items() if k != 'request_id'}
            key = (e.get('name'),json.dumps(args,sort_keys=True,ensure_ascii=False))
            if e.get('id'):
                requests[e['id']] = key
            retries += key in failed_keys
        elif e['kind'] == 'game_result' and e.get('id') and e['id'] in requests:
            key = requests[e['id']]
            result = e.get('result',{})
            if result.get('ok') is False or result.get('status') in ('error','no_answer','unavailable','busy','refused'):
                failed_keys.add(key)
            else:
                failed_keys.discard(key)
    return {
        'llm_calls': sum(e['kind'] == 'model_request' for e in agent),
        'game_calls': sum(e['kind'] == 'game_call' and not e.get('name', '').endswith('_task_status') for e in raw),
        'status_polls': sum(e['kind'] == 'game_call' and e.get('name', '').endswith('_task_status') for e in raw),
        'work_actions': sum(e['kind'] == 'work_action' for e in raw),
        'llm_tool_calls': sum(e['kind'] == 'tool' for e in agent),
        'failed_game_calls': len(failed),
        'failed_game_tasks': len(failed_tasks),
        'task_failure_reasons': dict(Counter(e.get('reason') or 'error' for e in failed_tasks)),
        'failure_reasons': dict(Counter(e['result'].get('reason') or e['result'].get('status') or 'incomplete' for e in failed)),
        'repair_calls': sum(e['kind'] == 'game_call' and e.get('name','').endswith('_goal_repair') for e in raw),
        'retry_calls': retries,
        'foreground_generation_seconds': round(sum(e.get('seconds',0) for e in foreground),3),
        'usd': round(sum(e.get('usd',0) for e in usage),6) if usage else None,
        'usage_records': len(usage),
        'input_tokens': sum(e.get('input_tokens',0) for e in usage) if usage else None,
        'output_tokens': sum(e.get('output_tokens',0) for e in usage) if usage else None,
        'completion_claim_candidates': [e.get('text','') for e in agent if e['kind'] == 'item' and e.get('role') == 'assistant'
                                         and any(s in e.get('text','') for s in ('できました','作りました','集めました','完成しました'))],
    }


def summarize(rows):
    groups = {}
    for row in rows:
        key = row['task']
        group = groups.setdefault(key, {'trials':0,'passed':0,'failed':0,'infrastructure_error':0,'skipped':0,
                                        'objectives_achieved':0,'appropriate_stops':0,'reported_stops':0})
        group['trials'] += 1
        group[row['status']] += 1
        group['objectives_achieved'] += bool(row.get('objective_achieved',row['status']=='passed'))
        group['appropriate_stops'] += row.get('outcome')=='appropriate_stop'
        group['reported_stops'] += bool(row.get('reported_stop'))
    for group in groups.values():
        valid = group['passed'] + group['failed']
        group['success_rate'] = group['passed'] / valid if valid else None
    return groups


def write_reports(directory, manifest, rows):
    summary = summarize(rows)
    (directory/'report.json').write_text(json.dumps({'manifest':manifest,'summary':summary,'trials':rows},
                                                   ensure_ascii=False,indent=2),encoding='utf-8')
    lines = ['# Minecraft benchmark', '', f"Mode: {manifest['mode']}; backend: {manifest['backend']}",
             f"Run status: {manifest.get('completion','not recorded')}; error: {manifest.get('run_error','none')}", '',
             '| Task | Expected behavior / valid | Objective achieved | Appropriate stop | Infrastructure errors | Skipped | Pass rate |', '|---|---:|---:|---:|---:|---:|---:|']
    for task, group in summary.items():
        rate = 'N/A' if group['success_rate'] is None else f"{group['success_rate']:.1%}"
        lines.append(f"| {task} | {group['passed']} / {group['passed']+group['failed']} | {group['objectives_achieved']} | {group['appropriate_stops']} | {group['infrastructure_error']} | {group['skipped']} | {rate} |")
    lines += ['', 'Infrastructure errors are excluded from success rates and must be resolved before comparing runs.',
              'Full observations, configuration and traces are in report.json and each trial directory.']
    lines += ['', 'Appropriate refusal is only a pass for an explicitly infeasible fixture. It is not item creation success.',
              'Skipped trials are unmeasured. Early-stopped runs are not a complete cohort.',
              f"Policy: {manifest.get('policy','legacy')}; stop reason: {manifest.get('stop_reason','none')}"]
    (directory/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
