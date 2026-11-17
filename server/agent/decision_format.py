"""Provider wire format for decisions; canonical schemas remain execution authority."""
import copy
import json

import jsonschema


class DecisionFormat:
    def __init__(self, name, schema, *, local):
        self.schema = copy.deepcopy(schema)
        self.local = local
        wire = copy.deepcopy(schema)
        if not local:
            # Tool schemas may contain optional fields or open objects. Keep their
            # exact JSON semantics, rather than making optional arguments required.
            for action in wire['properties']['act']['anyOf']:
                properties = action['properties']
                if 'arguments' in properties:
                    arguments = properties['arguments']
                    properties['arguments'] = {
                        'type': 'string',
                        'description': 'JSON-encoded arguments conforming to this schema: '
                            + json.dumps(arguments, ensure_ascii=False, separators=(',', ':')),
                    }
            wire = self._strict(wire)
        self.wire = wire
        self.response_format = {'type': 'json_schema', 'json_schema': {
            'name': name, 'schema': wire, **({} if local else {'strict': True})}}

    @classmethod
    def _strict(cls, schema):
        value = copy.deepcopy(schema)
        # Uniqueness is checked against the canonical schema after decoding.
        value.pop('uniqueItems', None)
        if 'const' in value:
            value['enum'] = [value.pop('const')]
        if 'enum' in value and 'type' not in value:
            types = {('null' if x is None else 'boolean' if isinstance(x, bool)
                      else 'integer' if isinstance(x, int) else 'number' if isinstance(x, float)
                      else 'string') for x in value['enum']}
            value['type'] = next(iter(types)) if len(types) == 1 else sorted(types)
        if 'properties' in value:
            if set(value.get('required', [])) != set(value['properties']):
                raise ValueError('decision_envelope_has_optional_fields')
            value['additionalProperties'] = False
            value['properties'] = {k: cls._strict(v) for k, v in value['properties'].items()}
        if 'items' in value:
            value['items'] = cls._strict(value['items'])
        if 'anyOf' in value:
            value['anyOf'] = [cls._strict(v) for v in value['anyOf']]
        return value

    def decode(self, response):
        choice = response.choices[0]
        if getattr(choice.message, 'refusal', None):
            raise ValueError('decision_refused')
        if getattr(choice, 'finish_reason', None) not in (None, 'stop'):
            raise ValueError('decision_incomplete')
        try:
            value = json.loads(choice.message.content or '')
            jsonschema.validate(value, self.wire)
            if not self.local and 'arguments' in value['act']:
                value['act']['arguments'] = json.loads(value['act']['arguments'])
            jsonschema.validate(value, self.schema)
        except (json.JSONDecodeError, jsonschema.ValidationError):
            # SDK logging must not include the rejected conversation or arguments.
            raise ValueError('invalid_decision_format') from None
        return value
