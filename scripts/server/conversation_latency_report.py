#!/usr/bin/env python3
"""Per-reply latency and prompt cache from one conversation's debug log (server/agent/debug_log.py).

  python scripts/server/conversation_latency_report.py .local/debug-logs-dev/<room>.jsonl [--json out.json]

For each assistant reply: who wrote it (mind/talker/decision), the time from the end of the owner's
speech to the first reply audio and the model's first token (LiveKit's item metrics), and the input,
cached and newly computed prompt tokens of the inference behind it. Background inferences
(thoughts, notes, ...) are counted apart, because they share the model with the replies.
"""
import argparse
import json
import statistics
from pathlib import Path


def report(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    replies, background, pending = [], {}, []
    route = None
    for r in rows:
        kind = r.get('kind')
        if kind == 'mind_route':
            route = r.get('why')
        elif kind == 'usage' and r.get('input_tokens') is not None:
            # The reply's streaming inference (LiveKit's usage of the conversation model).
            pending.append({'input_tokens': r['input_tokens'], 'cached_tokens': r.get('input_cached_tokens') or 0})
        elif kind == 'model_usage':
            if r.get('role') in ('mind',):
                pending.append(r)
            else:
                b = background.setdefault(r.get('role'), {'calls': 0, 'new_input': 0, 'output': 0})
                b['calls'] += 1
                b['new_input'] += r['input_tokens'] - r['cached_tokens']
                b['output'] += r['output_tokens']
        elif kind == 'item' and r.get('role') == 'assistant':
            m = r.get('metrics') or {}
            use = pending[-1] if pending else {}
            replies.append({'text': (r.get('text') or '')[:40], 'route': route,
                            'e2e': m.get('e2e_latency'), 'ttft': m.get('llm_node_ttft'),
                            'input': use.get('input_tokens'), 'cached': use.get('cached_tokens'),
                            'new': (use.get('input_tokens') or 0) - (use.get('cached_tokens') or 0) if use else None,
                            'inferences': len(pending)})
            pending, route = [], None

    def median(key):
        values = [x[key] for x in replies if isinstance(x.get(key), (int, float))]
        return round(statistics.median(values), 3) if values else None
    summary = {'replies': len(replies), 'median_e2e': median('e2e'), 'median_ttft': median('ttft'),
               'median_new_tokens': median('new'), 'median_cached_tokens': median('cached'),
               'no_cache': sum(1 for x in replies if x.get('cached') == 0), 'background': background}
    return {'summary': summary, 'replies': replies}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log', type=Path)
    p.add_argument('--json', type=Path)
    a = p.parse_args()
    out = report(a.log)
    for x in out['replies']:
        print(json.dumps(x, ensure_ascii=False))
    print(json.dumps(out['summary'], ensure_ascii=False))
    if a.json:
        a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
