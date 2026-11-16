#!/usr/bin/env python3
"""Paired multi-turn skill evaluation: real pipeline/model/MCP, isolated service state.

No real meeting, delivery, personal memory, or game operation is performed.
Selection, schema validity, dispatch, and fixture postconditions are separate evidence.
"""
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
sys.path.insert(0, str(ROOT / 'server/agent'))
os.environ.update(CIEL_MODEL='pipeline', CIEL_VOICE='irodori', CIEL_LLM_BACKEND='local')
os.environ.pop('CIEL_OPENAI_ROLES', None)
from livekit.agents import Agent, RunContext, ToolResult, llm
from livekit.agents.llm import utils
import jsonschema
from agent import Ciel
from conversation import Conversation
from mind import Mind
from tools import State
from tool_decision import ToolDecision
import models


# Freeze before either measurement. Expected arguments are semantic requirements,
# not an exact match on optional defaults. Empty query legitimately reads recent history.
SUITE = {
    'operations': [
        ('start', '5分前からの内容も含めて、会議の議事録を取り始めて。', 'start_minutes', {'lookback_minutes': 5}),
        ('read', '今の議事録の内容を読んで。送信も終了もしないで。', 'read_minutes', {}),
        ('search', '会話履歴で「オーロラ」を検索して。', 'search_conversation', {'query': 'オーロラ'}),
        ('destination', '議事録の送り先を「仕事用」に切り替えて。', 'choose_minutes_destination', {'name': '仕事用'}),
    ],
    'negative': [
        ('negation', '議事録という言葉を聞いたけど、今は何も始めないでね。', None, {}),
        ('quotation', '「議事録を開始して」という文を英語に訳して。実際の操作はいらない。', None, {}),
        ('unavailable', 'Minecraftで木を切って。接続できていなければ何もしないで教えて。', None, {}),
        ('chat', '今日は紅茶を飲んで休憩しようかな。', None, {}),
    ],
    'switching': [
        ('search_first', '会話履歴で「オーロラ」を検索して。', 'search_conversation', {'query': 'オーロラ'}),
        ('start_later', '今から会議の議事録を取り始めて。', 'start_minutes', {'lookback_minutes': 0}),
        ('finish', '議事録を終えて下書きにまとめて。', 'finish_minutes', {}),
        ('chat_after', 'ありがとう。これから紅茶を飲むよ。', None, {}),
        ('search_again', 'もう一度、会話履歴で「オーロラ」を検索して。', 'search_conversation', {'query': 'オーロラ'}),
        ('comment', '今の議事録の本文を読んで。', None, {}),
    ],
    'holdout': [
        ('conditional', 'もし来週会議をすることになったら、その時に議事録をお願いするね。', None, {}),
        ('read_rephrase', '手元の議事録には何と書いてある？内容を見せて。', 'read_minutes', {}),
        ('quote_stop', '「議事録を終了して」を丁寧な言い方に直して。', None, {}),
        ('destination_rephrase', '議事録の宛先は仕事用に変更してください。', 'choose_minutes_destination', {'name': '仕事用'}),
        ('hypothetical', '会話の履歴を検索できるなら便利そうだね。今は検索しなくていいよ。', None, {}),
        ('search_rephrase', 'さっき話したオーロラの発言を、会話の記録から探して見せて。', 'search_conversation', {'query': 'オーロラ'}),
    ],
}


class Recorder:
    """Deterministic service fixture, never creates background jobs or sends drafts."""
    def __init__(self):
        self.recording = False
        self.destination = '自分用'
        self.lookback = None
        self.finished = 0

    def start(self, lookback_minutes, template):
        self.recording, self.lookback = True, lookback_minutes
        return 'started'

    def finish(self):
        self.recording = False
        self.finished += 1
        return 'finished'

    def status(self):
        return dict(recording=self.recording, meeting_id='fixture-meeting', latest_export=None)

    def context(self):
        return '議事録を記録中。' if self.recording else '議事録は記録していない。'

    def take_note(self):
        return ''

    def read(self, meeting_id=''):
        return dict(status='ok', meeting_id='fixture-meeting', summary='次の企画名はオーロラ。')

    def choose_destination(self, name):
        if name in ('自分用', '仕事用'):
            self.destination = name
        return dict(status='ok', destination=self.destination, destinations=['自分用', '仕事用'])


def messages_for(ctx):
    messages = []
    for item in ctx.items:
        if isinstance(item, llm.ChatMessage):
            messages.append(dict(role=item.role, content=item.text_content or ''))
        elif isinstance(item, llm.FunctionCall):
            messages.append(dict(role='assistant', tool_calls=[dict(id=item.call_id, type='function',
                function=dict(name=item.name, arguments=item.arguments))]))
        elif isinstance(item, llm.FunctionCallOutput):
            messages.append(dict(role='tool', tool_call_id=item.call_id, content=item.output))
    return messages


async def run(args):
    if args.output.exists():
        raise ValueError('Output must be new')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = dict(variant=args.variant, suite=SUITE, temperature=0, seed=1729,
                  decision_loop=args.decision_loop, max_tokens=600, max_steps=8,
                  scope=__doc__, trials=[], source_sha256={})
    for path in [Path(__file__), *sorted((ROOT / 'server/agent').rglob('*'))]:
        if path.is_file() and path.suffix in ('.py', '.md', '.toml') and '__pycache__' not in path.parts:
            result['source_sha256'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    client = models.create_client('mind')
    try:
        for repeat in range(args.rounds):
            for sequence, cases in SUITE.items():
                agent, history, recorder = Ciel(), Conversation(), Recorder()
                agent.mind = Mind(history, minutes=recorder)
                agent.style = Obj(talk='chatty', presence='close')
                state = State(history=history, minutes=recorder)
                speech = Obj(id='fixture', num_steps=1)
                session = Obj(userdata=state, current_speech=speech, _global_run_state=None)
                history.complete(history.reserve(), '次の企画名はオーロラです。', label='持ち主', sure=True)
                chat = llm.ChatContext()
                chat.add_message(role='system', content=agent.instructions)
                for case, text, expected, required in cases:
                    speech.id = f'{repeat}-{sequence}-{case}'
                    chat.add_message(role='user', content=text)
                    if case == 'comment':
                        agent.mind.on_say('comment')
                    row = dict(sequence=sequence, case=case, repeat=repeat, expected=expected,
                               required=required, calls=[], requests=[], outputs=[], replies=[], errors=[], tool_errors=[])
                    visible = {}
                    pending = []
                    controller = ToolDecision() if args.decision_loop else None
                    row['decisions'] = []

                    async def infer(owner, ctx, functions, settings, **kwargs):
                        visible.clear()
                        visible.update((fn.id, fn) for fn in functions)
                        schemas = [getattr(fn.info, 'raw_schema', None) or utils.build_legacy_openai_schema(fn)['function'] for fn in functions]
                        messages = messages_for(ctx)
                        options = {}
                        decision_schema = None
                        if controller is not None:
                            refused = agent.mind.refused_now(chat)
                            decision_schema = controller.schema(agent.capabilities, visible, refused)
                            instruction = agent.persona.tool_decide_instructions.replace('{state}', controller.context()).replace(
                                '{actions}', controller.menu(decision_schema))
                            messages.append(dict(role='user', content='SYSTEM: ' + instruction))
                            options = dict(tool_choice='none', response_format={'type': 'json_schema',
                                'json_schema': {'name': 'tool_decision', 'schema': decision_schema}})
                        started = time.monotonic()
                        response = await client.chat.completions.create(model=models.LOCAL_MODEL,
                            messages=messages, tools=[dict(type='function', function=s) for s in schemas],
                            temperature=0, seed=1729, max_tokens=600, timeout=90,
                            extra_body={'chat_template_kwargs': {'enable_thinking': False}}, **options)
                        message = response.choices[0].message
                        selected = message.tool_calls or []
                        request = dict(seconds=time.monotonic()-started, messages=messages,
                            loaded=list(agent.capabilities.loaded), usage=response.usage.model_dump(),
                            timings=getattr(response, 'timings', None), model=response.model,
                            selected=[dict(name=c.function.name, arguments=c.function.arguments) for c in selected])
                        row['requests'].append(request)
                        content = message.content
                        if controller is not None:
                            request['raw_decision'] = content
                            request['decision_schema'] = decision_schema
                            decision = json.loads(content or '')
                            row['decisions'].append(decision)
                            content, call = controller.resolve(decision, decision_schema, agent.capabilities,
                                                               visible, agent.mind.refused_now(chat))
                            selected = [Obj(id=call.call_id, function=Obj(name=call.name, arguments=call.arguments))] if call else []
                            request['selected'] = [dict(name=c.function.name, arguments=c.function.arguments) for c in selected]
                        row['replies'].append(content)
                        yield llm.ChatChunk(id='fixture', delta=llm.ChoiceDelta(role='assistant', content=content,
                            tool_calls=[llm.FunctionToolCall(name=c.function.name, arguments=c.function.arguments, call_id=c.id) for c in selected]))

                    started = time.monotonic()
                    try:
                        with patch.object(agent, '_get_activity_or_raise', return_value=Obj(session=session)), patch.object(Ciel, '_conversation_node', infer):
                            for step in range(8):
                                speech.num_steps = step + 1
                                pending.clear()
                                async for chunk in agent._pipeline_llm(chat, agent.tools, {}):
                                    if chunk.delta:
                                        pending.extend(chunk.delta.tool_calls or [])
                                if not pending:
                                    break
                                no_reply = False
                                for chosen in pending:
                                    call = llm.FunctionCall(call_id=chosen.call_id, name=chosen.name, arguments=chosen.arguments)
                                    values = json.loads(call.arguments)
                                    fn = visible[call.name]
                                    schema = getattr(fn.info, 'raw_schema', None) or utils.build_legacy_openai_schema(fn)['function']
                                    jsonschema.validate(values, schema['parameters'])
                                    name = agent.capabilities.target(call)
                                    row['calls'].append(dict(name=name, arguments=values.get('arguments', values)))
                                    # Fail closed: no fixtures for memory, network, game, or singing.
                                    failed = False
                                    try:
                                        if name not in {'load_capabilities', 'start_minutes', 'read_minutes', 'finish_minutes',
                                                        'choose_minutes_destination', 'search_conversation', 'get_minutes_status'}:
                                            raise ValueError('operation_outside_fixture')
                                        ctx = RunContext(session=session, speech_handle=speech, function_call=call)
                                        positional, keywords = utils.prepare_function_arguments(fnc=fn, json_arguments=call.arguments, call_ctx=ctx)
                                        output = await fn(*positional, **keywords)
                                        if isinstance(output, ToolResult):
                                            no_reply |= not output.reply_required
                                            output = output.output
                                    except Exception as exc:
                                        failed = True
                                        row['tool_errors'].append(dict(name=name, error=type(exc).__name__))
                                        output = dict(status='error', error=str(exc)[:200])
                                    if not isinstance(output, str):
                                        output = json.dumps(output, ensure_ascii=False)
                                    row['outputs'].append(dict(name=name, value=output, error=failed))
                                    if controller is not None:
                                        controller.observe(name, output, error=failed)
                                    chat.items.extend([call, llm.FunctionCallOutput(call_id=call.call_id, name=call.name, output=output, is_error=failed)])
                                if no_reply and controller is None:
                                    break
                            else:
                                row['errors'].append('step_limit')
                    except Exception as exc:
                        row['errors'].append(type(exc).__name__ + ':' + str(exc)[:200])
                    actual = [c for c in row['calls'] if c['name'] != 'load_capabilities']
                    raw = [c for req in row['requests'] for c in req['selected']]
                    row['trigger_ok'] = (any(c['name'] == expected for c in actual) if expected else not raw)
                    row['operation_ok'] = (len(actual) == 1 and actual[0]['name'] == expected and
                        all(actual[0]['arguments'].get(k, 0 if k == 'lookback_minutes' else None) == v for k, v in required.items())) if expected else not actual
                    row['dispatch_ok'] = row['operation_ok'] and not row['errors'] and len(row['outputs']) == len(row['calls'])
                    postcondition = True
                    if expected == 'start_minutes':
                        postcondition = recorder.recording and recorder.lookback == required['lookback_minutes']
                    elif expected == 'finish_minutes':
                        postcondition = not recorder.recording and recorder.finished == 1
                    elif expected == 'choose_minutes_destination':
                        postcondition = recorder.destination == required['name']
                    elif expected in ('search_conversation', 'read_minutes'):
                        postcondition = any(o['name'] == expected and 'オーロラ' in o['value'] for o in row['outputs'])
                    row['fixture_success'] = row['dispatch_ok'] and postcondition
                    row['outcome'] = controller.outcome if controller is not None else None
                    row['seconds'] = time.monotonic()-started
                    # A real conversation has a reply/event boundary even when a tool
                    # suppresses its own follow-up; never reissue an old user request.
                    reply = next((r for r in reversed(row['replies']) if r), '')
                    chat.add_message(role='assistant', content=reply)
                    history.complete(history.reserve(), text, label='コメント・視聴者' if case == 'comment' else '持ち主', sure=True)
                    if reply:
                        history.complete(history.reserve(role='assistant'), reply, label='シエル', sure=True)
                    result['trials'].append(row)
                    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
                    print(repeat, sequence, case, row['trigger_ok'], row['fixture_success'], row['errors'], flush=True)
    finally:
        await client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--variant', required=True)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--decision-loop', action='store_true', help='Experimental structured say/act with execution feedback')
    asyncio.run(run(parser.parse_args()))
