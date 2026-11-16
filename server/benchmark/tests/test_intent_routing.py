import json
import sys
import types
import unittest
from pathlib import Path

from server.benchmark import intent_routing as ir

sys.path.insert(0, str(Path(ir.HERE).parent / 'agent'))   # game_decision, as the evaluator's setup() does

CASES = json.loads((Path(ir.HERE) / 'intent_routing_cases.json').read_text(encoding='utf-8'))


def accept_case(accept):
    return {'expect': 'accept', 'accept': accept}


class Score(unittest.TestCase):
    def test_outcome_names_answers_and_words_to_work(self):
        self.assertEqual(ir.outcome([('answer_game_task', {'action': 'reply'}), ('tell_game_task', {}),
                                     ('game_task_status', {})]), ['answer:reply', 'tell'])

    def test_accepted_outcomes(self):
        self.assertEqual(ir.score(accept_case(['none', 'tell']), [])['verdict'], 'ok')
        self.assertEqual(ir.score(accept_case(['none', 'tell']), [('tell_game_task', {})])['verdict'], 'ok')
        self.assertEqual(ir.score(accept_case(['none', 'tell']), [('submit_game_task', {})])['verdict'], 'wrong')
        self.assertEqual(ir.score(accept_case(['tell']), [])['verdict'], 'missed')
        self.assertEqual(ir.score(accept_case(['none']), [('answer_game_task', {'action': 'retry'})])['verdict'], 'false_action')

    def test_legacy_cases_keep_their_scoring(self):
        self.assertEqual(ir.score({'expect': 'chat'}, [('submit_game_task', {})])['verdict'], 'false_move')
        self.assertEqual(ir.score({'expect': 'stop'}, [('stop_game_task', {})])['verdict'], 'ok')


class WorkState(unittest.TestCase):
    def test_cases_hold_the_work_as_the_runner_reports_it(self):
        self.assertTrue(all(c['work'] is None or isinstance(c['work'], dict) for c in CASES))
        running = next(c for c in CASES if c['split'] == 'dev' and c['work'])
        self.assertEqual(ir.work_of(running)['state'], 'running')

    def test_work_cases_carry_a_state_and_accepted_outcomes(self):
        work = [c for c in CASES if c['split'] == 'work']
        self.assertGreaterEqual(len(work), 30)
        for case in work:
            self.assertTrue(case['accept'])
            self.assertTrue(case['work'] is None or case['work']['state'] in ('running', 'needs_decision', 'failed'))


class Decide(unittest.TestCase):
    def world(self):
        fn = types.SimpleNamespace(id='minecraft_come_here', info=types.SimpleNamespace(
            raw_schema={'description': 'come', 'parameters': {'type': 'object', 'properties': {}}}))
        return types.SimpleNamespace(profile={'work': {'version': 1, 'capabilities': [{'name': 'minecraft.pursue_goal', 'description': 'd', 'handoff': {'version': 1, 'argument': 'request', 'constraints': {}, 'seconds': 120}}]}},
                                     tools=[fn], meta={fn.id: {'ciel/role': 'act'}})

    def kinds(self, work):
        return [a['properties']['kind']['const'] for a, _ in ir.Harness._acts(self.world(), work)]

    def test_kinds_follow_the_work_state(self):
        self.assertEqual(self.kinds(None), ['none', 'work', 'minecraft_come_here'])
        self.assertEqual(self.kinds({'state': 'running'}), ['none', 'tell', 'cancel'])
        question = {'state': 'needs_decision', 'decision': {'decision_id': 'd', 'actions': ['reply', 'cancel'], 'message': 'q'}}
        self.assertEqual(self.kinds(question), ['none', 'reply', 'cancel'])

    def test_not_acting_is_recorded_as_no_action(self):
        self.assertEqual(ir.Harness._decided({}, None, self.world()), [])

    def test_decisions_become_recorded_actions(self):
        world = self.world()
        running = {'state': 'running'}
        question = {'state': 'needs_decision', 'decision': {'decision_id': 'd'}}
        self.assertEqual(ir.Harness._decided({'kind': 'none'}, running, world), [])
        self.assertEqual(ir.Harness._decided({'kind': 'cancel'}, running, world), [('stop_game_task', {})])
        self.assertEqual(ir.Harness._decided({'kind': 'cancel'}, question, world),
                         [('answer_game_task', {'decision_id': 'd', 'action': 'cancel'})])
        self.assertEqual(ir.Harness._decided({'kind': 'work', 'request': '家'}, None, world),
                         [('submit_game_task', {'capability': 'minecraft.pursue_goal', 'arguments': {'request': '家'}})])


if __name__ == '__main__':
    unittest.main()
