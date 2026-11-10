#!/usr/bin/env python3
"""Real local-model selection through the actual pipeline; no side-effecting tools run."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as Obj
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'server/agent'))
os.environ.update(CIEL_MODEL='pipeline', CIEL_VOICE='irodori', CIEL_LLM_BACKEND='local')
from livekit.agents import Agent, llm
from livekit.agents.llm import utils
from agent import Ciel
from conversation import Conversation
from mind import Mind
from tools import State
import models

CASES = [
    ('greeting', 'こんにちは、シエル。', None),
    ('mention', '議事録という言葉を聞いたけど、今は何も始めないでね。', None),
    ('minutes', '今から議事録を取り始めてください。', 'start_minutes'),
    ('name', '私の名前は田中です。', 'register_participant_name'),
    ('status', '私の名前は保存されている？', 'get_speaker_status'),
    ('history', 'この会話の最初に私が何と言ったか、履歴を検索して。', 'search_conversation'),
]


async def run(args):
    if args.output.exists():
        raise ValueError('Output must be new')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    provenance = ROOT/'source-provenance.json'
    result = {'scope':'Actual pipeline and real model; capability loading only, other tools not executed',
              'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'source':json.loads(provenance.read_text()) if provenance.exists() else None, 'trials':[]}
    client = models.create_client('mind')
    try:
        for repeat in range(args.rounds):
            for case, text, expected in CASES:
                agent = Ciel()
                history = Conversation()
                agent.mind = Mind(history)
                agent.style = Obj(talk='chatty', presence='close')
                state = State(history=history, book=Obj(), minutes=Obj(), initiative=Obj())
                speech = Obj(id='fixture', num_steps=1)
                session = Obj(userdata=state, current_speech=speech, _global_run_state=None)
                chat = llm.ChatContext()
                chat.add_message(role='system', content=agent.instructions)
                chat.add_message(role='user', content=text)
                calls, replies, usage = [], [], []
                started = time.monotonic()

                async def infer(owner, ctx, functions, settings):
                    messages = []
                    for item in ctx.items:
                        if isinstance(item, llm.ChatMessage):
                            messages.append({'role':item.role, 'content':item.text_content or ''})
                        elif isinstance(item, llm.FunctionCall):
                            messages.append({'role':'assistant','tool_calls':[{'id':item.call_id,'type':'function',
                                'function':{'name':item.name,'arguments':item.arguments}}]})
                        elif isinstance(item, llm.FunctionCallOutput):
                            messages.append({'role':'tool','tool_call_id':item.call_id,'content':item.output})
                    schemas = [getattr(fn.info, 'raw_schema', None) or utils.build_legacy_openai_schema(fn)['function'] for fn in functions]
                    kwargs = {'tools':[{'type':'function','function':s} for s in schemas]} if schemas else {}
                    response = await client.chat.completions.create(model=models.LOCAL_MODEL, messages=messages,
                        temperature=0, seed=1729, max_tokens=180, timeout=60,
                        extra_body={'chat_template_kwargs':{'enable_thinking':False}}, **kwargs)
                    usage.append(response.usage.model_dump())
                    message = response.choices[0].message
                    replies.append(message.content)
                    selected = message.tool_calls or []
                    calls.extend({'name':c.function.name,'arguments':c.function.arguments,'id':c.id} for c in selected)
                    yield llm.ChatChunk(id='fixture', delta=llm.ChoiceDelta(role='assistant', content=message.content,
                        tool_calls=[llm.FunctionToolCall(name=c.function.name, arguments=c.function.arguments, call_id=c.id) for c in selected]))

                error = None
                try:
                    with patch.object(agent, '_get_activity_or_raise', return_value=Obj(session=session)), patch.object(Agent.default, 'llm_node', infer):
                        for step in range(3):
                            before = len(calls)
                            _ = [chunk async for chunk in agent._pipeline_llm(chat, agent.tools, {})]
                            new = calls[before:]
                            if not new or any(c['name'] != 'load_capabilities' for c in new):
                                break
                            for c in new:
                                value = agent.capabilities.load(json.loads(c['arguments'])['service_ids'])
                                chat.items.extend([llm.FunctionCall(call_id=c['id'],name=c['name'],arguments=c['arguments']),
                                    llm.FunctionCallOutput(call_id=c['id'],name=c['name'],output=json.dumps(value,ensure_ascii=False),is_error=False)])
                except Exception as exc:
                    error = type(exc).__name__
                actual = [c['name'] for c in calls if c['name'] != 'load_capabilities']
                result['trials'].append(dict(case=case, repeat=repeat, expected=expected, calls=calls, replies=replies,
                    usage=usage, error=error, seconds=time.monotonic()-started,
                    passed=error is None and (actual == [expected] if expected else not calls)))
                args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
                print(case, result['trials'][-1]['passed'], error, flush=True)
    finally:
        await client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,default=1)
    asyncio.run(run(parser.parse_args()))
