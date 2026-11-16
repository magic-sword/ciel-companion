#!/usr/bin/env python3
"""Conditional annotation-prefix probabilities for plain and structured speech.

This probes the text field without a grammar. It is not an action-quality score.
"""
import argparse
import asyncio
import importlib.util
import json
import math
import os
from pathlib import Path
import time
import urllib.request

spec = importlib.util.spec_from_file_location('skill_benchmark', Path(__file__).with_name('benchmark-skill-lifecycle.py'))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

PREFIXES = ['うん、紅茶でひと息つこう。', 'あたたかい紅茶、いいね。', '今日はのんびり過ごそう。',
            'ちょっと休憩するのもいいね。', 'どんな紅茶を飲むの？', '香りを楽しみながら休もう。',
            'ミルクティーもおいしそうだね。', '一緒にゆっくりしよう。', 'お菓子もあると楽しそう。', 'ひと息ついたらまた話そう。']


def post(base, path, data):
    body = json.dumps(data, ensure_ascii=False).encode('utf8')
    with urllib.request.urlopen(urllib.request.Request(base + path, data=body,
        headers={'Content-Type': 'application/json'}), timeout=120) as response:
        return json.load(response)


def probabilities(response):
    entry = response['completion_probabilities'][0]
    values = entry.get('probs') or entry.get('top_logprobs')
    if not values:
        raise ValueError('No probability candidates returned')
    return [(p.get('tok_str', p.get('token', '')), p['prob'] if 'prob' in p else math.exp(p['logprob'])) for p in values]


async def prepare():
    agent, history, recorder = bench.Ciel(), bench.Conversation(), bench.Recorder()
    agent.mind = bench.Mind(history, minutes=recorder)
    agent.style = bench.Obj(talk='chatty', presence='close')
    session = bench.Obj(userdata=bench.State(history=history, minutes=recorder),
                        current_speech=bench.Obj(id='prefix-probe', num_steps=1), _global_run_state=None)
    chat = bench.llm.ChatContext()
    chat.add_message(role='system', content=agent.instructions)
    chat.add_message(role='user', content='今日は紅茶を飲んで休憩しようかな。')
    captured = {}

    async def capture(owner, ctx, functions, settings):
        schemas = [getattr(f.info, 'raw_schema', None) or bench.utils.build_legacy_openai_schema(f)['function'] for f in functions]
        captured.update(messages=bench.messages_for(ctx), tools=[dict(type='function', function=s) for s in schemas])
        controller = bench.ToolDecision()
        actions = controller.schema(agent.capabilities, {f.id: f for f in functions}, agent.mind.refused_now(chat))
        captured['instruction'] = agent.persona.tool_decide_instructions.replace('{state}', controller.context()).replace(
            '{actions}', controller.menu(actions))
        yield bench.llm.ChatChunk(id='capture', delta=bench.llm.ChoiceDelta(role='assistant', content=''))

    with bench.patch.object(agent, '_get_activity_or_raise', return_value=bench.Obj(session=session)), \
         bench.patch.object(bench.Agent.default, 'llm_node', capture):
        _ = [chunk async for chunk in agent._pipeline_llm(chat, agent.tools, {})]
    return captured


def main(args):
    if args.output.exists():
        raise ValueError('Output must be new')
    base = os.environ['CIEL_LOCAL_LLM_URL'].removesuffix('/v1').rstrip('/')
    request = asyncio.run(prepare())
    prefixes = PREFIXES[:args.limit]
    result = dict(scope=__doc__, prefixes=prefixes, requests=request, probes=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for variant in args.variants:
        messages = list(request['messages'])
        if variant == 'structured':
            messages.append(dict(role='user', content='SYSTEM: ' + request['instruction']))
        prompt = post(base, '/apply-template', dict(messages=messages, tools=request['tools'],
            tool_choice='none' if variant == 'structured' else 'auto',
            chat_template_kwargs={'enable_thinking': False}))['prompt']
        for index, prefix in enumerate(prefixes):
            suffix = '[neutral]' + prefix if variant == 'plain' else '{"say":[{"feeling":"neutral","text":"' + prefix
            text = prompt + suffix
            started = time.monotonic()
            options = dict(n_predict=1, n_probs=40, temperature=0, cache_prompt=False)
            response = post(base, '/completion', dict(prompt=text, **options))
            values = probabilities(response)
            chance = sum(p for token, p in values if token.lstrip().startswith(('（', '(', '※')))
            branches = []
            for token, weight in values:
                if token.strip() == '' and '\n' in token and weight > 0:
                    next_response = post(base, '/completion', dict(prompt=text + token, **options))
                    probability = sum(p for t, p in probabilities(next_response) if t.lstrip().startswith(('（', '(', '※')))
                    chance += weight * probability
                    branches.append(dict(token=token, weight=weight, probability=probability))
            result['probes'].append(dict(variant=variant, index=index, probability=chance,
                top_mass=sum(p for _, p in values), newline_branches=branches, raw=response,
                seconds=time.monotonic()-started))
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
            print(variant, index, chance, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, choices=range(1, 11), default=10)
    parser.add_argument('--variants', nargs='+', choices=['plain', 'structured'], default=['plain', 'structured'])
    main(parser.parse_args())
