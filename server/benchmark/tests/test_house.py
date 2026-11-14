import random
import unittest

from server.benchmark.house import LANE_Z, PASTURE, cells, commands, footprint, layout, load, rotate, validate
from server.benchmark.run import load_tasks
from server.benchmark.world import achieved


class HouseTaskTest(unittest.TestCase):
    def test_turns_match_the_body_and_only_turns_that_fit_the_patch_are_goals(self):
        self.assertEqual(rotate([['a', 'b'], ['c', 'd']], 1), [['c', 'a'], ['d', 'b']])
        plan = load('dirt_shelter')
        self.assertEqual((footprint(plan), footprint(plan, 1)), ((5, 6), (6, 5)))
        for seed in range(11, 31):
            for side in (-1, 1):
                house = layout(random.Random(seed), side, 'dirt_shelter')
                x1, z1, x2, z2 = house['patch']
                self.assertEqual((x2 - x1 + 1, z2 - z1 + 1), (5, 6))
                self.assertTrue(all(x * side < 0 for x in (x1, x2)), 'on the side away from the trees')
                self.assertTrue(-9 <= z1 and z2 <= 9, 'clear of the ores')
                self.assertEqual(len(house['goal_layouts']), 2)
                for goal in house['goal_layouts']:
                    self.assertEqual({y for _, y, _, _ in goal}, {62, 63, 64, 65})
                    self.assertTrue(all(x1 <= x <= x2 and z1 <= z <= z2 for x, _, z, _ in goal))
                dx1, dz1, dx2, dz2 = house['dirt']
                self.assertLess(min(dx2 - dx1, dz2 - dz1) + 1, 5, 'the dirt is no place to build')
                self.assertGreaterEqual((dx2 - dx1 + 1) * (dz2 - dz1 + 1), 50, 'enough dirt for the walls and roof')
                self.assertTrue(dz2 < -16, 'clear of the ores')

    def test_generic_blocks_accept_every_kind_the_body_may_place(self):
        goal = cells(load('dirt_shelter'), (0, 63, 0), 0)
        accepts = {tuple(a) for *_, a in goal}
        self.assertIn(('minecraft:torch', 'minecraft:wall_torch'), accepts)
        self.assertIn(('#minecraft:beds',), accepts)
        self.assertIn(('#minecraft:dirt',), accepts)
        self.assertEqual(sum(1 for *_, a in goal if a == ['#minecraft:beds']), 2)

    def test_the_suite_task_hides_the_sheep_at_the_end_of_a_narrow_lane(self):
        task = next(t for t in load_tasks() if t['id'] == 'long_dirt_shelter')
        self.assertEqual((task['policy'], task['mobs'], task['house']), ('long-horizon-v1', {'sheep': 3}, {'plan': 'dirt_shelter', 'pasture': True}))
        self.assertLess(LANE_Z[1] - LANE_Z[0] + 1, 5, 'too narrow for the house')
        self.assertGreater(PASTURE[0], 26 + 64, 'out of sight from the trees')
        house = layout(random.Random(11), 1, 'dirt_shelter')
        self.assertTrue(any('summon' not in c and 'kill' in c for c in commands(house, True)))
        with self.assertRaises(ValueError):
            validate({**task, 'house': {'plan': 'large_house'}})
        initial = {'goal_blocks': [False] * 101}
        self.assertFalse(achieved(task, initial, {'goal_blocks': [True] * 100 + [False]}))
        self.assertTrue(achieved(task, initial, {'goal_blocks': [True] * 101}))


if __name__ == '__main__':
    unittest.main()
