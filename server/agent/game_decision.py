"""One decision per owner utterance while a game is played: what to say and what to do.

The conversation model reads the whole conversation and writes one structured output {say, act}.
`act` names one of the actions of the current work state (docs/conversation/agent-state-machine-ja.md):
  no work         a work capability, or one of the game's direct actions
  running work    words passed to the work, or stopping it
  waiting work    the answers the work's decision accepts
  ended work      as with no work, and starting the work that failed or was stopped again
Not acting is the kind `none`. `say` is what Ciel speaks, written as parts that each carry their
feeling (one of emotion.CAPTIONS), so every part reaches the face and the voice, also when the action could not be done or
a stop word already stopped the body: then a second decision that can only speak tells it in her words.

Starting, checking and stopping stay with the work runner and the game environment. Two things do
not wait for the model: a stop word stops the body as soon as it is heard (on_transcribed), and what
the owner pointed at is captured when the speech ends (on_user_state). An action aimed at a target
(pointed, or coordinates in the words) takes a target id; target_candidates binds the real value, the
model never writes it. Work is offered for a capability that takes the request as it is (a handoff).
The local model writes the decision under the schema; a cloud model is asked for the same schema and
its answer is checked against it.
"""
import asyncio
import copy
import json
import os
import re
import time
import uuid

import debug_log
import jsonschema
import emotion
import models
from mind import NOTE_PREFIX

STRING = {'type': 'string', 'minLength': 1, 'maxLength': 2000}
ACTIVE = ('accepted', 'running', 'needs_decision', 'cancelling')
ENDED = ('failed', 'cancelled')   # an ended work that may be started again with its own request
# Results that did not do what was chosen.
FAILED = ('error', 'unavailable', 'busy', 'goal_running', 'no_task', 'refused', 'failed')
NONE = {'type': 'object', 'additionalProperties': False, 'properties': {'kind': {'const': 'none'}}, 'required': ['kind']}
# Stop words stop the body when they are heard, before any model (a plain stop, nothing else in it).
STOP = re.compile(r'^(?:今の作業を)?(?:止まって|止めて|やめて|待って|中止して)(?:ください)?[。！!、\s]*'
                  r'(?:(?:その場で待ってください|こちらが頼むまで再開しないでください)[。\s、]*)*$')
REASONING = os.environ.get('CIEL_MIND_REASONING', 'none')   # a cloud mind's reasoning effort (agent.MIND_REASONING)


# 持ち主が止めた作業のあとは、自分から動かない（止めたのは持ち主の意思）。期限切れ・失敗のあとは続けてよい
SELF_STOPPED = ('deadline', 'execution_error')


def after_work(work) -> bool:
    """自分の決定で次の行動を始めてよいか：作業が無いか、終わったか（持ち主が止めたときを除く）"""
    if work is None:
        return True
    state = work.get('state')
    return state in ('succeeded', 'failed') or (state == 'cancelled' and work.get('reason') in SELF_STOPPED)


def capabilities(env):
    """Work capabilities the decision can start: those that take the request as it is."""
    work = env.profile.get('work') or {}
    if work.get('version') != 1:
        return []
    return [c for c in work.get('capabilities', []) if (c.get('handoff') or {}).get('version') == 1 and not c.get('preparation')]


def targeted(env, name) -> bool:
    """An action whose target comes from the owner's pointing or from coordinates in the words."""
    meta = getattr(env, 'meta', {}).get(name, {})
    return bool(meta.get('ciel/reference_argument') or meta.get('ciel/target_binding'))


def _act_tools(env):
    return [fn for fn in getattr(env, 'tools', []) if getattr(env, 'meta', {}).get(fn.id, {}).get('ciel/role') == 'act']


def bind_targets(env, text, references, request_id):
    """The targets of this utterance for the game's targeted actions, keyed by action name."""
    from target_candidates import TargetCandidates
    definitions = {}
    for fn in _act_tools(env):
        if targeted(env, fn.id):
            meta = env.meta[fn.id]
            params = copy.deepcopy(fn.info.raw_schema['parameters'])
            params['additionalProperties'] = False
            definitions[fn.id] = {'kind': 'tool', 'name': fn.id, 'arguments': params,
                                  'reference_argument': meta.get('ciel/reference_argument'),
                                  'target_binding': copy.deepcopy(meta.get('ciel/target_binding'))}
    return TargetCandidates(request_id, text, references, definitions)


def _alt(properties):
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}


def acts(env, work, targets=None):
    """The kinds a decision may take in this work state, as (schema alternative, line for the prompt).
    A targeted action is offered only when this utterance has its target (targets from bind_targets)."""
    out = [(NONE, 'none：話すだけ')]
    state = (work or {}).get('state')
    if state in ('accepted', 'running'):
        out += [(_alt({'kind': {'const': 'tell'}}),
                 'tell：今の作業へ相手の言葉を渡す（やり方・好み・続けてよいこと）。発言の原文は基盤が渡す'),
                (_alt({'kind': {'const': 'cancel'}}), 'cancel：今の作業を止める')]
    elif state == 'needs_decision':
        decision = work.get('decision') or {}
        for action in decision.get('actions') or ['retry', 'cancel']:
            if action == 'reply':
                out.append((_alt({'kind': {'const': 'reply'}}),
                            f"reply：作業からの質問（{decision.get('message', '')}）へ相手の答えを渡す。発言の原文は基盤が渡す"))
            elif action in ('retry', 'cancel'):
                out.append((_alt({'kind': {'const': action}}),
                            {'retry': 'retry：作業をもう一度試す', 'cancel': 'cancel：作業をやめる'}[action]))
    elif state not in ACTIVE:
        if state in ENDED and _handoff(env, work.get('capability')) and (work.get('arguments') or {}):
            request = json.dumps(work['arguments'], ensure_ascii=False)
            out.append((_alt({'kind': {'const': 'resume'}}),
                        f"resume：止まった作業（{request}）を、同じ依頼でもう一度始める。体は進んだ分を見て続きから計画する"))
        for capability in capabilities(env)[:1]:   # one work kind: a game declares one entry that takes the request
            out.append((_alt({'kind': {'const': 'work'}, 'request': STRING}),
                        # The name is how the game's own instructions refer to this capability.
                        f"work：{capability['name']}。{capability.get('description', '')} requestに相手の頼み"))
        for fn in _act_tools(env):
            description = fn.info.raw_schema.get('description', '')
            if targeted(env, fn.id):
                bound = (targets.definitions.get(fn.id) if targets is not None else None) or {}
                if not bound.get('target_ids'):
                    continue   # Nothing was pointed at or named for it in this utterance.
                out.append((_alt({'kind': {'const': fn.id}, 'arguments': bound['arguments']}),
                            f"{fn.id}：{description} 行き先はarguments.target_id"
                            f"（{json.dumps(targets.targets, ensure_ascii=False)}）"))
                continue
            params = copy.deepcopy(fn.info.raw_schema['parameters'])
            params['additionalProperties'] = False
            out.append((_alt({'kind': {'const': fn.id}, 'arguments': params}), f"{fn.id}：{description}"))
    if state in ('accepted', 'running', 'needs_decision') and capabilities(env):
        current = json.dumps(work.get('arguments') or {}, ensure_ascii=False)
        out.append((_alt({'kind': {'const': 'replace'}, 'request': STRING}),
                    f'replace：現在の目的は{current}。相手が別の最終成果を依頼・訂正したら、停止を確認してその目的へ切り替える。requestは新しい目的の全体'))
    return out


def _handoff(env, name):
    # The capability's declared handoff, or None.
    return next((c.get('handoff') for c in capabilities(env) if c.get('name') == name), None)


def instructions(template, alternatives):
    return template.replace('{actions}', '\n'.join('- ' + line for _, line in alternatives))


# What Ciel says: parts of her words, each with its feeling. The feeling becomes the face and the voice.
SAY = {'type': 'array', 'minItems': 1, 'maxItems': 6, 'items': {
    'type': 'object', 'additionalProperties': False, 'required': ['feeling', 'text'],
    'properties': {'feeling': {'enum': list(emotion.CAPTIONS)}, 'text': STRING}}}


def spoken(say) -> str:
    """The words to speak, each part led by its feeling as the voice pipeline reads it (emotion.py)."""
    parts = say if isinstance(say, list) else []
    return ''.join(f"[{p['feeling']}]{emotion.strip_tags(p['text']).strip()}" for p in parts
                   if isinstance(p, dict) and emotion.strip_tags(str(p.get('text') or '')).strip())


def schema(alternatives):
    """Choose the operation before narrating it; no-action remains an explicit option."""
    properties = {'act': {'anyOf': [a for a, _ in alternatives]}, 'say': SAY}
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}


def operations(act, work, env):
    """What the decision does, as (operation, arguments): the names the work runner and the game use."""
    kind = (act or {}).get('kind')
    decision = (work or {}).get('decision') or {}
    if kind in (None, 'none'):
        return []
    if kind == 'tell':
        return [('tell_game_task', {})]
    if kind == 'replace':
        name = (capabilities(env) or [{}])[0].get('name')
        return [('replace_game_task', {'capability': name, 'arguments': {'request': act.get('request')},
            'expected_work': tuple((work or {}).get(k) for k in ('session', 'task_id'))})]
    if kind == 'cancel' and work and work['state'] in ('accepted', 'running'):
        return [('stop_game_task', {})]
    if kind in ('reply', 'retry', 'cancel'):
        return [('answer_game_task', {'decision_id': decision.get('decision_id'), 'action': kind})]
    if kind == 'resume':
        return [('resume_game_task', {'capability': work.get('capability'), 'arguments': copy.deepcopy(work.get('arguments') or {})})]
    if kind == 'work':
        name = (capabilities(env) or [{}])[0].get('name')
        return [('submit_game_task', {'capability': name, 'arguments': {'request': act.get('request')}})]
    return [(kind, act.get('arguments') or {})]


class GameDecision:
    """Decides and carries out one owner utterance, and returns what Ciel says about it."""
    TEMPERATURE = 0   # the local model; a cloud reasoning model takes its own

    def __init__(self, runner, template, *, client=None, authorized=lambda: True):
        self.runner, self.template = runner, template
        self.authorized = authorized
        self._client = client
        self._items = {}
        self._generation = 0          # a stop word heard while deciding cancels what was decided
        self._fast_stop = None
        self._speech_reference = None
        self._reference_items = {}
        self._reference_tasks = set()
        self._speech_item = None
        self.autonomy_allowed = True

    def supported(self) -> bool:
        return self.runner.env is not None and self.runner.env.playing()

    # ---- what is heard before the decision ----
    async def _capture_references(self):
        env = self.runner.env
        if not env.playing() or not env.profile.get('reference_context'):
            return None
        epoch = getattr(env, '_connection_epoch', None)
        if await asyncio.wait_for(env._refresh(), 2) is False or epoch != getattr(env, '_connection_epoch', None):
            raise RuntimeError('Reference observation unavailable')
        return copy.deepcopy(env.state.get('references'))

    def on_user_state(self, event):
        """When the owner stops speaking, capture what they point at (the words arrive after)."""
        if event.new_state == 'speaking':
            self._speech_reference = None
            self._speech_item = None
            return
        if getattr(event, 'old_state', None) != 'speaking':
            return
        self._begin_reference_capture()

    def _begin_reference_capture(self):
        task = asyncio.create_task(self._capture_references())
        self._speech_reference = (time.monotonic(), task)
        self._speech_item = None
        self._reference_tasks.add(task)

        def finished(t):
            self._reference_tasks.discard(t)
            if not t.cancelled():
                t.exception()   # observed again by the matching words; no orphan warning
        task.add_done_callback(finished)

    def on_transcribed(self, event, owner=True):
        """Bind the captured pointing to the words; a plain stop word stops the body at once."""
        if not owner or not getattr(event, 'is_final', False):
            return
        if STOP.fullmatch(event.transcript.strip()):
            self.autonomy_allowed = False
            self._generation += 1
            self._fast_stop = asyncio.create_task(self._stop())
            return
        item_id = getattr(event, 'item_id', None)
        if item_id and self.runner.env is not None and self.runner.env.profile.get('reference_context'):
            if (not self._speech_reference or time.monotonic() - self._speech_reference[0] >= 10
                    or self._speech_item not in (None, item_id)):
                self._begin_reference_capture()
            captured_at, task = self._speech_reference
            if time.monotonic() - captured_at < 10:
                self._speech_item = item_id
                self._reference_items[item_id] = (task, getattr(self.runner.env, '_connection_epoch', None))
                while len(self._reference_items) > 16:
                    del self._reference_items[next(iter(self._reference_items))]

    async def _stop(self):
        """Stop the work, or the body's direct action when no work runs."""
        self.autonomy_allowed = False
        if self.runner.body_step():
            return await self.runner.stop()
        env = self.runner.env
        name = env.profile.get('stop_tool')
        if env.playing() and name and getattr(env, 'meta', {}).get(name, {}).get('ciel/stops'):
            result = await env.use(name, {})
            if not result.get('message') and result.get('status') in ('stopped', 'stopping'):
                result = {**result, 'message': '停止しました。' if result['status'] == 'stopped'
                          else '停止を依頼しました。停止の確認を待っています。'}
            return result
        return await self.runner.stop()

    async def close(self):
        for task in self._reference_tasks:
            task.cancel()
        await asyncio.gather(*self._reference_tasks, return_exceptions=True)
        if self._client is not None:
            await self._client.close()

    # ---- the decision ----
    async def handle(self, item, messages, tools=(), note: str = '') -> str | None:
        """messages: the conversation exactly as the conversation model gets it (its fixed instructions first);
        tools: the same tool schemas it gets. Local requests retain them for a shared cached prefix
        (Qwen's template puts tools first); cloud requests use only the JSON action schema. How to write the decision,
        what can be done now and the game's instructions (note) go after the conversation.
        Returns what to say, or None to let the conversation model answer as usual.
        One user item is decided once; a second call for it returns the same words."""
        if item.id in self._items:
            return self._items[item.id]
        reply = await self._handle(item, (list(messages), list(tools), note))
        self._items[item.id] = reply
        while len(self._items) > 128:
            del self._items[next(iter(self._items))]
        return reply

    async def _handle(self, item, prefix):
        text = item.text_content or ''
        if not self.authorized():
            return None
        env, generation = self.runner.env, self._generation
        if STOP.fullmatch(text.strip()):
            # The body was stopped when the words were heard (on_transcribed); Ciel says so.
            fast, self._fast_stop = self._fast_stop, None
            r = await fast if fast is not None else await self._stop()
            fact = r.get('message') or '停止を確認できませんでした。'
            return await self._speak(prefix, f'相手の言葉を受けて、体を止めました。結果：{fact}') or fact
        if not env.playing():
            return None
        work = self.runner.work
        references = await self._references(item)
        targets = bind_targets(env, text, references, item.id)
        alternatives = acts(env, work, targets)
        out = await self._decide(prefix, alternatives, work)
        if out is None:
            return None   # The conversation model answers as before; nothing was started.
        act, say = out.get('act') or {}, spoken(out.get('say'))
        if generation != self._generation or not self.authorized():
            return await self._speak(prefix, '確かめている間に止める指示があったので、何も始めませんでした。') \
                or '止める指示があったので、何も始めませんでした。'
        failure = await self._carry_out(operations(act, work, env), text, targets, references)
        if failure:
            return await self._speak(prefix, f'選んだ行動は、できませんでした。理由：{failure}') or failure
        if act.get('kind') != 'none':
            self.autonomy_allowed = True
        return say or None

    async def _references(self, item):
        """What was pointed at when the owner finished speaking."""
        env = self.runner.env
        if not env.profile.get('reference_context'):
            return None
        try:
            capture = self._reference_items.pop(item.id, None)
            if capture:
                task, epoch = capture
                references = await task
                return references if epoch == getattr(env, '_connection_epoch', None) else None
            return await self._capture_references()
        except Exception:
            debug_log.record('game_decision_error', error='references_unavailable')
            return None

    async def _decide(self, prefix, alternatives, work, note='', *, template=None, silent=False):
        messages, tools, game = prefix
        local = models.is_local('mind')
        after = '\n\n'.join(t for t in (game, instructions(template or self.template, alternatives), note) if t)
        # After the conversation, as the conversation model's own turn notes are (mind.local_context).
        wire = [*messages, {'role': 'user', 'content': NOTE_PREFIX + after} if local else {'role': 'system', 'content': after}]
        if self._client is None:
            self._client = models.create_client('mind')
        decision_schema = schema(alternatives)
        if silent:
            decision_schema = copy.deepcopy(decision_schema)
            decision_schema['properties']['say']['minItems'] = 0
        request, began = uuid.uuid4().hex, time.monotonic()
        timings = {}
        debug_log.record('work_inference', id=request, model=models.model('mind'), stage='consider' if silent else 'decide' if not note else 'decide_speak',
                         state=(work or {}).get('state'), temperature=self.TEMPERATURE if local else None)
        try:
            from decision_format import DecisionFormat
            output = DecisionFormat('decision', decision_schema, local=local)
            options = models.options('mind', model=models.model('mind'), max_completion_tokens=800, timeout=20, messages=wire,
                                     # Local templates keep the shared tool prefix for caching.
                                     # Hosted models interpret tool_choice=none as prohibiting
                                     # the game actions too, even though those use the JSON act.
                                     **({'tools': tools, 'tool_choice': 'none'} if local and tools else {}),
                                     response_format=output.response_format,
                                     **({'temperature': self.TEMPERATURE} if local else {'reasoning_effort': REASONING}))
            response = await self._client.chat.completions.create(**options)
            timings = getattr(response, 'timings', None) or {}
            models.record('mind', models.model('mind'), getattr(response, 'usage', None))
            out = output.decode(response)
        except Exception as e:
            debug_log.record('game_decision_error', error=type(e).__name__)
            return None
        finally:
            debug_log.record('model_response', role='consider' if silent else 'game_decision', id=request,
                             seconds=round(time.monotonic()-began, 3),
                             prompt_ms=timings.get('prompt_ms'), predicted_ms=timings.get('predicted_ms'))
        debug_log.record('work_decision', stage='decide', operation=(out.get('act') or {}).get('kind'))
        return out

    async def consider(self, messages, tools, template, *, game='', valid=lambda: True):
        """One autonomous decision. Reuse the reply prefix; never answer a human-only work decision."""
        if not valid():
            return {'status': 'cancelled', 'say': '', 'acted': False}
        runner = self.runner
        env = runner.env if runner is not None else None
        work = copy.deepcopy(runner.work) if runner is not None else None
        epoch = getattr(env, '_connection_epoch', None)
        generation = self._generation
        can_act = bool(env is not None and self.supported() and self.authorized()
                       and self.autonomy_allowed and after_work(work))
        alternatives = acts(env, work) if can_act else [(NONE, 'none')]
        out = await self._decide((list(messages), list(tools), game), alternatives, work,
                                 template=template, silent=True)
        if not valid() or generation != self._generation:
            return {'status': 'cancelled', 'say': '', 'acted': False}
        if out is None:
            return {'status': 'failed', 'say': '', 'acted': False}
        act = out['act']
        moving = act.get('kind') != 'none'
        if moving:
            if (not can_act or not self.authorized() or not self.autonomy_allowed or not self.supported()
                    or epoch != getattr(env, '_connection_epoch', None) or runner.work != work):
                return {'status': 'cancelled', 'say': '', 'acted': False}
            failure = await self._carry_out(operations(act, work, env), act.get('request', ''), None, None)
            if failure:
                return {'status': 'failed', 'say': '', 'acted': False}
        say = spoken(out['say']) if valid() else ''
        return {'status': 'acted' if moving else 'spoken' if say else 'silent', 'say': say, 'acted': moving}

    async def _speak(self, prefix, note):
        """Ciel's own words about what happened, from a decision that can only speak."""
        out = await self._decide(prefix, [(NONE, 'none：話すだけ')], self.runner.work, note)
        return spoken((out or {}).get('say')) or None

    def _why(self, r):
        r = r if isinstance(r, dict) else {}
        reason = r.get('reason')
        return r.get('message') or self.runner.env.profile.get('reasons', {}).get(reason, reason) or r.get('status') or '結果が分からない'

    async def _carry_out(self, ops, text, targets, references):
        """None when done (or nothing to do); otherwise why it was not done."""
        runner, env = self.runner, self.runner.env
        for name, args in ops:
            if name == 'tell_game_task':
                r = await runner.tell(text[:2000])
            elif name == 'stop_game_task':
                r = await self._stop()
            elif name == 'answer_game_task':
                r = await runner.answer(args['decision_id'], args['action'],
                                        text[:2000] if args['action'] == 'reply' else None)
            elif name == 'replace_game_task':
                if tuple((runner.work or {}).get(k) for k in ('session', 'task_id')) != args['expected_work']:
                    return '判断している間に対象の作業が変わりました'
                handoff = _handoff(env, args['capability'])
                if not handoff:
                    return '新しい目的を受け付ける入口がありません'
                request = str(args['arguments']['request'])[:2000]
                generation = self._generation
                r = await runner.replace(args['capability'], {handoff['argument']: request},
                    constraints=copy.deepcopy(handoff['constraints']), seconds=handoff['seconds'], title=request[:100],
                    valid=lambda: self.authorized() and generation == self._generation)
            elif runner.body_step():
                return '今の作業の途中なので、先に止める必要がある'
            elif name == 'resume_game_task':
                handoff = _handoff(env, args['capability'])
                if handoff is None:
                    return 'その作業は今は始め直せない'
                r = await runner.start(args['capability'], args['arguments'], constraints=copy.deepcopy(handoff['constraints']),
                                       title=getattr(runner, 'title', '') or str(args['arguments'].get(handoff['argument']) or '')[:100],
                                       seconds=handoff['seconds'], request_id=uuid.uuid4().hex)
            elif name == 'submit_game_task':
                capability = (capabilities(env) or [{}])[0]
                handoff = capability['handoff']
                request = str(args['arguments'].get('request') or text)
                r = await runner.start(capability['name'], {handoff['argument']: request[:2000]},
                                       constraints=copy.deepcopy(handoff['constraints']), title=request[:100],
                                       seconds=handoff['seconds'], request_id=uuid.uuid4().hex)
            else:
                fn = next((f for f in _act_tools(env) if f.id == name), None)
                if fn is None:
                    return 'その行動は今は使えない'
                try:
                    if targeted(env, name):
                        args = targets.resolve(name, args)
                        ref_arg = env.meta[name].get('ciel/reference_argument')
                        if ref_arg and (not references or args.get(ref_arg) != references.get('selection_id')):
                            return '指し示した対象を確かめられなかった'
                    jsonschema.validate(args, fn.info.raw_schema['parameters'])
                except (ValueError, jsonschema.ValidationError):
                    return '行き先や対象を確かめられなかった'
                r = await env.use(name, args)
            debug_log.record('game_decision_result', operation=name, status=(r or {}).get('status') if isinstance(r, dict) else None)
            if not isinstance(r, dict) or r.get('status') in FAILED:
                return self._why(r)
        return None
