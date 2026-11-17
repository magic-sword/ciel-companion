"""Say/act controller and LiveKit adapter; dispatch stays in the catalog/MCP guards."""
import asyncio
import copy
import json
import time
import uuid

import jsonschema
from livekit.agents import llm
from livekit.agents.llm._provider_format.openai import to_fnc_ctx
from game_decision import REASONING, SAY, spoken
import models
import debug_log


def object_schema(properties):
    return dict(type='object', additionalProperties=False, properties=properties, required=list(properties))


def terminal(kind, **properties):
    return object_schema({'kind': {'const': kind}, **properties})


class ToolDecision:
    MAX_STEPS = 8
    MAX_SECONDS = 120

    def __init__(self):
        self.started = time.monotonic()
        self.steps = 0
        self.pending = False
        self.results = []
        self.attempted = set()
        self.outcome = None
        self.cancelled = False
        self.issued = {}
        self.observed = set()
        self.notification_owned = False

    def check(self):
        if self.cancelled:
            raise RuntimeError('decision_cancelled')
        if self.outcome is not None:
            raise RuntimeError('decision_already_finished')
        if self.steps >= self.MAX_STEPS or time.monotonic() - self.started >= self.MAX_SECONDS:
            raise TimeoutError('decision_budget_exhausted')

    def schema(self, catalog, visible, refused=()):
        self.check()
        actions = []
        if not self.pending:
            actions.append(terminal('none'))
        actions.extend([terminal('clarify'), terminal('blocked')])
        evidence = [r['id'] for r in self.results if not r['error'] and r['tool'] != catalog.loader.id]
        if evidence:
            refs = dict(type='array', items={'enum': evidence}, minItems=1, maxItems=len(evidence), uniqueItems=True)
            actions.extend([terminal('complete', evidence=refs), terminal('accepted', evidence=refs)])
        services = [s.id for s in catalog.available() if any(
            catalog.service_for(n) == s.name and n not in refused for n in catalog.allowed)]
        if services and catalog.loader.id in visible:
            actions.append(terminal('load', service_ids=dict(type='array', items={'enum': services},
                minItems=1, maxItems=min(3, len(services)), uniqueItems=True)))
        for name in sorted(catalog.allowed):
            if name in refused or not catalog.can_execute(name):
                continue
            definition = catalog.definition(name)
            if definition:
                actions.append(terminal('call', tool_id={'const': name},
                    arguments=copy.deepcopy(definition['schema']['parameters'])))
        say = copy.deepcopy(SAY)
        say['minItems'] = 0
        return object_schema({'say': say, 'act': {'anyOf': actions}})

    def context(self):
        # Tool outputs remain in the actual tool history; this is just their identity
        # and outcome ledger, never a second copy of long service instructions.
        return json.dumps(dict(pending=self.pending, results=self.results), ensure_ascii=False)

    @staticmethod
    def menu(schema):
        """Schemas are already in tool definitions/results; repeat only decision IDs."""
        items = []
        for alternative in schema['properties']['act']['anyOf']:
            properties = alternative['properties']
            item = {'kind': properties['kind']['const']}
            if 'tool_id' in properties:
                item['tool_id'] = properties['tool_id']['const']
            if 'service_ids' in properties:
                item['available_service_ids'] = properties['service_ids']['items']['enum']
            items.append(item)
        return json.dumps(items, ensure_ascii=False, separators=(',', ':'))

    def resolve(self, decision, schema, catalog, visible, refused=()):
        """Validate against both the proposed schema and the CURRENT permission state."""
        self.check()
        jsonschema.validate(decision, schema)
        self.steps += 1
        act = decision['act']
        kind = act['kind']
        if kind in ('none', 'clarify', 'blocked', 'complete', 'accepted'):
            self.outcome = kind
            return spoken(decision['say']), None
        self.pending = True
        if kind == 'load':
            name, arguments = catalog.loader.id, {'service_ids': act['service_ids']}
        else:
            target = act['tool_id']
            if target in refused or not catalog.can_execute(target):
                raise ValueError('operation_no_longer_allowed')
            if target in visible:
                name, arguments = target, act['arguments']
            else:
                name = catalog.executor.id
                arguments = dict(tool_id=target, version=catalog.definition(target)['version'], arguments=act['arguments'])
            identity = json.dumps([target, act['arguments']], sort_keys=True, ensure_ascii=False)
            if identity in self.attempted:
                raise ValueError('duplicate_operation')
            self.attempted.add(identity)
        if name not in visible:
            raise ValueError('entrypoint_no_longer_allowed')
        call = llm.FunctionToolCall(name=name, arguments=json.dumps(arguments, ensure_ascii=False), call_id=uuid.uuid4().hex)
        self.issued[call.call_id] = catalog.target(call)
        # A proposal is not an observed success. Intermediate speech is held until
        # feedback, so an unexecuted promise is never the terminal spoken answer.
        return '', call

    def observe(self, name, output, *, error=False):
        """Transport success is evidence for reasoning, not proof of task completion."""
        status = None
        try:
            data = json.loads(output) if isinstance(output, str) else output
            if isinstance(data, dict):
                status = data.get('status')
                error |= status in {'failed', 'error', 'unavailable', 'invalid_selection', 'not_found', 'denied'}
        except (TypeError, ValueError):
            pass
        self.results.append(dict(id=f'r{len(self.results)+1}', tool=name, status=status, error=error))

    def feedback(self, event):
        """Keep LiveKit's result loop running, including services owning their spoken notice."""
        for output in event.function_call_outputs:
            if output.call_id not in self.issued or output.call_id in self.observed:
                continue
            self.observed.add(output.call_id)
            self.notification_owned = not output.reply_required and not output.is_error
            self.observe(self.issued[output.call_id], output.output, error=output.is_error)
            if not self.cancelled:
                output.reply_required = True


class ConversationDecision:
    """A bounded say/act stream; LiveKit owns audio delivery and interruption."""
    def __init__(self, observe=lambda **state: None, observe_continuation=lambda **state: None, enabled=True):
        self.observe = observe
        self.observe_continuation = observe_continuation
        self.enabled = enabled
        self.progress("waiting")
        self.speech_id = None
        self.loop = self.flow = None

    def progress(self, phase):
        self.phase = phase
        self.observe_continuation(enabled=self.enabled, phase=phase)

    def configure(self, enabled):
        if self.enabled == enabled:
            return
        if self.flow is not None and not self.flow.waiting:
            self.cancel()
        self.enabled = enabled
        self.progress(self.phase)

    def cancel(self):
        if self.flow is not None and not self.loop.cancelled:
            self.flow.interrupt()
            self.show("cancelled")
            self.progress("cancelled")

    def show(self, phase):
        self.observe(phase=phase, step=self.loop.steps if self.loop else 0,
                     outcome=self.loop.outcome or "" if self.loop else "")

    async def close(self):
        self.cancel()

    def on_user_state(self, event):
        if event.new_state == 'speaking':
            self.cancel()

    def feedback(self, event):
        if self.loop is not None:
            before = len(self.loop.observed)
            self.loop.feedback(event)
            if not self.loop.cancelled and len(self.loop.observed) > before:
                self.show("reviewing")

    async def node(self, owner, ctx, functions, settings, *, source=None):
        from continuation import Continuation
        import os
        speech = owner.session.current_speech
        if self.loop is None or self.speech_id != speech.id:
            self.cancel()
            enabled = os.environ.get('CIEL_INITIATIVE', '1') == '1' and getattr(owner.style, 'talk', 'normal') != 'quiet'
            self.enabled = enabled
            self.flow = Continuation(enabled=enabled, speech_chars=120 if enabled else None)
            self.flow.wake()
            self.speech_id, self.loop = speech.id, self.flow.chain
        flow, loop = self.flow, self.loop
        if loop.cancelled or getattr(speech, 'interrupted', False):
            return
        token = flow.generation
        # The SDK re-enters after actual function feedback; never synthesize success.
        resuming_tool = flow.pending is not None
        if resuming_tool:
            flow.finish(token)
        visible = {fn.id: fn for fn in functions}
        source = source if source is not None else ctx
        local = models.is_local('mind')
        messages = ctx.to_provider_format('openai')[0]
        template = owner.persona.tool_decide_instructions
        if flow.enabled:
            template += '\n\n' + owner.persona.continuation_experiment + '\n\n' + owner.persona.continuation_chunk_experiment
        first = True
        try:
            while not flow.waiting and not loop.cancelled and not getattr(speech, 'interrupted', False):
                self.show('deciding')
                self.progress("tool_result" if resuming_tool else "responding" if flow.steps == 0 else "continuing")
                resuming_tool = False
                refused = owner.mind.refused_now(source)
                schema = flow.schema(owner.capabilities, visible, refused)
                instruction = (template.replace('{state}', loop.context()).replace('{actions}', loop.menu(schema))
                               if first else loop.context() + '\n' + loop.menu(schema))
                first = False
                messages.append({'role': 'user' if local else 'system', 'content': ('SYSTEM: ' if local else '') + instruction})
                options = models.options('mind', model=models.model('mind'), messages=messages,
                    tools=to_fnc_ctx(llm.ToolContext(functions), strict=True), tool_choice='none',
                    response_format={'type': 'json_schema', 'json_schema': {'name': 'tool_decision', 'schema': schema,
                        **({} if local else {'strict': False})}},
                    max_completion_tokens=600, timeout=90,
                    **({'temperature': 0, 'seed': 1729} if local else {'reasoning_effort': REASONING}))
                async with models.create_client('mind', traced=True) as client:
                    response = await client.chat.completions.create(**options)
                models.record('mind', models.model('mind'), response.usage)
                if loop.cancelled or self.loop is not loop or getattr(speech, 'interrupted', False):
                    return
                if getattr(response.choices[0], 'finish_reason', None) == 'length':
                    raise RuntimeError('generation_truncated')
                raw = response.choices[0].message.content or ''
                decision = json.loads(raw)
                text, call = flow.accept(token, decision, schema, owner.capabilities, visible,
                                         owner.mind.refused_now(source))
                self.show(('loading' if decision['act']['kind'] == 'load' else 'calling') if call else 'finished')
                debug_log.record('conversation_decision', speech_id=speech.id, step=loop.steps,
                                 outcome=decision['act']['kind'], next=decision.get('next', 'wait'),
                                 notification_owned=loop.notification_owned)
                if call is None and loop.notification_owned and loop.outcome in ('complete', 'accepted'):
                    text = ''
                    # The service owns delivery; do not continue with duplicate narration.
                    flow.pending['value'] = {**decision, 'next': 'wait'}
                yield llm.ChatChunk(id=uuid.uuid4().hex, delta=llm.ChoiceDelta(role='assistant',
                    content=text or None, tool_calls=[call] if call is not None else []))
                if call is not None:
                    return
                # Submitted to the SDK stream, not a claim of completed audio playback.
                # Common history is recorded by the SDK, including interrupted speech.
                if loop.cancelled or self.loop is not loop or getattr(speech, 'interrupted', False):
                    return
                messages.append({'role': 'assistant', 'content': raw})
                flow.finish(token)
                self.progress("waiting" if flow.waiting else "continuing")
        except asyncio.CancelledError:
            flow.interrupt()
            if self.loop is loop:
                self.show("cancelled")
                self.progress("cancelled")
            raise
        except Exception:
            flow.interrupt()
            if self.loop is loop:
                self.show("failed")
                self.progress("failed")
            raise
