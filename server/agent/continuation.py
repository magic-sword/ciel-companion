"""Experimental session continuation; no production host is wired to this yet.

ToolDecision still validates permissions, staged loading and result evidence.
The owner supplies delivery/result events; model completion alone is not delivery.
"""
import copy
import jsonschema

from tool_decision import ToolDecision


class Continuation:
    def __init__(self, *, enabled=True, memo=False, max_steps=8, turn_first=True, speech_chars=None, terminal_wait=True):
        self.enabled, self.memo_enabled = enabled, memo
        self.turn_first = turn_first
        self.speech_chars = speech_chars
        self.terminal_wait = terminal_wait
        self.max_steps = max_steps
        self.generation = 0
        self.waiting = True
        self.pending = None
        self.memo = ''
        self.steps = 0
        self.chain = ToolDecision()

    def interrupt(self):
        """Invalidate late model output without pretending dispatched work was undone."""
        self.generation += 1
        self.chain.cancelled = True
        self.waiting = True
        self.pending = None

    def wake(self):
        """Only the host may wake on a real input/event; never replay an old request."""
        self.interrupt()
        self.chain = ToolDecision()
        self.steps = 0
        self.waiting = False
        return self.generation

    def schema(self, catalog, visible):
        if self.waiting or self.pending:
            raise RuntimeError('continuation_not_ready')
        if self.steps >= self.max_steps:
            raise TimeoutError('continuation_budget_exhausted')
        value = self.chain.schema(catalog, visible)
        if self.speech_chars is not None:
            value['properties']['say']['maxItems'] = 1
            value['properties']['say']['items']['properties']['text']['maxLength'] = self.speech_chars
        if self.enabled:
            value['properties']['next'] = {'enum': ['continue', 'wait']}
            value['required'].append('next')
            if self.turn_first:
                value['properties'] = {'next': value['properties']['next'], **value['properties']}
                value['required'] = ['next', 'say', 'act']
        if self.memo_enabled:
            # Empty means keep; null means clear. No mandatory rewriting each round.
            value['properties']['memo'] = {'anyOf': [{'type': 'string', 'maxLength': 160}, {'type': 'null'}]}
            value['required'].append('memo')
        return value

    def accept(self, token, value, schema, catalog, visible):
        if token != self.generation or self.waiting:
            raise RuntimeError('stale_decision')
        if self.pending:
            raise RuntimeError('delivery_pending')
        jsonschema.validate(value, schema)
        kind = value['act']['kind']
        if not self.terminal_wait and value.get('next') == 'continue' and kind in ('clarify', 'blocked', 'accepted'):
            raise ValueError('terminal_requires_wait')
        if value.get('next') == 'continue' and kind == 'none' and not value['say'] and not value.get('memo'):
            raise ValueError('empty_continuation')
        base = copy.deepcopy(schema)
        for key in ('next', 'memo'):
            base['properties'].pop(key, None)
            if key in base['required']:
                base['required'].remove(key)
        try:
            text, call = self.chain.resolve({k: value[k] for k in ('say', 'act')}, base, catalog, visible)
        except Exception:
            self.interrupt()
            raise
        self.steps += 1
        self.pending = dict(token=token, value=value, call=call, results=len(self.chain.results))
        return text, call

    def finish(self, token, *, delivered=True):
        """Called after tool feedback or confirmed speech delivery, including silence."""
        if token != self.generation or not self.pending:
            return False
        value, call = self.pending['value'], self.pending['call']
        if call is not None and delivered and len(self.chain.results) <= self.pending['results']:
            raise RuntimeError('tool_feedback_required')
        self.pending = None
        if not delivered:
            self.interrupt()
            return False
        if self.memo_enabled and value.get('memo') != '':
            self.memo = value.get('memo') or ''
        if call is not None:
            # Result review is mandatory regardless of the model's next field.
            return True
        self.waiting = (value['act']['kind'] in ('clarify', 'blocked', 'accepted')
                        or value.get('next', 'wait') != 'continue')
        if not self.waiting:
            # Preserve operation identities/evidence across spoken continuations.
            self.chain.outcome = None
            self.chain.pending = False
        return not self.waiting
