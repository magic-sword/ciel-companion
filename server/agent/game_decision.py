"""One decision per owner utterance while a game is played: what to say and what to do.

The conversation model reads the whole conversation and writes one structured output {say, act}.
`act` names one of the actions of the current work state (docs/conversation/agent-state-machine-ja.md):
  no work         a work capability, or one of the game's direct actions
  running work    words passed to the work, or stopping it
  waiting work    the answers the work's decision accepts
  ended work      as with no work, and starting the work that failed or was stopped again
Not acting is the kind `none`. `say` is what Ciel speaks, also when the action could not be done or
a stop word already stopped the body: then a second decision that can only speak tells it in her words.

Starting, checking and stopping stay with the work runner and the game environment. The intake
(game_intake.py) keeps two parts the decision builds on: stopping at once when a stop word is heard,
and capturing what the owner pointed at when the speech ended. An action aimed at a target (pointed,
or coordinates in the words) takes a target id; target_candidates binds the real value, the model
never writes it. Games whose work needs preparation are left to the intake as a whole.
"""
import copy
import json
import time
import uuid

import debug_log
import jsonschema
import models

STRING = {'type': 'string', 'minLength': 1, 'maxLength': 2000}
ACTIVE = ('accepted', 'running', 'needs_decision', 'cancelling')
ENDED = ('failed', 'cancelled')   # an ended work that may be started again with its own request
# Results that did not do what was chosen.
FAILED = ('error', 'unavailable', 'busy', 'goal_running', 'no_task', 'refused', 'failed')
FORMS = ('say_first', 'act_first')
NONE = {'type': 'object', 'additionalProperties': False, 'properties': {'kind': {'const': 'none'}}, 'required': ['kind']}


def supported(env) -> bool:
    """The decision covers games whose work takes the request as it is (a declared handoff)."""
    if not env.playing():
        return False
    work = env.profile.get('work') or {}
    if work.get('version') != 1:
        return False
    return not any((c.get('handoff') or {}).get('version') != 1 or c.get('preparation') for c in work.get('capabilities', []))


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
        out += [(_alt({'kind': {'const': 'tell'}, 'message': STRING}),
                 'tell：今の作業へ相手の言葉を渡す（やり方・好み・続けてよいこと）。messageに渡す言葉'),
                (_alt({'kind': {'const': 'cancel'}}), 'cancel：今の作業を止める')]
    elif state == 'needs_decision':
        decision = work.get('decision') or {}
        for action in decision.get('actions') or ['retry', 'cancel']:
            if action == 'reply':
                out.append((_alt({'kind': {'const': 'reply'}, 'message': STRING}),
                            f"reply：作業からの質問（{decision.get('message', '')}）へ相手の答えを渡す。messageに相手の答え"))
            elif action in ('retry', 'cancel'):
                out.append((_alt({'kind': {'const': action}}),
                            {'retry': 'retry：作業をもう一度試す', 'cancel': 'cancel：作業をやめる'}[action]))
    elif state not in ACTIVE:
        if state in ENDED and _handoff(env, work.get('capability')) and (work.get('arguments') or {}):
            request = json.dumps(work['arguments'], ensure_ascii=False)
            out.append((_alt({'kind': {'const': 'resume'}}),
                        f"resume：止まった作業（{request}）を、同じ依頼でもう一度始める。体は進んだ分を見て続きから計画する"))
        for capability in (env.profile.get('work') or {}).get('capabilities', []):
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
    return out


def _handoff(env, name):
    # The capability's declared handoff, or None.
    return next((c.get('handoff') for c in (env.profile.get('work') or {}).get('capabilities', []) if c.get('name') == name), None)


def instructions(template, alternatives):
    return template.replace('{actions}', '\n'.join('- ' + line for _, line in alternatives))


def schema(alternatives, form='say_first'):
    """say before act: the words are written first and the action chosen after them (fewer moves on praise)."""
    act, say = {'anyOf': [a for a, _ in alternatives]}, {'type': 'string'}
    properties = {'say': say, 'act': act} if form == 'say_first' else {'act': act, 'say': say}
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}


def operations(act, work, env):
    """What the decision does, as (operation, arguments): the names the work runner and the game use."""
    kind = (act or {}).get('kind')
    decision = (work or {}).get('decision') or {}
    if kind in (None, 'none'):
        return []
    if kind == 'tell':
        return [('tell_game_task', {'message': act.get('message')})]
    if kind == 'cancel' and work and work['state'] in ('accepted', 'running'):
        return [('stop_game_task', {})]
    if kind in ('reply', 'retry', 'cancel'):
        return [('answer_game_task', {'decision_id': decision.get('decision_id'), 'action': kind,
                                      **({'message': act.get('message')} if kind == 'reply' else {})})]
    if kind == 'resume':
        return [('resume_game_task', {'capability': work.get('capability'), 'arguments': copy.deepcopy(work.get('arguments') or {})})]
    if kind == 'work':
        name = ((env.profile.get('work') or {}).get('capabilities') or [{}])[0].get('name')
        return [('submit_game_task', {'capability': name, 'arguments': {'request': act.get('request')}})]
    return [(kind, act.get('arguments') or {})]


class GameDecision:
    """Decides and carries out one owner utterance, and returns what Ciel says about it."""
    TEMPERATURE = 0

    def __init__(self, intake, template, *, form='say_first'):
        self.intake, self.template, self.form = intake, template, form
        self.runner = intake.runner
        self._items = {}

    def supported(self) -> bool:
        return models.is_local('mind') and supported(self.runner.env)

    async def handle(self, item, system: str, messages) -> str | None:
        """system: the fixed instructions; messages: the rest of the conversation as sent to the model.
        Returns what to say, or None to let the conversation model answer as usual.
        One user item is decided once; a second call for it returns the same words."""
        if item.id in self._items:
            return self._items[item.id]
        reply = await self._handle(item, system, messages)
        self._items[item.id] = reply
        while len(self._items) > 128:
            del self._items[next(iter(self._items))]
        return reply

    async def _handle(self, item, system, messages):
        from game_intake import STOP
        text = item.text_content or ''
        if not self.intake.authorized():
            return None
        env, generation = self.runner.env, self.intake._generation
        if STOP.fullmatch(text.strip()):
            # The body was stopped when the words were heard (game_intake.on_transcribed); Ciel says so.
            fast, self.intake._fast_stop = self.intake._fast_stop, None
            r = await fast if fast is not None else await self.intake._stop()
            fact = r.get('message') or '停止を確認できませんでした。'
            return await self._speak(system, messages, f'相手の言葉を受けて、体を止めました。結果：{fact}') or fact
        if not env.playing():
            return None
        work = self.runner.work
        references = await self._references(item)
        targets = bind_targets(env, text, references, item.id)
        alternatives = acts(env, work, targets)
        out = await self._decide(system, messages, alternatives, work)
        if out is None:
            return None   # The conversation model answers as before; nothing was started.
        act, say = out.get('act') or {}, str(out.get('say') or '').strip()
        if generation != self.intake._generation or not self.intake.authorized():
            return await self._speak(system, messages, '確かめている間に止める指示があったので、何も始めませんでした。') \
                or '止める指示があったので、何も始めませんでした。'
        failure = await self._carry_out(operations(act, work, env), text, targets, references)
        if failure:
            return await self._speak(system, messages, f'選んだ行動は、できませんでした。理由：{failure}') or failure
        return say or None

    async def _references(self, item):
        """What was pointed at when the owner finished speaking, captured by the intake."""
        env = self.runner.env
        if not env.profile.get('reference_context'):
            return None
        try:
            capture = self.intake._reference_items.pop(item.id, None)
            if capture:
                task, epoch = capture
                references = await task
                return references if epoch == getattr(env, '_connection_epoch', None) else None
            return await self.intake._capture_references()
        except Exception:
            debug_log.record('game_decision_error', error='references_unavailable')
            return None

    async def _decide(self, system, messages, alternatives, work, note=''):
        wire = [{'role': 'system', 'content': system + '\n\n' + instructions(self.template, alternatives)
                 + (('\n\n' + note) if note else '')}, *messages]
        if self.intake._client is None:
            self.intake._client = models.create_client('mind')
        request, began = uuid.uuid4().hex, time.monotonic()
        debug_log.record('work_inference', id=request, model=models.model('mind'), stage='decide' if not note else 'decide_speak',
                         state=(work or {}).get('state'), temperature=self.TEMPERATURE)
        try:
            options = models.options('mind', model=models.model('mind'), max_completion_tokens=800, timeout=20,
                                     messages=wire, temperature=self.TEMPERATURE,
                                     response_format={'type': 'json_schema', 'json_schema': {
                                         'name': 'decision', 'schema': schema(alternatives, self.form)}})
            response = await self.intake._client.chat.completions.create(**options)
            models.record('mind', models.model('mind'), getattr(response, 'usage', None))
            out = json.loads(response.choices[0].message.content or '')
            if not isinstance(out, dict):
                raise ValueError('Expected object')
        except Exception as e:
            debug_log.record('game_decision_error', error=type(e).__name__)
            return None
        finally:
            debug_log.record('model_response', role='game_decision', id=request, seconds=round(time.monotonic()-began, 3))
        debug_log.record('work_decision', stage='decide', operation=(out.get('act') or {}).get('kind'))
        return out

    async def _speak(self, system, messages, note):
        """Ciel's own words about what happened, from a decision that can only speak."""
        out = await self._decide(system, messages, [(NONE, 'none：話すだけ')], self.runner.work, note)
        return str((out or {}).get('say') or '').strip() or None

    def _why(self, r):
        r = r if isinstance(r, dict) else {}
        reason = r.get('reason')
        return r.get('message') or self.runner.env.profile.get('reasons', {}).get(reason, reason) or r.get('status') or '結果が分からない'

    async def _carry_out(self, ops, text, targets, references):
        """None when done (or nothing to do); otherwise why it was not done."""
        runner, env = self.runner, self.runner.env
        for name, args in ops:
            if name == 'tell_game_task':
                r = await runner.tell(str(args.get('message') or text)[:2000])
            elif name == 'stop_game_task':
                r = await self.intake._stop()
            elif name == 'answer_game_task':
                r = await runner.answer(args['decision_id'], args['action'],
                                        str(args.get('message') or text)[:2000] if args['action'] == 'reply' else None)
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
                capability = ((env.profile.get('work') or {}).get('capabilities') or [{}])[0]
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
