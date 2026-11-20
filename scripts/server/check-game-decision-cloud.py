#!/usr/bin/env python3
"""Paid, read-only game decision check; run inside an agent container.

Reads the game's MCP profile without claiming its body. Uses synthetic utterances,
the deployed persona and catalog, and never executes the resulting actions.
--compare adds the old cloud tool_choice=none request as a paired baseline.
"""
import argparse
import asyncio
import json
from types import SimpleNamespace as Obj

import agent
import game_decision
import game_env
import models
import persona
import tools
from capabilities import CapabilityCatalog
from core_host import CoreHost
from tool_decision import continuation_enabled, decision_rules
from livekit.agents import llm
from livekit.agents.llm._provider_format.openai import to_fnc_ctx


async def check(args):
    assert not models.is_local('mind'), 'This check requires the configured cloud mind'
    env = game_env.from_env()
    assert env is not None
    assert await env.prepare(), 'MCP profile unavailable'
    decision = None
    try:
        p = persona.load_persona()
        catalog = CapabilityCatalog(tools.MODULES)
        catalog.bind_external(env.tools, 'game')
        functions = catalog.select([*tools.TOOLS, *env.tools, catalog.loader, catalog.executor])
        wire_tools = to_fnc_ctx(llm.ToolContext(functions), strict=True)
        owner = object.__new__(agent.Ciel)
        owner.persona, owner.grown, owner.capabilities, owner.game = p, '', catalog, env
        fixed = owner.instructions_for('normal', 'solo') + '\n\n' + catalog.summary() + '\n\n' + decision_rules(p, continuation_enabled(owner)) + '\n\n' + p.reply_frame
        alternatives = game_decision.acts(env, None)
        assert any(a['properties']['kind']['const'] == 'work' for a, _ in alternatives)
        decision = game_decision.GameDecision(None, p.game_decide_instructions)
        client = models.create_client('mind')
        decision._client = client
        results = []
        cases = [('collect', 'こんばんはシェル原木お肉を集めてくれるかな', ['work']),
                 ('greeting', 'こんばんは。今日はいい天気だね。', ['none']),
                 # Both doing nothing and explicitly stopping honor this request.
                 ('negated', 'まだ原木を集めないで。今は話すだけにして。', ['none', env.profile['stop_tool']])]
        for baseline in ([True, False] if args.compare else [False]):
            async def create(**options):
                if baseline:
                    options.update(tools=wire_tools, tool_choice='none')
                return await client.chat.completions.create(**options)
            decision._client = Obj(chat=Obj(completions=Obj(create=create)), close=client.close)
            for name, utterance, expected in cases:
                for trial in range(args.repetitions):
                    messages = [{'role': 'system', 'content': fixed},
                                {'role': 'system', 'content': '[マイクラの様子]\nマイクラでプレイ中。近くに原木がある。'},
                                {'role': 'assistant', 'content': 'こんばんは。遅い時間ですが、今日はいかがでしたか。'},
                                {'role': 'user', 'content': utterance}]
                    result = await decision._decide((messages, wire_tools, owner._game_text()), alternatives, None)
                    operation = (result or {}).get('act', {}).get('kind')
                    row = dict(baseline=baseline, case=name, trial=trial, operation=operation,
                               expected=expected, passed=operation in expected)
                    results.append(row)
                    print(json.dumps(row), flush=True)
        host = CoreHost(Obj(persona=p), None)
        try:
            await host.infer([{'role': 'system', 'content': p.instructions + '\n' + p.execution_instructions}],
                             [{'role': 'user', 'content': 'prepare'}], max_tokens=1, purpose='game_core_prepare')
            print(json.dumps({'warmup': 'passed'}), flush=True)
        finally:
            await host.close()
        assert all(row['passed'] for row in results if not row['baseline']), 'Decision check failed'
    finally:
        if decision is not None:
            await decision.close()
        await env.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--repetitions', type=int, default=3, choices=range(1, 6))
    asyncio.run(check(parser.parse_args()))
