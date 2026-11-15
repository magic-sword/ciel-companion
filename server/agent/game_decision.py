"""One decision per owner utterance while a game is played: what to say and what to do.

The conversation model reads the whole conversation and writes one structured output {say, act}.
`act` names one of the actions of the current work state (docs/conversation/agent-state-machine-ja.md):
  no work         a work capability, or one of the game's direct actions
  running work    words passed to the work, or stopping it
  waiting work    the answers the work's decision accepts
Not acting is the kind `none`. Starting, checking and stopping stay with the work runner and the
game environment, as for the intake (game_intake.py), which still handles stop words, pointing and
games whose work needs preparation.
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
# Results that did not do what was chosen; the reply then says so instead of the planned words.
FAILED = ('error', 'unavailable', 'busy', 'goal_running', 'no_task', 'refused', 'failed')
FORMS = ('say_first', 'act_first')


def supported(env) -> bool:
    """The decision covers games whose work takes the request as it is and whose actions need no pointing."""
    if not env.playing() or env.profile.get('reference_context'):
        return False
    work = env.profile.get('work') or {}
    if work.get('version') != 1:
        return False
    if any((c.get('handoff') or {}).get('version') != 1 or c.get('preparation') for c in work.get('capabilities', [])):
        return False
    meta = getattr(env, 'meta', {})
    return not any(m.get('ciel/role') == 'act' and (m.get('ciel/reference_argument') or m.get('ciel/target_binding'))
                   for m in meta.values())


def _alt(properties):
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}


def acts(env, work):
    """The kinds a decision may take in this work state, as (schema alternative, line for the prompt)."""
    out = [(_alt({'kind': {'const': 'none'}}), 'none：話すだけ')]
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
        for capability in (env.profile.get('work') or {}).get('capabilities', []):
            out.append((_alt({'kind': {'const': 'work'}, 'request': STRING}),
                        # The name is how the game's own instructions refer to this capability.
                        f"work：{capability['name']}。{capability.get('description', '')} requestに相手の頼み"))
        for fn in getattr(env, 'tools', []):
            if getattr(env, 'meta', {}).get(fn.id, {}).get('ciel/role') == 'act':
                raw = copy.deepcopy(fn.info.raw_schema)
                raw['parameters']['additionalProperties'] = False
                out.append((_alt({'kind': {'const': fn.id}, 'arguments': raw['parameters']}),
                            f"{fn.id}：{raw.get('description', '')}"))
    return out


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
    if kind == 'work':
        name = ((env.profile.get('work') or {}).get('capabilities') or [{}])[0].get('name')
        return [('submit_game_task', {'capability': name, 'arguments': {'request': act.get('request')}})]
    return [(kind, act.get('arguments') or {})]


class GameDecision:
    """Decides and carries out one owner utterance; the intake keeps stop words and the rest."""
    TEMPERATURE = 0

    def __init__(self, intake, template, *, form='say_first'):
        self.intake, self.template, self.form = intake, template, form
        self.runner = intake.runner

    def supported(self) -> bool:
        return models.is_local('mind') and supported(self.runner.env)

    async def handle(self, item, system: str, messages) -> str | None:
        """system: the fixed instructions; messages: the rest of the conversation as sent to the model.
        Returns what to say, or None to let the conversation model answer as usual."""
        from game_intake import STOP
        text = item.text_content or ''
        if STOP.fullmatch(text.strip()):
            return await self.intake.handle(item)
        if not self.intake.authorized():
            return None
        env, generation = self.runner.env, self.intake._generation
        work = self.runner.work
        alternatives = acts(env, work)
        wire = [{'role': 'system', 'content': system + '\n\n' + instructions(self.template, alternatives)}, *messages]
        if self.intake._client is None:
            self.intake._client = models.create_client('mind')
        request, began = uuid.uuid4().hex, time.monotonic()
        debug_log.record('work_inference', id=request, model=models.model('mind'), stage='decide',
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
            return None   # The conversation model answers as before; nothing was started.
        finally:
            debug_log.record('model_response', role='game_decision', id=request, seconds=round(time.monotonic()-began, 3))
        act, say = out.get('act') or {}, str(out.get('say') or '').strip()
        debug_log.record('work_decision', stage='decide', operation=act.get('kind'))
        if generation != self.intake._generation or not self.intake.authorized():
            return '依頼の確認中に中止の指示があったため、作業を開始しませんでした。'
        done = await self._carry_out(operations(act, work, env), work, text)
        if done is not True:
            return done
        return say or None

    async def _carry_out(self, ops, work, text):
        """True when done (or nothing to do); otherwise the words that say it was not done."""
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
                return '今の作業を中止してから、新しい操作を依頼してください。'
            elif name == 'submit_game_task':
                capability = ((env.profile.get('work') or {}).get('capabilities') or [{}])[0]
                handoff = capability['handoff']
                request = str(args['arguments'].get('request') or text)
                r = await runner.start(capability['name'], {handoff['argument']: request[:2000]},
                                       constraints=copy.deepcopy(handoff['constraints']), title=request[:100],
                                       seconds=handoff['seconds'], request_id=uuid.uuid4().hex)
            else:
                fn = next((f for f in getattr(env, 'tools', []) if f.id == name), None)
                if fn is None:
                    return '操作を受け付けられませんでした。'
                try:
                    jsonschema.validate(args, fn.info.raw_schema['parameters'])
                except jsonschema.ValidationError:
                    return '操作の引数を確認できませんでした。'
                r = await env.use(name, args)
            debug_log.record('game_decision_result', operation=name, status=(r or {}).get('status'))
            if not isinstance(r, dict) or r.get('status') in FAILED:
                return (r or {}).get('message') or '操作を受け付けられませんでした。'
        return True
