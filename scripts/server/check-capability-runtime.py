#!/usr/bin/env python3
"""Offline pipeline + MCP integration check. No model, DB or Minecraft is started."""
import asyncio
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server' / 'agent'))
os.environ['CIEL_MODEL'] = 'pipeline'
os.environ['CIEL_VOICE'] = 'irodori'

from livekit.agents import Agent, RunContext, llm  # noqa: E402
from livekit.agents.llm import utils  # noqa: E402
from agent import Ciel  # noqa: E402
from conversation import Conversation  # noqa: E402
from mind import Mind  # noqa: E402
from tools import State  # noqa: E402


def schema_chars(functions):
    def schema(fn):
        return getattr(fn.info, 'raw_schema', None) or utils.build_legacy_openai_schema(fn)['function']
    return sum(len(json.dumps(schema(fn), ensure_ascii=False)) for fn in functions)


async def main():
    agent = Ciel()
    history = Conversation()
    agent.mind = Mind(history)
    researcher = Obj(search=AsyncMock(return_value={'status': 'completed', 'summary': 'fixture', 'sources': []}))
    state = State(history=history, researcher=researcher)
    speech = Obj(id='fixture', num_steps=1)
    session = Obj(userdata=state, current_speech=speech, _global_run_state=None)
    chat = llm.ChatContext()
    chat.add_message(role='system', content=agent.instructions)
    chat.add_message(role='user', content='公式ページを調べて')
    original = chat.items[0].text_content
    captured = []

    async def model_stub(agent, ctx, functions, settings):
        captured.append((ctx, functions))
        if len(captured) == 1:
            name, arguments = 'load_capabilities', '{"service_ids":["4"]}'
        else:
            definition = agent.capabilities.definition('research_web')
            name, arguments = 'execute_capability', json.dumps({'tool_id':'research_web',
                'version':definition['version'],'arguments':{'question':'公式ページ'}},ensure_ascii=False)
        yield llm.ChatChunk(id='fixture', delta=llm.ChoiceDelta(role='assistant', tool_calls=[
            llm.FunctionToolCall(name=name, arguments=arguments, call_id=f'fixture-{len(captured)}')]))

    with patch.object(agent, '_get_activity_or_raise', return_value=Obj(session=session)), \
            patch.object(Agent.default, 'llm_node', model_stub), \
            patch('models.is_local', return_value=False), patch('models.LOCAL_TEST', False):
        outputs = [chunk async for chunk in agent._pipeline_llm(chat, agent.tools, {})]
        assert outputs[0].delta.tool_calls[0].name == 'load_capabilities'
        functions = {fn.id: fn for fn in captured[0][1]}
        assert 'research_web' not in functions
        call = llm.FunctionCall(call_id='fixture-1', name='load_capabilities', arguments='{"service_ids":["4"]}')
        ctx = RunContext(session=session, speech_handle=speech, function_call=call)
        args, kwargs = utils.prepare_function_arguments(fnc=functions[call.name], json_arguments=call.arguments, call_ctx=ctx)
        result = await functions[call.name](*args, **kwargs)
        chat.items.extend([call, llm.FunctionCallOutput(call_id=call.call_id, name=call.name, output=result, is_error=False)])
        outputs = [chunk async for chunk in agent._pipeline_llm(chat, agent.tools, {})]
        assert outputs[0].delta.tool_calls[0].name == 'execute_capability'
        functions = {fn.id: fn for fn in captured[1][1]}
        definition=agent.capabilities.definition('research_web')
        call = llm.FunctionCall(call_id='fixture-2', name='execute_capability', arguments=json.dumps({
            'tool_id':'research_web','version':definition['version'],'arguments':{'question':'公式ページ'}}))
        ctx = RunContext(session=session, speech_handle=speech, function_call=call)
        args, kwargs = utils.prepare_function_arguments(fnc=functions[call.name], json_arguments=call.arguments, call_ctx=ctx)
        result = await functions[call.name](*args, **kwargs)
        assert json.loads(result.output)['status'] == 'completed'
        researcher.search.assert_awaited_once_with('公式ページ', 'fixture-2', speech)
        assert chat.items[0].text_content == original
        assert agent.persona.research_voice_instructions not in captured[0][0].items[0].text_content
        assert agent.persona.research_voice_instructions not in captured[1][0].items[0].text_content
        assert captured[0][0].items[0].text_content == captured[1][0].items[0].text_content
        assert {f.id for f in captured[0][1]} == {f.id for f in captured[1][1]}

    print(json.dumps({
        'status': 'passed', 'mode': 'offline_scripted_selection',
        'scope': 'pipeline -> loader -> tool continuation -> real MCP -> host service',
        'all_registered_tools': len(agent.tools),
        'initial_tools': len(captured[0][1]), 'loaded_research_tools': len(captured[1][1]),
        'all_schema_chars': schema_chars(agent.tools),
        'initial_schema_chars': schema_chars(captured[0][1]),
        'loaded_research_schema_chars': schema_chars(captured[1][1]),
        'initial_instructions_chars': len(captured[0][0].items[0].text_content),
        'loaded_instructions_chars': len(captured[1][0].items[0].text_content),
        'live_model_evaluated': False,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
