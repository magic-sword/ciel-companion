import unittest
from server.benchmark.world import achieved


class MiningReturnTest(unittest.TestCase):
    def test_underground_gain_is_not_a_returned_harvest(self):
        task = dict(item='cobblestone', count=30, return_to_start=True)
        initial = dict(inventory={}, position=[0.5,64,0.5])
        self.assertFalse(achieved(task, initial, dict(inventory={'cobblestone':30},position=[0.5,61,0.5])))
        self.assertFalse(achieved(task, initial, dict(inventory={'cobblestone':29},position=[0.5,64,0.5])))
        self.assertTrue(achieved(task, initial, dict(inventory={'cobblestone':30},position=[0.5,64,0.5])))
