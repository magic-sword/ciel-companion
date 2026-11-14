import unittest

from server.benchmark.arm_compare import compare


def run(label_blocked, trials, **manifest):
    return {'label': 'blocked !obtainItem' if label_blocked else 'default',
            'manifest': {'policy': 'long-horizon-v1', 'model_id': 'm', **manifest},
            'trials': {(t['task'], t['seed'], 0): t for t in trials}}


def trial(task, seed, status, seconds=None, calls=None, milestones=None, **kw):
    return {'task': task, 'seed': seed, 'status': status, 'time_to_goal_seconds': seconds,
            'metrics': {'llm_calls': calls}, 'progress': {'milestones': milestones}, **kw}


class ArmCompareTest(unittest.TestCase):
    def test_only_trials_scored_in_every_arm_are_paired(self):
        base = run(True, [trial('t', 11, 'failed', None, 20, 0.5, reason='time_budget'), trial('t', 12, 'passed', 90, 12, 1.0),
                          trial('t', 13, 'infrastructure_error')])
        cand = run(False, [trial('t', 11, 'passed', 60, 3, 1.0), trial('t', 12, 'passed', 50, 2, 1.0),
                           trial('t', 13, 'passed', 40, 2, 1.0)])
        result = compare([base, cand])
        self.assertEqual([p['seed'] for p in result['paired']], [11, 12])
        self.assertEqual(result['unscored'], {'blocked !obtainItem': 1, 'default': 0})
        rows = {r['arm']: r for r in result['summary']}
        self.assertEqual((rows['blocked !obtainItem']['passed'], rows['blocked !obtainItem']['mean_seconds_passed']), (1, 90))
        self.assertEqual((rows['default']['passed'], rows['default']['mean_llm_calls'], rows['default']['mean_milestones']), (2, 2.5, 1.0))
        self.assertEqual(result['mismatched_conditions'], {})

    def test_different_conditions_are_reported(self):
        result = compare([run(True, [], model_id='a'), run(False, [], model_id='b')])
        self.assertEqual(result['mismatched_conditions'], {'model_id': ['a', 'b']})


if __name__ == '__main__':
    unittest.main()
