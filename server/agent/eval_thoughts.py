# -*- coding: utf-8 -*-
"""内なる考えの質の評価（initiative.py）。決まった会話の場面を考える係に通し、できた考えを別のモデルに採点させる。

声の試験（bench_thoughts.py）は 1 回に数分かかり、毎回会話が違うので、考えの質を比べにくい。ここでは場面（SCENARIOS）を
固定し、相手が話すたびに（切れ端も含めて文字起こしのとおりに）考える係を呼んで、その時点の考えと知りたいことを、
審査のモデル（config/prompts/eval_thought_judge.md）に 1〜5 で採点させる。直す前と後で同じ場面を流して比べる。

観点：具体的か（specific）・今の話題に合うか（topical）・話す・聞く価値（value）・切れ端やあいさつに反応していないか
（grounded）・シエルらしさ（persona）、いちばん強い考えを今話したら良くなるか（top）、知りたいことの質（unknowns）。
OpenAI の API を使う（会話は合成。実在の人の会話は使わない）。開発用の会話サーバーのコンテナで動かす：

  docker exec ciel-dev-agent-dev-1 python eval_thoughts.py [--repeat 1] [--only 名前] > 結果.json

標準出力に場面ごとの考え・採点と平均を JSON で出す。標準エラーに要約を出す。
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from types import SimpleNamespace

import openai

from conversation import Conversation
import initiative
from persona import load_persona

JUDGE_MODEL = os.environ.get('CIEL_EVAL_JUDGE_MODEL', 'gpt-5.4')
JUDGE_PROMPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'prompts', 'eval_thought_judge.md')
U, C = 'user', 'assistant'

# 場面：(役, 発言)。相手の発言は、文字起こしで切れて届くとおりに分けて書く（「ねえ、シエル。」「昨日の夜、」…）。
# memories は、その人について前の会話から覚えていること（同意がある人だけ使える想定）
SCENARIOS = [
    {'name': 'stars_fragments', 'speaker': 'ハカセ', 'memories': [], 'turns': [
        (U, 'ねえ、シエル。'), (U, '昨日の夜、'), (U, '冬の星空を撮りに山の方まで行ってきたんだ。'),
        (C, 'わあ、冬の星空！山まで行くなんてすてきなのです。どんな星が見えましたか？'),
        (U, 'オリオン座がすごくきれいに撮れたよ。'), (U, 'でも、'), (U, '寒くて手がかじかんじゃった。'),
        (C, 'オリオン座、きれいに撮れたのですね！手がかじかむほど寒かったなんて、おつかれさまです。'),
        (U, '今度は流れ星も撮ってみたいんだよね。')]},
    {'name': 'greeting_then_topic', 'speaker': 'ミナ', 'memories': [], 'turns': [
        (U, 'こんにちは。'), (C, 'こんにちは！今日はどんな一日でしたか？'),
        (U, 'うーん、まあ普通かな。'), (U, 'あ、そういえば'), (U, '今日初めてパンを焼いてみたんだ。'),
        (C, 'パンを焼いたのですか！どんなパンですか？'),
        (U, 'シンプルな食パン。でも膨らみが足りなくて、ちょっと固くなっちゃった。')]},
    {'name': 'topic_shift', 'speaker': 'ハカセ', 'memories': [], 'turns': [
        (U, '最近カレーにはまってて、スパイスから作ってるんだ。'),
        (C, 'スパイスから！本格的なのです。どんなスパイスを使っていますか？'),
        (U, 'クミンとコリアンダーが中心かな。'),
        (C, 'いい香りがしそうなのです！'),
        (U, 'ところでさ、来週プレゼンがあって、ちょっと緊張してるんだよね。'),
        (C, 'プレゼン、緊張しますよね。どんな内容なのですか？'),
        (U, '新しいサービスの提案。上の人たちも来るんだ。')]},
    {'name': 'memory_recall', 'speaker': 'ハカセ',
     'memories': ['来月の初めにフルマラソンに出る予定', '前に右膝を痛めたことがある', '朝は 6 時に走っている'], 'turns': [
        (U, 'シエル、おはよう。'), (C, 'おはようございます、ハカセさん！'),
        (U, '今朝もちょっと走ってきたよ。'), (U, '10キロくらい。'),
        (C, '朝から 10 キロも！すごいのです。')]},
    {'name': 'tired_short', 'speaker': 'ミナ', 'memories': [], 'turns': [
        (U, 'ただいま。'), (C, 'おかえりなさい！今日はどうでしたか？'),
        (U, '疲れた。'), (C, 'おつかれさまです……ゆっくり休んでくださいね。'),
        (U, 'うん。'), (U, '残業で、ご飯もまだなんだ。')]},
    {'name': 'ai_trends', 'speaker': 'ハカセ', 'memories': ['AI の研究をしている'], 'turns': [
        (U, '最近の AI の動向で、気になってることがあってさ。'),
        (C, 'どんなことですか？気になるのです。'),
        (U, 'エージェントが自分でツールを使って作業するのが、だいぶ実用になってきたなって。'),
        (U, 'でも、'), (U, '勝手に動きすぎるのも怖いんだよね。')]},
]


def build(scenario, turns_so_far):
    h = Conversation()
    for role, text in turns_so_far:
        t = h.reserve(role=role)
        h.complete(t, text, label=scenario['speaker'])
    return h


async def run_scenario(scenario, persona, judge, judge_prompt):
    """相手が話すたびに考える係を呼び、その時点の考えを採点する"""
    style = SimpleNamespace(talk='chatty', presence='close')
    session = SimpleNamespace(generate_reply=lambda **k: None)
    memories = scenario['memories']
    talker = initiative.Initiative(session, style, persona.talk_chatty_nudge, instructions=persona.inner_thoughts_instructions,
                                   correction_nudge=persona.talk_correction_nudge,
                                   memories=(lambda: memories) if memories else None)
    checkpoints = []
    turns = scenario['turns']
    for i, (role, _) in enumerate(turns):
        if role != U:
            continue
        talker.history = build(scenario, turns[:i + 1])
        talker._last = time.monotonic()
        await talker._think(time.monotonic())
        thoughts = [t for t in talker.thoughts if not t.expressed]
        request = {'conversation': [{'speaker': scenario['speaker'] if r == U else 'シエル', 'text': x} for r, x in turns[:i + 1]],
                   **({'memories': memories} if memories else {}),
                   'thoughts': [{'text': t.text, 'kind': t.kind, 'motivation': t.motivation} for t in thoughts],
                   'unknowns': talker.unknowns}
        r = await judge.chat.completions.create(
            model=JUDGE_MODEL, reasoning_effort='medium', response_format={'type': 'json_object'},
            messages=[{'role': 'system', 'content': judge_prompt},
                      {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
        score = json.loads(r.choices[0].message.content or '{}')
        checkpoints.append({'after': turns[i][1], **request, 'score': score})
    return {'name': scenario['name'], 'checkpoints': checkpoints}


def summarize(results):
    keys = ('specific', 'topical', 'value', 'grounded', 'persona')
    per = {k: [] for k in keys}
    top, unknowns, bad, total = [], [], 0, 0
    for s in results:
        for c in s['checkpoints']:
            sc = c['score']
            for t in sc.get('thoughts') or []:
                total += 1
                vals = [t.get(k) for k in keys if isinstance(t.get(k), (int, float))]
                for k in keys:
                    if isinstance(t.get(k), (int, float)):
                        per[k].append(t[k])
                bad += any(v <= 2 for v in vals)
            if isinstance(sc.get('top'), (int, float)):
                top.append(sc['top'])
            if isinstance(sc.get('unknowns'), (int, float)):
                unknowns.append(sc['unknowns'])

    def mean(xs):
        return round(statistics.mean(xs), 2) if xs else None
    return {**{k: mean(v) for k, v in per.items()}, 'top': mean(top), 'unknowns': mean(unknowns),
            'thoughts': total, 'bad_ratio': round(bad / total, 2) if total else None}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repeat', type=int, default=1)
    ap.add_argument('--only', default='')
    args = ap.parse_args()
    persona = load_persona()
    judge = openai.AsyncOpenAI()
    judge_prompt = open(JUDGE_PROMPT, encoding='utf-8').read()
    scenarios = [s for s in SCENARIOS if not args.only or s['name'] == args.only]
    results = []
    for _ in range(args.repeat):
        results += await asyncio.gather(*(run_scenario(s, persona, judge, judge_prompt) for s in scenarios))
    summary = summarize(results)
    print(json.dumps({'summary': summary, 'results': results}, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)


if __name__ == '__main__':
    asyncio.run(main())
