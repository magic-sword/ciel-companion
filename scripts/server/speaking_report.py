#!/usr/bin/env python3
"""Who spoke up and what the mind wanted to say, from conversation debug logs (server/agent/debug_log.py).

  python scripts/server/speaking_report.py <room>.debug.jsonl [...] [--json out.json]

Stage 0 of docs/conversation/speaking-motivation-ja.md (the baseline): Ciel's lines that did not answer a
user line (she spoke up on her own), how many of them got an answer, lines cut off by the user, and the
inferences per user line. Stage 1: the ideas and scores the mind wrote (recall.MindRecall with
CIEL_MIND_IDEAS=1), with the score weighted by the output probabilities of 1-5. Stage 2 (CIEL_MIND_IDEAS=2):
the ideas put into the next reply, and how much of each the reply used (character bigrams of the idea that
the reply contains; read the pairs too, a reply can use an idea in other words). Stage 3 (CIEL_MIND_IDEAS=3):
the high ideas Ciel said at the open turn after her reply (speak_up.py), and why the others were dropped.
"""
import argparse
import collections
import json
import statistics
from pathlib import Path

ANSWER_S = 15.0   # a user line within this many seconds after Ciel spoke up counts as an answer
USED = 0.3        # share of the idea's bigrams found in the reply that counts as used


def bigrams(text):
    t = ''.join(ch for ch in text if ch.isalnum())
    return {t[i:i + 2] for i in range(len(t) - 1)}


def overlap(idea, reply):
    a = bigrams(idea)
    return len(a & bigrams(reply)) / len(a) if a else 0.0


def rows_of(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def baseline(rows):
    items, why = [], None
    for r in rows:   # the reason the mouth gave (mouth.py 'speak') belongs to the next line of Ciel's
        if r.get('kind') == 'speak':
            why = r.get('why')
        elif r.get('kind') == 'item' and r.get('role') in ('user', 'assistant') and r.get('text'):
            items.append({**r, 'why': why if r['role'] == 'assistant' else None})
            why = None
    user = [r for r in items if r['role'] == 'user']
    replies, own, greetings = [], [], []
    for i, r in enumerate(items):
        if r['role'] != 'assistant':
            continue
        if r['why'] in ('greeting', 'greeting_owner'):
            greetings.append(r)
        else:
            (own if i == 0 or items[i - 1]['role'] == 'assistant' else replies).append(r)
    answered = 0
    for r in own:
        after = next((x for x in items if x['t'] > r['t'] and x is not r), None)
        answered += int(after is not None and after['role'] == 'user' and after['t'] - r['t'] <= ANSWER_S)
    calls = collections.Counter()
    new_input = collections.Counter()
    for r in rows:
        if r.get('kind') == 'model_usage':
            role = r.get('role') or '?'
            calls[role] += 1
            new_input[role] += (r.get('input_tokens') or 0) - (r.get('cached_tokens') or 0)
        elif r.get('kind') == 'usage' and r.get('input_tokens') is not None:
            calls['reply'] += 1
            new_input['reply'] += r['input_tokens'] - (r.get('input_cached_tokens') or 0)
    background = sum(n for role, n in calls.items() if role not in ('reply', 'mind'))
    return {
        'user_lines': len(user), 'ciel_lines': len(replies) + len(own) + len(greetings), 'greetings': len(greetings),
        'spoke_up': len(own), 'spoke_up_why': dict(collections.Counter(r['why'] for r in own)),
        'spoke_up_answered': answered,
        'cut_off': sum(1 for r in items if r['role'] == 'assistant' and r.get('interrupted')),
        'interruptions': sum(1 for r in rows if r.get('kind') == 'interruption' and r.get('decision') == 'confirmed'),
        'speak_why': dict(collections.Counter(r.get('why') for r in rows if r.get('kind') == 'speak')),
        'calls': dict(calls), 'new_input': dict(new_input),
        'background_calls_per_user_line': round(background / len(user), 2) if user else None,
    }


def ideas(rows):
    runs = [r for r in rows if r.get('kind') == 'mind_ideas']
    all_ideas = [i for r in runs for i in r.get('ideas') or []]
    weighted = [i['weighted'] for i in all_ideas if isinstance(i.get('weighted'), (int, float))]
    return {
        'runs': len(runs), 'runs_without_candidates': sum(1 for r in runs if not r.get('candidates')),
        'runs_with_ideas': sum(1 for r in runs if r.get('ideas')), 'ideas': len(all_ideas),
        'ms_median': statistics.median([r['ms'] for r in runs]) if runs else None,
        'ms_max': max((r['ms'] for r in runs), default=None),
        'output_tokens_median': statistics.median(x) if (x := [r['output_tokens'] for r in runs
                                                              if r.get('output_tokens')]) else None,
        'kinds': dict(collections.Counter(i.get('kind') for i in all_ideas)),
        'scores': dict(sorted(collections.Counter(i.get('score') for i in all_ideas).items())),
        # weighted scores in half-point bins: shows whether they still pile up at 3
        'weighted_bins': dict(sorted(collections.Counter(min(5.0, int(w * 2) / 2) for w in weighted).items())),
        'weighted_distinct': len({round(w, 1) for w in weighted}),
        'samples': [{'turn': r.get('turn'), **i} for r in runs for i in r.get('ideas') or []],
    }


def placed(rows):
    replies = [r for r in rows if r.get('kind') == 'item' and r.get('role') == 'assistant' and r.get('text')]
    pairs = []
    for r in rows:
        if r.get('kind') == 'recall_turn' and r.get('idea'):
            reply = next((x for x in replies if x['t'] > r['t']), None)
            text = reply['text'] if reply else ''
            pairs.append({'idea': r['idea'], 'kind': r.get('idea_kind'), 'level': r.get('idea_level'),
                          'age_s': r.get('idea_age_s'), 'reply': text, 'overlap': round(overlap(r['idea'], text), 2)})
    turns = sum(1 for r in rows if r.get('kind') == 'recall_turn')
    return {'replies_checked': turns, 'placed': len(pairs), 'used': sum(1 for x in pairs if x['overlap'] >= USED),
            'pairs': pairs}


def spoke(rows):
    ups = [r for r in rows if r.get('kind') == 'speak_up']
    said = [r for r in ups if r.get('status') == 'spoken']
    return {'statuses': dict(collections.Counter(
                f"{r.get('status')}:{r['reason']}" if r.get('reason') else r.get('status') for r in ups)),
            'after_reply_s': [r.get('after_reply_s') for r in said],
            'generate_s': [r.get('generate_s') for r in ups if r.get('generate_s') is not None],
            'scheduled': [{k: r.get(k) for k in ('level', 'idea_kind', 'text', 'overlap', 'reply_playing', 'reply')}
                          for r in ups if r.get('status') == 'scheduled'],
            'dropped': [{k: r.get(k) for k in ('reason', 'level', 'text', 'overlap')}
                        for r in ups if r.get('status') == 'dropped']}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('logs', nargs='+')
    ap.add_argument('--json')
    a = ap.parse_args()
    out = {}
    for path in a.logs:
        rows = rows_of(path)
        out[Path(path).name] = {'baseline': baseline(rows), 'ideas': ideas(rows), 'placed': placed(rows),
                                'spoke': spoke(rows)}
        b, s = out[Path(path).name]['baseline'], out[Path(path).name]['ideas']
        print(f'== {Path(path).name}')
        print(f"  相手の発言 {b['user_lines']}  シエルの発言 {b['ciel_lines']}（あいさつ {b['greetings']}）  自分から {b['spoke_up']}"
              f"（{ANSWER_S:.0f}秒以内に答えが返った {b['spoke_up_answered']}）  遮られた {b['cut_off']}"
              f"  割り込みの確定 {b['interruptions']}")
        print(f"  推論の回数 {b['calls']}  新しい入力 {b['new_input']}  返事以外/相手の発言 {b['background_calls_per_user_line']}")
        if s['runs']:
            print(f"  心の考え：{s['runs']}回（候補なし {s['runs_without_candidates']}、考えあり {s['runs_with_ideas']}）"
                  f"  1回 中央値{s['ms_median']:.0f}ms 最大{s['ms_max']:.0f}ms  書き出し中央値 {s['output_tokens_median']}")
            print(f"  種類 {s['kinds']}  書いた点 {s['scores']}  重み付き(0.5刻み) {s['weighted_bins']}"
                  f"  重み付きの値の種類 {s['weighted_distinct']}")
            for i in s['samples']:
                w = f"{i['weighted']:.2f}" if isinstance(i.get('weighted'), (int, float)) else '-'
                print(f"    [{i['turn']}] {i['kind']:7} {i['score']} ({w}) {i['text']}  ← {i.get('about', '')}")
        q = out[Path(path).name]['placed']
        if q['placed']:
            print(f"  返事に置いた考え {q['placed']}/{q['replies_checked']}  返事が使った（2字組の重なり{USED:.0%}以上） {q['used']}")
            for x in q['pairs']:
                print(f"    {x['level']} {x['kind']:7} {x['overlap']:.2f} {x['idea']}\n      → {x['reply'][:90]}")
        u = out[Path(path).name]['spoke']
        if u['statuses']:
            print(f"  自分から話す：{u['statuses']}  返事を話し終えてから(s) {u['after_reply_s']}  作るのに(s) {u['generate_s']}")
            for x in u['scheduled']:
                print(f"    頼んだ {x['level']} {x['idea_kind']} 重なり{x['overlap']} 返事の声の間={x['reply_playing']} {x['text']}  ← 返事：{x.get('reply') or ''}")
            for x in u['dropped']:
                print(f"    落とした {x['reason']} {x['level']} 重なり{x['overlap']} {x['text']}")
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
