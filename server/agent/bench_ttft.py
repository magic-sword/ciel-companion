# -*- coding: utf-8 -*-
"""心（全部の指示と道具）と小脳（短い指示・道具なし）で、文字のモデルが返事を書き始めるまでの秒数を比べる（mind.py）。

【料金がかかる】OpenAI を使う。既定（各 10 回）で約 0.02〜0.03 ドル。回す前に docs/paid-checks-ja.md を見る。
声・LiveKit の部屋は使わない。返事の作り方は会話サーバーと同じ（LiveKit の openai.LLM に、会話の指示・最近の発言・今回の発言を渡す）。

  python bench_ttft.py [--rounds 10] [--model gpt-5.4-mini] [--reasoning none]
"""
import argparse
import asyncio
import statistics
import time

from dotenv import load_dotenv
from livekit.agents import llm
from livekit.plugins import openai

import agent
import tools

load_dotenv()
HISTORY = [('user', 'ゆうき：昨日の夜、オリオン座の写真を撮ってみたんだ。'), ('assistant', '[happy]わあ、すてきなのです！'),
           ('user', 'ゆうき：寒かったけど、思ったよりきれいに撮れたよ。'), ('assistant', '[relaxed]がんばった甲斐がありましたね。')]
LINES = ['最近おすすめの本とかある？', 'シエルは何色が好き？', '明日は午前中に買い物に行って、午後は映画を見ようと思ってるんだ。']


def context(instructions: str, line: str) -> llm.ChatContext:
    ctx = llm.ChatContext()
    ctx.add_message(role='system', content=instructions)
    for role, text in HISTORY:
        ctx.add_message(role=role, content=text)
    ctx.add_message(role='system', content='[今：2026年10月30日（金）・朝・秋（日本時間）]')
    ctx.add_message(role='user', content=f'[発言者：ゆうき]\n{line}')
    return ctx


async def once(model: openai.LLM, ctx: llm.ChatContext, fns: list) -> tuple[float, float, str]:
    t0 = time.perf_counter()
    first, text = None, ''
    async with model.chat(chat_ctx=ctx, tools=fns) as stream:
        async for chunk in stream:
            piece = chunk.delta.content if chunk.delta is not None else None
            if piece:
                first = first or time.perf_counter() - t0
                text += piece
    return first or float('nan'), time.perf_counter() - t0, text


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=10)
    ap.add_argument('--model', default='gpt-5.4-mini')
    ap.add_argument('--reasoning', default='none')
    args = ap.parse_args()
    ciel = agent.Ciel()
    full = ciel.instructions_for('normal', 'solo')
    short = ciel.talker_instructions_for('normal', 'solo')
    model = openai.LLM(model=args.model, reasoning_effort=args.reasoning)
    print(f'指示：心 {len(full)} 字＋道具 {len(tools.TOOLS)} 個、小脳 {len(short)} 字・道具なし', flush=True)
    results = {'mind': [], 'talker': []}
    for n in range(args.rounds):
        line = LINES[n % len(LINES)]
        for name, instructions, fns in (('mind', full, tools.TOOLS), ('talker', short, [])):
            first, total, text = await once(model, context(instructions, line), fns)
            results[name].append((first, total))
            print(f'{name:6} 書き始め {first:.2f} 秒  書き終わり {total:.2f} 秒  {text[:40]}', flush=True)
    for name, rows in results.items():
        firsts = [f for f, _ in rows[1:]]   # 1 回目はキャッシュが無いので除く
        totals = [t for _, t in rows[1:]]
        print(f'SUMMARY {name}: 書き始め 中央値 {statistics.median(firsts):.2f} 秒（最大 {max(firsts):.2f}）'
              f'  書き終わり 中央値 {statistics.median(totals):.2f} 秒', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
