"""Navigation scoring cannot pass from promises, proximity alone, or stale commands."""
import asyncio
import copy
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmark.navigation import evaluate_navigation, validate_navigation
from benchmark.run import Trace, load_tasks
from benchmark.world import World


class NavigationTest(unittest.IsolatedAsyncioTestCase):
    async def trial(self, *, task_id='come_here', active=False, done=False, old=False, stop_ack=True,
                    locator_known=False, no_hint=False, move=False, resume=False, reply=False):
        task = copy.deepcopy(next(t for t in load_tasks() if t['id'] == task_id))
        task['budget'] = {'seconds': 40}
        now = [0]
        target = [task['navigation']['targets'][0]]
        stopping = [False]
        moves = []
        skill = 'follow' if task_id == 'follow_owner' else 'come'
        class Driver:
            goal_state = {}
            async def submit(self, task): pass
            async def stop(self, task): stopping[0] = True
            def events(self): return []
            def report_complete(self, after): return reply
        class World:
            def snapshot(self, items):
                pos = list(target[0]) if move else [0, 64, 0]
                if stopping[0] and resume: pos[0] += now[0]
                return {'position': pos, 'target_position': target[0], 'inventory': {}, 'health': 20, 'deaths': 0}
            def move_target(self, p): target[0] = p; moves.append(p)
        def observe():
            stopped = stopping[0] and stop_ack
            return {'target_entity_known': locator_known, 'hint': None if no_hint else {'source': 'azimuth'},
                    'body': {'current': {'skill': skill, 'phase': 'running'} if active and not stopped else None,
                             'last': {'skill': skill, 'phase': 'cancelled' if stopped else 'succeeded',
                                      'since': (time.time() + (-10 if old else 10)) * 1000,
                                      'result': {'reason': 'stopped' if stopped else None}}
                             if done or stopped else None}}
        async def sleep(seconds): now[0] += seconds
        with tempfile.TemporaryDirectory() as d:
            trace = Trace(Path(d) / 'trace.jsonl')
            result = await evaluate_navigation(task, World(), Driver(), trace, {'inventory': {}, 'position': [0,64,0]}, seconds=40,
                max_llm=30, max_calls=80, poll=1, stable_seconds=2, clock=lambda: now[0], sleep=sleep, observe=observe)
        return result, moves

    async def test_promise_and_proximity_are_not_completion(self):
        result, _ = await self.trial(move=True)
        self.assertEqual(result['reason'], 'first_action_timeout')

    async def test_spoken_reply_is_not_a_completion_report(self):
        result, _ = await self.trial(reply=True)
        self.assertTrue(result['reply_observed'])
        self.assertIsNone(result['completion_observed'])
        self.assertFalse(result['body_completion_confirmed'])

    async def test_old_success_does_not_complete_a_new_trial(self):
        result, _ = await self.trial(move=True, done=True, old=True)
        self.assertEqual(result['status'], 'failed')

    async def test_arrival_requires_distance_and_current_command_success(self):
        result, _ = await self.trial(move=True, done=True)
        self.assertEqual(result['reason'], 'arrived_and_stayed')
        result, _ = await self.trial(move=False, done=True)
        self.assertEqual(result['reason'], 'false_completion')

    async def test_follow_requires_every_stage_and_stop_stability(self):
        result, moves = await self.trial(task_id='follow_owner', active=True, move=True)
        self.assertEqual(result['reason'], 'followed_stopped_and_stayed')
        self.assertEqual(len(moves), 2)
        self.assertEqual(len(result['navigation_stages']), 3)
        result, _ = await self.trial(task_id='follow_owner', active=True, move=True, stop_ack=False)
        self.assertEqual(result['reason'], 'did_not_stop')

    async def test_resuming_after_stop_is_failure(self):
        result, _ = await self.trial(task_id='follow_owner', active=True, move=True, resume=True)
        self.assertEqual(result['reason'], 'resumed_after_stop')

    async def test_locator_precondition_cannot_be_silently_relaxed(self):
        for kw in [{'locator_known': True}, {'no_hint': True}]:
            with self.assertRaisesRegex(RuntimeError, 'Locator fixture'):
                await self.trial(task_id='come_here_locator', **kw)
        task = next(t for t in load_tasks() if t['id'] == 'come_here_azimuth')
        with self.assertRaisesRegex(RuntimeError, 'Locator fixture'):
            await evaluate_navigation(task, None, None, None, {}, seconds=120, max_llm=30, max_calls=80,
                observe=lambda: {'target_entity_known':False,'hint':{'source':'chunk'}})

    def test_mismatched_body_operation_and_out_of_bounds_target_are_rejected(self):
        task = copy.deepcopy(next(t for t in load_tasks() if t['id'] == 'come_here'))
        task['body_call']['name'] = 'minecraft_follow_me'
        with self.assertRaises(ValueError): validate_navigation(task)
        task['navigation']['targets'][0][0] = 10000
        with self.assertRaises(ValueError): validate_navigation(task)

    def test_owner_mutation_keeps_marker_and_lease_checks(self):
        class Rcon:
            def command(self, text): return 'not a benchmark'
        world = World(Rcon())
        with self.assertRaisesRegex(RuntimeError, 'Not a marked'): world.move_target([20, 64, 0])

    def test_corridor_is_bounded_and_owner_is_a_fixture_not_an_agent_tool(self):
        commands = []
        class Rcon:
            def command(self, text):
                commands.append(text)
                return 'meta has: "ciel-benchmark-v1"' if text == 'data get storage ciel_benchmark:meta suite' else 'ok'
        world = World(Rcon())
        world.lease = 'test'
        world.scalar = lambda *a, **kw: 1
        task = next(t for t in load_tasks() if t['id'] == 'come_here_azimuth')
        world.reset(task, 11)
        self.assertIn('tp Bench_Owner 384 64 0', commands)
        for command in commands:
            if command.startswith('fill '):
                xyz = list(map(int, command.split()[1:7]))
                size = 1
                for i in range(3): size *= abs(xyz[i + 3] - xyz[i]) + 1
                self.assertLessEqual(size, 32768)

    async def test_stale_fixture_position_is_not_started(self):
        from benchmark.navigation import prepare_navigation
        task = next(t for t in load_tasks() if t['id'] == 'come_here')
        observations = iter([
            {'target_entity_known': True, 'target_entity_position': {'x': 0, 'y': 64, 'z': 0}},
            {'target_entity_known': True, 'target_entity_position': {'x': 20.5, 'y': 64, 'z': 0.5}},
        ])
        with patch('benchmark.navigation.read_body_observation', side_effect=lambda: next(observations)) as read:
            await prepare_navigation(task, {'target_position': [20.5, 64, 0.5]})
        self.assertEqual(read.call_count, 2)
