#!/usr/bin/env python3
"""Shared-local-model smoke of the production conversation decision adapter.

Only synthetic history search is executed; external operations are rejected.
Uses the real pipeline, structured inference, MCP and LiveKit result event types.
No microphone, TTS, personal database, or production conversation is opened.
"""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import time

spec = importlib.util.spec_from_file_location('lifecycle', Path(__file__).with_name('benchmark-skill-lifecycle.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
from livekit.agents.voice.events import FunctionToolsExecutedEvent


async def run(output):
    if output.exists():
        raise ValueError('Output must be new')
    cases = [('search', '会話履歴から「オーロラ」を検索して。', True),
             ('quotation', '「会話履歴を検索して」を英語に訳して。操作はしないで。', False),
             ('chat', '今日は紅茶で休憩しようかな。', False)]
    results = []
    for name, text, required in cases:
        agent, history = b.Ciel(), b.Conversation()
        agent.mind = b.Mind(history)
        agent.style = b.Obj(talk='chatty', presence='close')
        history.complete(history.reserve(), '次の企画名はオーロラです。', label='持ち主', sure=True)
        speech = b.Obj(id=name, num_steps=1, interrupted=False)
        session = b.Obj(userdata=b.State(history=history), current_speech=speech, _global_run_state=None)
        chat = b.llm.ChatContext()
        chat.add_message(role='system', content=agent.instructions)
        chat.add_message(role='user', content=text)
        row = dict(case=name, calls=[], outputs=[], replies=[], errors=[])
        started = time.monotonic()
        try:
            with b.patch.object(agent, '_get_activity_or_raise', return_value=b.Obj(session=session)):
                for _ in range(8):
                    chunks = [c async for c in agent._pipeline_llm(chat, agent.tools, {})]
                    calls = []
                    for chunk in chunks:
                        delta = chunk if isinstance(chunk, str) else chunk.delta
                        row['replies'].append(delta if isinstance(delta, str) else delta.content or '')
                        if not isinstance(delta, str):
                            calls.extend(delta.tool_calls or [])
                    if not calls:
                        break
                    for call in calls:
                        target = agent.capabilities.target(call)
                        if target not in ('load_capabilities', 'search_conversation'):
                            raise ValueError('operation_outside_fixture:' + target)
                        row['calls'].append(target)
                        fn = next(f for f in agent.capabilities.select(agent.tools) if f.id == call.name)
                        call = b.llm.FunctionCall(call_id=call.call_id, name=call.name, arguments=call.arguments)
                        ctx = b.RunContext(session=session, speech_handle=speech, function_call=call)
                        args, kwargs = b.utils.prepare_function_arguments(fnc=fn, json_arguments=call.arguments, call_ctx=ctx)
                        result = await fn(*args, **kwargs)
                        reply_required = True
                        if isinstance(result, b.ToolResult):
                            reply_required, result = result.reply_required, result.output
                        out = b.llm.FunctionCallOutput(call_id=call.call_id, name=call.name,
                            output=result if isinstance(result, str) else json.dumps(result, ensure_ascii=False),
                            is_error=False, reply_required=reply_required)
                        agent.conversation_decision.feedback(FunctionToolsExecutedEvent(
                            function_calls=[call], function_call_outputs=[out]))
                        row['outputs'].append(dict(tool=target, result=out.output))
                        chat.items.extend([call, out])
                else:
                    raise TimeoutError('step_limit')
        except Exception as exc:
            row['errors'].append(type(exc).__name__ + ':' + str(exc)[:200])
        row['seconds'] = time.monotonic() - started
        loop = getattr(getattr(agent, 'conversation_decision', None), 'loop', None)
        row['outcome'] = loop.outcome if loop else None
        found = any(o['tool'] == 'search_conversation' and any(m.get('id') == 1 for m in json.loads(o['result']).get('matches', [])) for o in row['outputs'])
        row['passed'] = not row['errors'] and (found if required else not row['calls']) and any(row['replies'])
        results.append(row)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(dict(scope=__doc__, model=b.models.model('mind'), trials=results), ensure_ascii=False, indent=2), encoding='utf8')
        print(name, row['passed'], row['calls'], row['outcome'], row['errors'], flush=True)
    if not all(r['passed'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(run(parser.parse_args().output))
