"""Offline checks of Mindcraft-defined body tasks and partial progress scoring."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmark.mindcraft_tasks import VENDOR, expand, progress
from benchmark.report import summarize
from benchmark.run import load_tasks


def entry(**kw):
    return {'id': 'mc_x', 'mindcraft': {'file': 'tasks/x.json', 'task': 'x'}, 'forest': 'near',
            'milestones': ['oak_log', 'oak_planks', 'stick'], 'budget': {'seconds': 90}, **kw}


def upstream(**kw):
    return {'goal': 'Craft sticks.', 'initial_inventory': {}, 'agent_count': 1, 'target': 'stick',
            'number_of_target': 4, 'type': 'techtree', 'timeout': 500, **kw}


class ExpandTest(unittest.TestCase):
    def expand(self, task=None, **definition):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'tasks').mkdir()
            (Path(tmp)/'tasks'/'x.json').write_text(json.dumps({'x': upstream(**definition)}), encoding='utf-8')
            return expand(task or entry(), vendor=tmp)

    def test_upstream_owns_goal_target_count_and_inventory(self):
        task = self.expand(initial_inventory={'0': {'oak_planks': 2}})
        self.assertEqual((task['prompt'], task['item'], task['count'], task['inventory']),
                         ('Craft sticks.', 'stick', 4, {'oak_planks': 2}))
        self.assertEqual(task['modes'], ['body'])
        self.assertEqual(task['upstream']['timeout'], 500)
        self.assertEqual(len(task['upstream']['sha256']), 64)

    def test_missing_count_defaults_to_one_like_the_upstream_validator(self):
        definition = upstream()
        del definition['number_of_target']
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'tasks').mkdir()
            (Path(tmp)/'tasks'/'x.json').write_text(json.dumps({'x': definition}), encoding='utf-8')
            self.assertEqual(expand(entry(), vendor=tmp)['count'], 1)

    def test_unsupported_definitions_are_rejected(self):
        cases = [
            ({'agent_count': 2}, None),
            ({'blocked_actions': {'0': ['!craftRecipe']}}, None),
            ({'missing_items': ['stick']}, None),
            ({'initial_inventory': {'0': {}, '1': {}}}, None),
            ({'initial_inventory': {'stick': 1}}, None),
            ({}, entry(prompt='override')),
            ({}, entry(modes=['body', 'conversation'])),
            ({}, entry(milestones=['oak_log'])),
            ({}, entry(mindcraft={'file': '../x.json', 'task': 'x'})),
        ]
        for definition, task in cases:
            with self.subTest(definition=definition, task=task):
                with self.assertRaises(ValueError):
                    self.expand(task, **definition)


class SuiteTest(unittest.TestCase):
    def test_vendored_tasks_load_as_body_only_tasks(self):
        tasks = {t['id']: t for t in load_tasks() if t.get('upstream')}
        self.assertEqual(set(tasks), {'mc_gather_oak_logs', 'mc_crafting_oak_log', 'mc_crafting_stick',
                                      'mc_crafting_wooden_pickaxe', 'mc_crafting_stone_pickaxe'})
        for task in tasks.values():
            self.assertEqual(task['modes'], ['body'])
            self.assertTrue((VENDOR/task['upstream']['file']).is_file())
            self.assertLessEqual(task['budget']['seconds'], 120)
            self.assertEqual(task['milestones'][-1], task['item'])


class ProgressTest(unittest.TestCase):
    task = {'item': 'stick', 'count': 4, 'milestones': ['oak_log', 'oak_planks', 'stick']}

    def state(self, **inventory):
        return {'inventory': inventory}

    def test_partial_target_and_observed_milestones(self):
        result = progress(self.task, {'oak_log', 'oak_planks', 'stick'}, self.state(), self.state(stick=2))
        self.assertEqual((result['target'], result['milestones']), (0.5, 1.0))
        result = progress(self.task, {'oak_log'}, self.state(), self.state(oak_log=1))
        self.assertEqual((result['target'], result['milestones'], result['milestones_reached']), (0.0, 0.333, 1))

    def test_reaching_the_target_credits_intermediates_missed_between_snapshots(self):
        result = progress(self.task, {'stick'}, self.state(), self.state(stick=4))
        self.assertEqual((result['target'], result['milestones']), (1.0, 1.0))

    def test_given_items_are_not_progress(self):
        result = progress(self.task, set(), self.state(stick=1), self.state(stick=1))
        self.assertEqual(result['target'], 0.0)

    def test_summary_excludes_unscored_trials_from_progress(self):
        rows = [{'task': 't', 'status': 'failed', 'progress': {'target': 0.5, 'milestones': 1.0}},
                {'task': 't', 'status': 'skipped', 'reason': 'run_time_budget'},
                {'task': 't', 'status': 'infrastructure_error', 'progress': {'target': 0.0, 'milestones': 0.0}}]
        group = summarize(rows)['t']
        self.assertEqual((group['mean_target_progress'], group['mean_milestones_progress']), (0.5, 1.0))


if __name__ == '__main__':
    unittest.main()
