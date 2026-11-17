import unittest
from types import SimpleNamespace

from continuation import Continuation
from capabilities import CapabilityCatalog
import tools


class EmptyCatalog:
    allowed = set()
    loader = SimpleNamespace(id='load')
    def available(self):
        return []


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = EmptyCatalog()
        self.loop = Continuation(memo=True)
        self.token = self.loop.wake()

    def choose(self, kind='none', next='wait', text='hello', memo=''):
        schema = self.loop.schema(self.catalog, {})
        value = dict(say=[dict(feeling='neutral', text=text)] if text else [],
                     act=dict(kind=kind), next=next, memo=memo)
        return self.loop.accept(self.token, value, schema, self.catalog, {})

    def test_question_wait_does_not_poll_and_event_resumes(self):
        self.choose(text='Which colour?')
        self.assertFalse(self.loop.finish(self.token))
        with self.assertRaisesRegex(RuntimeError, 'not_ready'):
            self.loop.schema(self.catalog, {})
        self.token = self.loop.wake()
        self.choose(text='Blue it is.')

    def test_continue_requires_delivery_and_has_budget(self):
        self.loop.max_steps = 1
        self.choose(next='continue')
        with self.assertRaisesRegex(RuntimeError, 'delivery_pending'):
            self.loop.accept(self.token, {}, {}, self.catalog, {})
        with self.assertRaisesRegex(RuntimeError, 'not_ready'):
            self.loop.schema(self.catalog, {})
        self.assertTrue(self.loop.finish(self.token))
        with self.assertRaises(TimeoutError):
            self.loop.schema(self.catalog, {})

    def test_late_output_is_rejected_after_interruption(self):
        schema = self.loop.schema(self.catalog, {})
        self.loop.interrupt()
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            self.loop.accept(self.token, {}, schema, self.catalog, {})
        self.assertFalse(self.loop.finish(self.token))

    def test_undelivered_memo_is_not_committed(self):
        self.choose(next='continue', memo='ask later')
        self.loop.finish(self.token, delivered=False)
        self.assertEqual(self.loop.memo, '')
        self.assertTrue(self.loop.waiting)

    def test_memo_survives_user_input_and_can_be_cleared(self):
        self.choose(memo='ask later')
        self.loop.finish(self.token)
        self.token = self.loop.wake()
        self.assertEqual(self.loop.memo, 'ask later')
        self.choose(memo=None)
        self.loop.finish(self.token)
        self.assertEqual(self.loop.memo, '')

    def test_no_action_is_valid_but_empty_spin_is_not(self):
        with self.assertRaisesRegex(ValueError, 'empty_continuation'):
            self.choose(next='continue', text='')
        self.choose(text='')
        self.assertFalse(self.loop.finish(self.token))

    def test_clarification_cannot_auto_continue(self):
        text, call = self.choose(kind='clarify', next='continue')
        self.assertIn('hello', text)
        self.assertIsNone(call)
        self.assertFalse(self.loop.finish(self.token))
        self.assertTrue(self.loop.waiting)

    def test_previous_benchmark_policy_rejects_conflicting_terminal(self):
        self.loop.terminal_wait = False
        with self.assertRaisesRegex(ValueError, 'terminal_requires_wait'):
            self.choose(kind='clarify', next='continue')

    def test_control_has_no_next_or_memo_field(self):
        control = Continuation(enabled=False)
        control.wake()
        schema = control.schema(self.catalog, {})
        self.assertEqual(set(schema['properties']), {'say', 'act'})

    def test_turn_choice_precedes_words_without_extra_inference(self):
        schema = self.loop.schema(self.catalog, {})
        self.assertEqual(list(schema['properties']), ['next', 'say', 'act', 'memo'])
        previous = Continuation(turn_first=False)
        previous.wake()
        self.assertEqual(list(previous.schema(self.catalog, {})['properties']), ['say', 'act', 'next'])

    def test_chunk_limit_is_generation_contract_not_text_truncation(self):
        limited = Continuation(speech_chars=120)
        token = limited.wake()
        schema = limited.schema(self.catalog, {})
        self.assertEqual(schema['properties']['say']['maxItems'], 1)
        self.assertEqual(schema['properties']['say']['items']['properties']['text']['maxLength'], 120)
        import jsonschema
        with self.assertRaises(jsonschema.ValidationError):
            limited.accept(token, dict(next='wait', say=[dict(feeling='neutral', text='x'*121)],
                act=dict(kind='none')), schema, self.catalog, {})
        self.assertEqual(limited.steps, 0)

    def test_load_requires_actual_feedback_even_if_model_says_wait(self):
        catalog = CapabilityCatalog(tools.MODULES)
        visible = {f.id: f for f in catalog.select(tools.TOOLS + [catalog.loader, catalog.executor])}
        schema = self.loop.schema(catalog, visible)
        _, call = self.loop.accept(self.token, dict(say=[], act=dict(kind='load', service_ids=['5']),
            next='wait', memo=''), schema, catalog, visible)
        with self.assertRaisesRegex(RuntimeError, 'tool_feedback_required'):
            self.loop.finish(self.token)
        self.loop.chain.observe(call.name, catalog.load(['5']))
        self.assertTrue(self.loop.finish(self.token))
        schema = self.loop.schema(catalog, visible)
        self.assertIn('read_minutes', str(schema))

    def test_completed_operation_can_continue_talking_without_reissuing(self):
        catalog = CapabilityCatalog(tools.MODULES)
        visible = {f.id: f for f in catalog.select(tools.TOOLS + [catalog.loader, catalog.executor])}
        catalog.load(['5'])
        def accept(act, next='wait', text=''):
            return self.loop.accept(self.token, dict(say=[dict(feeling='neutral', text=text)] if text else [],
                act=act, next=next, memo=''), self.loop.schema(catalog, visible), catalog, visible)
        act = dict(kind='call', tool_id='read_minutes', arguments={})
        accept(act)
        self.loop.chain.observe('read_minutes', dict(status='ok'))
        self.loop.finish(self.token)
        accept(dict(kind='complete', evidence=['r1']), next='continue', text='Read it.')
        self.loop.finish(self.token)
        self.assertIn("'const': 'none'", str(self.loop.schema(catalog, visible)))
        with self.assertRaisesRegex(ValueError, 'duplicate_operation'):
            accept(act)
        self.assertTrue(self.loop.waiting)


if __name__ == '__main__':
    unittest.main()
