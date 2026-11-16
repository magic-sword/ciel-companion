"""Experimental say/act controller. The host owns dispatch and observed results.

Used by the lifecycle evaluation, not enabled in the deployed voice pipeline.
No side effects occur here: calls still go through the existing catalog/MCP guards.
"""
import copy
import json
import time
import uuid

import jsonschema
from livekit.agents import llm
from game_decision import SAY, spoken


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
