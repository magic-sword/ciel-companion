import random
import unittest

from server.benchmark.farm import layout, validate, progress
from server.benchmark.policy import Progress
from server.benchmark.run import load_tasks
from server.benchmark.world import achieved


def state(goal_blocks, inventory=None):
    return {'inventory': inventory or {}, 'position': [0.5, 64, 0.5], 'health': 20, 'deaths': 0, 'goal_blocks': goal_blocks}


class FarmTaskTest(unittest.TestCase):
    def test_layout_keeps_the_farm_pond_and_field_apart_from_trees_ores_and_spawn(self):
        for seed in range(11, 31):
            for side in (-1, 1):
                farm = layout(random.Random(seed), side, 3)
                x1, z1, x2, z2 = farm['patch']
                self.assertEqual((x2 - x1, z2 - z1), (2, 2))
                for area in (farm['patch'], farm['pond'], farm['field']):
                    ax1, az1, ax2, az2 = area
                    self.assertTrue(-47 <= ax1 <= ax2 <= 47 and -47 <= az1 <= az2 <= 47)
                    self.assertTrue(all(x * side < 0 for x in (ax1, ax2)), 'on the trees\' side')
                    self.assertTrue(-9 <= az1 and az2 <= 9, 'where ores may be')
                self.assertGreaterEqual(min(abs(x1), abs(x2)), 8)
                wheat = [b for b in farm['goal_blocks'] if b[3] == 'wheat']
                water = [b for b in farm['goal_blocks'] if b[3] == 'water']
                self.assertEqual((len(wheat), len(water)), (8, 1))
                self.assertEqual(water[0][:3:2], [(x1 + x2) // 2, (z1 + z2) // 2])

    def test_the_suite_task_is_a_long_farm_on_stone(self):
        task = next(t for t in load_tasks() if t['id'] == 'long_wheat_farm')
        self.assertEqual((task['policy'], task['surface'], task['farm']), ('long-horizon-v1', 'stone', {'size': 3, 'crop': 'wheat'}))
        with self.assertRaises(ValueError):
            validate({**task, 'farm': {'size': 4, 'crop': 'wheat'}})

    def test_the_goal_is_every_cell_and_more_cells_count_as_progress(self):
        task = {'farm': {'size': 3, 'crop': 'wheat'}, 'milestones': []}
        initial = state([False] * 9)
        self.assertFalse(achieved(task, initial, state([True] * 8 + [False])))
        self.assertTrue(achieved(task, initial, state([True] * 9)))
        self.assertEqual(progress([True] * 3 + [False] * 6), 0.333)
        watch = Progress(initial, task)
        watch.observe(state([False] * 9), 10)
        self.assertEqual(watch.last_progress, 0)
        watch.observe(state([True] + [False] * 8), 20)
        self.assertEqual(watch.last_progress, 20)


class MobTaskTest(unittest.TestCase):
    def test_bed_tasks_place_one_or_three_white_sheep_under_the_long_policy(self):
        tasks = {t['id']: t for t in load_tasks()}
        self.assertEqual(tasks['long_white_bed']['mobs'], {'sheep': 3})
        self.assertEqual(tasks['long_white_bed_one_sheep']['mobs'], {'sheep': 1})
        self.assertEqual(tasks['long_white_bed']['policy'], 'long-horizon-v1')


if __name__ == '__main__':
    unittest.main()
