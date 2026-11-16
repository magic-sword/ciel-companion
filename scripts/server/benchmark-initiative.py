#!/usr/bin/env python3
"""Baseline for autonomous decisions through the real pipeline, with simulated game operations."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'server/agent'))
os.environ.update(CIEL_MODEL='pipeline', CIEL_VOICE='irodori', CIEL_LLM_BACKEND='local', CIEL_OPENAI_ROLES='')
from livekit.agents import llm
from agent import Ciel
from conversation import Conversation
from game_decision import GameDecision
from initiative import Initiative
from mind import Mind
from tools import State
import models


async def run(args):
    if args.output.exists():
        raise ValueError('Output must be new')
    cases_path = ROOT/'server/benchmark/initiative_cases.json'
    cases = json.loads(cases_path.read_text(encoding='utf8'))
    report = {'scope': 'Real local model, actual pipeline; game operations simulated, no world writes',
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cases_sha256': hashlib.sha256(cases_path.read_bytes()).hexdigest(),
              'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((ROOT/'server/agent').rglob('*'))
                  if p.is_file() and p.suffix in ('.py', '.md', '.toml') and '__pycache__' not in p.parts},
              'trials': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    client = models.create_client('mind')
    try:
        for repeat in range(args.rounds):
            for case in cases:
                agent, history = Ciel(), Conversation()
                for role, text in case['history']:
                    history.complete(history.reserve(role=role), text)
                agent.mind = Mind(history)
                agent.style = Obj(talk='chatty', presence='solo')
                session = Obj(userdata=State(history=history), current_speech=Obj(id='fixture'),
                              user_state='listening', _global_run_state=None)
                requests = []
                async def create(**kwargs):
                    began = time.monotonic()
                    response = await client.chat.completions.create(**kwargs)
                    requests.append({'seconds': time.monotonic()-began, 'model': response.model,
                                     'usage': response.usage.model_dump(), 'timings': getattr(response, 'timings', None),
                                     'request': kwargs})
                    return response
                proxy = Obj(chat=Obj(completions=Obj(create=create)))
                runner = None
                if case.get('game'):
                    env = Obj(playing=lambda: True, _connection_epoch=1, tools=[], meta={},
                        profile={'work': {'version': 1, 'capabilities': [{'name': 'game.goal',
                            'handoff': {'version': 1, 'argument': 'request', 'constraints': {}, 'seconds': 120}}]}})
                    runner = Obj(env=env, work=case.get('work'), body_step=lambda: case.get('work'),
                                 start=AsyncMock(return_value={'status': 'accepted'}))
                decider = GameDecision(runner, agent.persona.initiative_instructions, client=proxy)
                agent.initiative = Initiative(history, Obj(session=session), decider,
                    agent.persona.initiative_instructions, agent.persona.initiative_trigger)
                agent.initiative._pending = (history.last_id-1, 0)
                agent.mind.on_say('initiative')
                chat = llm.ChatContext()
                chat.add_message(role='system', content=agent.instructions)
                chat.add_message(role='system', content=agent.persona.initiative_trigger)
                error, output = None, []
                began = time.monotonic()
                try:
                    with patch.object(agent, '_get_activity_or_raise', return_value=Obj(session=session)):
                        output = [chunk async for chunk in agent._pipeline_llm(chat, agent.tools, {})]
                except Exception as exc:
                    error = type(exc).__name__
                status = next((s for s in ('acted', 'spoken', 'silent', 'cancelled', 'failed')
                               if agent.initiative.counts[s]), 'missing')
                report['trials'].append({'case': case['id'], 'repeat': repeat, 'status': status, 'error': error,
                    'expected': case['expected'], 'passed': error is None and status in case['expected'],
                    'seconds': time.monotonic()-began, 'requests': requests, 'say': output,
                    'simulated_actions': runner.start.await_count if runner else 0})
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
                print(case['id'], status, report['trials'][-1]['passed'], error, flush=True)
    finally:
        await client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3)
    asyncio.run(run(parser.parse_args()))
