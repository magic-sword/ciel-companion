import json
import unittest
from dataclasses import replace
from unittest.mock import patch

import jsonschema
from capabilities import CapabilityCatalog
from persona import load_persona
from tool_decision import ToolDecision
import tools


class ToolDecisionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = CapabilityCatalog(tools.MODULES)
        self.visible = {f.id: f for f in self.catalog.select(tools.TOOLS + [self.catalog.loader, self.catalog.executor])}
        self.loop = ToolDecision()

    def choose(self, act):
        schema = self.loop.schema(self.catalog, self.visible)
        return self.loop.resolve({'say': [], 'act': act}, schema, self.catalog, self.visible)

    def test_none_is_a_valid_initial_choice(self):
        self.assertEqual(self.choose({'kind': 'none'}), ('', None))
        self.assertEqual(self.loop.outcome, 'none')

    def test_load_is_not_completion_and_does_not_expose_unloaded_tools(self):
        with self.assertRaises(jsonschema.ValidationError):
            self.choose({'kind': 'call', 'tool_id': 'read_minutes', 'arguments': {}})
        _, call = self.choose({'kind': 'load', 'service_ids': ['5']})
        result = self.catalog.load(['5'])
        self.loop.observe(call.name, result)
        for terminal in ('none', 'complete', 'accepted'):
            with self.assertRaises(jsonschema.ValidationError):
                self.choose({'kind': terminal, **({'evidence': ['r1']} if terminal != 'none' else {})})
        _, call = self.choose({'kind': 'call', 'tool_id': 'read_minutes', 'arguments': {}})
        self.assertEqual(call.name, 'execute_capability')
        self.assertEqual(json.loads(call.arguments)['version'], self.catalog.definition('read_minutes')['version'])
        self.loop.observe('read_minutes', {'status': 'ok'})
        self.choose({'kind': 'complete', 'evidence': ['r2']})
        self.assertEqual(self.loop.outcome, 'complete')

    def test_failed_result_can_be_reported_but_not_cited_as_success(self):
        self.catalog.load(['5'])
        self.choose({'kind': 'call', 'tool_id': 'read_minutes', 'arguments': {}})
        self.loop.observe('read_minutes', {'status': 'failed'})
        with self.assertRaises(jsonschema.ValidationError):
            self.choose({'kind': 'complete', 'evidence': ['r1']})
        self.choose({'kind': 'blocked'})

    def test_repeat_operation_is_not_dispatched_twice(self):
        self.catalog.load(['5'])
        act = {'kind': 'call', 'tool_id': 'read_minutes', 'arguments': {}}
        self.choose(act)
        self.loop.observe('read_minutes', {'status': 'ok'})
        with self.assertRaisesRegex(ValueError, 'duplicate_operation'):
            self.choose(act)

    def test_current_permissions_override_old_schema(self):
        self.catalog.load(['5'])
        schema = self.loop.schema(self.catalog, self.visible)
        self.catalog.select(tools.for_comments(tools.TOOLS))
        with self.assertRaisesRegex(ValueError, 'no_longer_allowed'):
            self.loop.resolve({'say': [], 'act': {'kind': 'call', 'tool_id': 'read_minutes', 'arguments': {}}},
                              schema, self.catalog, self.visible)

    def test_refused_operation_absent_and_can_clarify_after_loading(self):
        self.catalog.load(['5'])
        schema = self.loop.schema(self.catalog, self.visible, {'start_minutes'})
        self.assertNotIn('start_minutes', json.dumps(schema))
        self.choose({'kind': 'load', 'service_ids': ['5']})
        self.choose({'kind': 'clarify'})

    def test_cancel_timeout_and_step_budget(self):
        self.loop.cancelled = True
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.choose({'kind': 'none'})
        self.loop.cancelled = False
        with patch('tool_decision.time.monotonic', return_value=self.loop.started + 121):
            with self.assertRaises(TimeoutError):
                self.choose({'kind': 'none'})
        self.loop.steps = 8
        with self.assertRaises(TimeoutError):
            self.choose({'kind': 'none'})

    def test_intermediate_speech_is_held_and_prompt_is_loaded(self):
        schema = self.loop.schema(self.catalog, self.visible)
        speech, call = self.loop.resolve({'say': [{'feeling': 'neutral', 'text': '記録します。'}],
            'act': {'kind': 'load', 'service_ids': ['5']}}, schema, self.catalog, self.visible)
        self.assertEqual(speech, '')
        self.assertIsNotNone(call)
        persona = load_persona()
        self.assertIn('{state}', persona.tool_decide_instructions)
        self.assertNotEqual(persona.fingerprint, replace(persona, tool_decide_instructions='changed').fingerprint)
