import copy
import json
import unittest
from types import SimpleNamespace as Obj

from decision_format import DecisionFormat


def response(value, **kwargs):
    return Obj(choices=[Obj(finish_reason=kwargs.get('finish_reason', 'stop'),
        message=Obj(content=json.dumps(value), refusal=kwargs.get('refusal')))])


class DecisionFormatTests(unittest.TestCase):
    def setUp(self):
        self.schema = {'type': 'object', 'additionalProperties': False,
            'required': ['say', 'act'], 'properties': {
                'say': {'type': 'array', 'maxItems': 1, 'items': {'type': 'string', 'maxLength': 40}},
                'act': {'anyOf': [{'type': 'object', 'additionalProperties': False,
                    'required': ['kind', 'arguments'], 'properties': {
                        'kind': {'const': 'call'}, 'arguments': {
                            'type': 'object', 'additionalProperties': False, 'required': ['request'],
                            'properties': {'request': {'type': 'string'},
                                'optional': {'type': ['string', 'null']}}}}}]}}}

    def test_both_providers_preserve_optional_absent_null_and_value(self):
        original = copy.deepcopy(self.schema)
        for arguments in ({'request': 'hello'}, {'request': 'hello', 'optional': None},
                          {'request': 'hello', 'optional': 'value'}):
            expected = {'say': ['hello'], 'act': {'kind': 'call', 'arguments': arguments}}
            for local in (True, False):
                codec = DecisionFormat('decision', self.schema, local=local)
                value = copy.deepcopy(expected)
                if not local:
                    value['act']['arguments'] = json.dumps(arguments)
                    self.assertTrue(codec.response_format['json_schema']['strict'])
                self.assertEqual(codec.decode(response(value)), expected)
        self.assertEqual(self.schema, original)

    def test_rejects_extra_speech_and_invalid_tool_arguments_on_both_routes(self):
        for local in (True, False):
            codec = DecisionFormat('decision', self.schema, local=local)
            for say, arguments in [(['a', 'b'], {'request': 'hello'}),
                                   (['x' * 41], {'request': 'hello'}),
                                   ([], {}), ([], {'request': 'hello', 'invented': True})]:
                value = {'say': say, 'act': {'kind': 'call',
                    'arguments': arguments if local else json.dumps(arguments)}}
                with self.assertRaisesRegex(ValueError, '^invalid_decision_format$'):
                    codec.decode(response(value))

    def test_rejects_refusal_truncation_and_malformed_arguments(self):
        codec = DecisionFormat('decision', self.schema, local=False)
        for kwargs in ({'refusal': 'refused'}, {'finish_reason': 'length'},
                       {'finish_reason': 'content_filter'}):
            with self.assertRaises(ValueError):
                codec.decode(response({}, **kwargs))
        with self.assertRaises(ValueError):
            codec.decode(response({'say': [], 'act': {'kind': 'call', 'arguments': '{'}}))

    def test_uniqueness_is_still_checked_after_wire_decode(self):
        self.schema['properties']['say'].update(maxItems=3, uniqueItems=True)
        codec = DecisionFormat('decision', self.schema, local=False)
        self.assertNotIn('uniqueItems', codec.wire['properties']['say'])
        with self.assertRaisesRegex(ValueError, '^invalid_decision_format$'):
            codec.decode(response({'say': ['a', 'a'], 'act': {
                'kind': 'call', 'arguments': '{"request":"hello"}'}}))
