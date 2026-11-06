"""目的の係（goals.py）と、マイクラの係（minecraft.py の Goals）"""
import asyncio
import json
import unittest

import goals
import minecraft


class Said:
    def __init__(self):
        self.lines = []

    def __call__(self, why, **kw):
        self.lines.append(kw['instructions'])


class FakeAdapter:
    """段の結果を順に返す係"""

    def __init__(self, plans, results, linked=True):
        self.plans, self.results, self.linked = list(plans), list(results), linked
        self.ran, self.stopped = [], 0

    def available(self):
        return self.linked

    async def plan(self, goal):
        return self.plans.pop(0)

    async def run(self, goal, step):
        self.ran.append(step.label)
        await asyncio.sleep(0)
        return self.results.pop(0)

    def check(self, goal, step, result):
        return bool(result.get('ok')), step.progress

    async def repair(self, goal, step, result):
        if result.get('reason') == 'missing_materials' and self.plans:
            return self.plans.pop(0), '材料が足りないので、計画を直した'
        return None

    def why(self, reason, result=None):
        return {'not_found': '見える所に無い', 'stopped': '止められた'}.get(reason, 'うまくいかなかった')

    async def stop(self):
        self.stopped += 1


def steps(*labels):
    return [{'kind': 'x', 'args': {}, 'label': label} for label in labels]


async def settle(runner):
    for _ in range(50):
        await asyncio.sleep(0)
        if runner._task is None or runner._task.done():
            return


class RunnerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.said, self.shown = Said(), []
        self.runner = goals.GoalRunner(self.said, publish=self.shown.append)

    async def test_steps_run_one_by_one_and_the_goal_is_done(self):
        a = FakeAdapter([steps('原木を集める', 'ツルハシを作る')], [{'ok': True}, {'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        r = await self.runner.start('mc', '木のツルハシを作る', {'make': 'wooden_pickaxe'})
        self.assertEqual(r['status'], 'started')
        self.assertEqual(r['steps'], ['原木を集める', 'ツルハシを作る'])
        await settle(self.runner)
        self.assertEqual(a.ran, ['原木を集める', 'ツルハシを作る'])
        self.assertEqual(self.runner.goal.status, 'done')
        self.assertEqual(self.said.lines[-1], '[目的「木のツルハシを作る」ができた]')
        self.assertIsNone(self.runner.context())
        self.assertEqual(self.shown[-1]['goal']['status'], 'done')

    async def test_missing_materials_are_repaired_without_the_mind(self):
        # 作業台に原木を使い、木のつるはしの原木が足りなかった件（2026-11-07）：計画し直して、心を通さずに続ける
        a = FakeAdapter([steps('木のツルハシを作る'), steps('原木を 1 個集める', '木のツルハシを作る')],
                        [{'ok': False, 'reason': 'missing_materials'}, {'ok': True}, {'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '木のツルハシを作る', {'make': 'wooden_pickaxe'})
        await settle(self.runner)
        self.assertEqual(a.ran, ['木のツルハシを作る', '原木を 1 個集める', '木のツルハシを作る'])
        self.assertEqual(self.runner.goal.status, 'done')
        self.assertIn('[目的「木のツルハシを作る」：材料が足りないので、計画を直した。続けている]', self.said.lines)
        self.assertEqual(self.runner.state()['changes'], ['材料が足りないので、計画を直した'])

    async def test_unrepairable_failure_pauses_and_asks_the_mind_then_resumes(self):
        a = FakeAdapter([steps('丸石を集める', '石のツルハシを作る')],
                        [{'ok': False, 'reason': 'not_found'}, {'ok': True}, {'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '石のツルハシを作る', {'make': 'stone_pickaxe'})
        await settle(self.runner)
        self.assertEqual(self.runner.goal.status, 'paused')
        self.assertIn('見える所に無い', self.runner.context())
        self.assertIn('resume_goal', self.said.lines[-1])
        self.assertEqual(self.runner.resume()['status'], 'resumed')
        await settle(self.runner)
        self.assertEqual(self.runner.goal.status, 'done')

    async def test_three_failures_ask_the_owner(self):
        a = FakeAdapter([steps('丸石を集める')], [{'ok': False, 'reason': 'not_found'}] * 3)
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '石のツルハシを作る', {'make': 'stone_pickaxe'})
        for _ in range(3):
            await settle(self.runner)
            if self.runner.goal.status == 'paused' and '持ち主に聞く' in self.said.lines[-1]:
                break
            self.runner.resume()
        self.assertIn('3 回うまくいかなかった', self.said.lines[-1])

    async def test_stopped_by_the_owner_pauses_without_counting_a_failure(self):
        a = FakeAdapter([steps('原木を集める')], [{'ok': False, 'reason': 'stopped'}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '木のツルハシを作る', {'make': 'wooden_pickaxe'})
        await settle(self.runner)
        g = self.runner.goal
        self.assertEqual((g.status, g.steps[0].status, g.steps[0].fails), ('paused', 'todo', 0))
        self.assertEqual(self.said.lines, [])   # 止めたのは持ち主。わざわざ知らせない

    async def test_next_goals_wait_and_start_after(self):
        a = FakeAdapter([steps('A'), steps('B')], [{'ok': True}, {'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '一つ目', {'make': 'x'})
        r = await self.runner.start('mc', '二つ目', {'make': 'y'}, by='ciel')
        self.assertEqual(r, {'status': 'queued', 'after': '一つ目'})
        self.assertIn('あとで：二つ目', self.runner.context())
        await settle(self.runner)
        await settle(self.runner)
        self.assertEqual(self.runner.goal.title, '二つ目')
        self.assertEqual(self.runner.state()['goal']['by_label'], 'シエルが決めた')

    async def test_mind_step_waits_for_finish_step(self):
        a = FakeAdapter([None], [])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '村を探す', {})
        await settle(self.runner)
        self.assertIn('自分で考えて進める', self.said.lines[-1])
        self.assertEqual(self.runner.goal.status, 'running')
        self.assertEqual(self.runner.finish_step(True)['status'], 'ok')
        await settle(self.runner)
        self.assertEqual(self.runner.goal.status, 'done')

    async def test_state_hides_the_owner_name_in_public(self):
        a = FakeAdapter([steps('A')], [{'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        self.runner.owner_name = lambda: 'ハカセ'
        await self.runner.start('mc', '木のツルハシを作る', {'make': 'x'})
        self.assertEqual(self.runner.state()['goal']['by_label'], 'ハカセのお願い')
        self.runner.presence = lambda: 'public'
        self.assertEqual(self.runner.state()['goal']['by_label'], '持ち主のお願い')
        self.assertEqual(self.runner.state()['goal']['game_label'], 'マイクラ')

    async def test_unavailable_game_and_stop(self):
        self.runner.register('mc', FakeAdapter([], [], linked=False), 'マイクラ')
        self.assertEqual((await self.runner.start('mc', 'x', {}))['status'], 'unavailable')
        self.assertEqual((await self.runner.stop())['status'], 'no_goal')


class FakeBody:
    def __init__(self, planned, done):
        self.linked, self.planned, self.done, self.asked = True, list(planned), list(done), []

    async def plan(self, item, count):
        return {'status': 'planned', 'steps': self.planned.pop(0)}

    async def run_skill(self, skill, args):
        self.asked.append((skill, args))
        return self.done.pop(0)

    async def stop(self):
        pass


class MinecraftGoalsTest(unittest.IsolatedAsyncioTestCase):
    async def test_plan_labels_gather_progress_and_repair(self):
        body = FakeBody([[{'kind': 'gather', 'item': 'oak_log', 'count': 3}, {'kind': 'craft', 'item': 'wooden_pickaxe', 'count': 1}],
                         [{'kind': 'gather', 'item': 'oak_log', 'count': 1}, {'kind': 'craft', 'item': 'wooden_pickaxe', 'count': 1}]],
                        [{'ok': True, 'note': {'gained': {'oak_log': 2}, 'short': 'not_found'}},
                         {'ok': True, 'note': {'found': 'oak_log'}},
                         {'ok': True, 'note': {'gained': {'oak_log': 1}}},
                         {'ok': False, 'reason': 'missing_materials', 'note': {'needs': {'oak_log': 1}}},
                         {'ok': True, 'note': {'gained': {'oak_log': 1}}},
                         {'ok': True, 'note': {'gained': {'wooden_pickaxe': 1}}}])
        said = Said()
        runner = goals.GoalRunner(said)
        runner.register('minecraft', minecraft.Goals(body), 'マイクラ')
        r = await runner.start('minecraft', '木のツルハシを作る', {'make': 'wooden_pickaxe', 'count': 1})
        self.assertEqual(r['steps'], ['オークの原木を 3 個集める', '木のツルハシを作る'])
        await settle(runner)
        # 2 本で見える所に無くなった → 探す段を足し、見つけてから残り 1 本だけ集める。作るときに足りなければ計画し直す
        self.assertEqual(body.asked[1], ('find', {'block': 'oak_log', 'how': 'auto'}))
        self.assertEqual(body.asked[2], ('collect', {'block': 'oak_log', 'count': 1}))
        self.assertEqual(runner.goal.status, 'done')
        self.assertEqual(runner.state()['changes'][0], 'オークの原木が見える所に無いので、探す段を足した')
        self.assertIn('材料が足りないので、計画を直した', runner.state()['changes'][1])


    async def test_not_found_adds_a_find_step_before_gathering(self):
        # 丸石が見える所に無く止まった件（2026-11-07）：先に探す段を足して、見つけてから集める
        body = FakeBody([[{'kind': 'gather', 'item': 'cobblestone', 'count': 3},
                          {'kind': 'craft', 'item': 'stone_pickaxe', 'count': 1}]],
                        [{'ok': False, 'reason': 'not_found', 'note': {'gained': {}}},
                         {'ok': True, 'note': {'found': 'stone'}},
                         {'ok': True, 'note': {'gained': {'cobblestone': 3}}},
                         {'ok': True, 'note': {'gained': {'stone_pickaxe': 1}}}])
        runner = goals.GoalRunner(Said())
        runner.register('minecraft', minecraft.Goals(body), 'マイクラ')
        await runner.start('minecraft', '石のツルハシを作る', {'make': 'stone_pickaxe'})
        await settle(runner)
        self.assertEqual([a[0] for a in body.asked], ['collect', 'find', 'collect', 'craft'])
        self.assertEqual(body.asked[1][1], {'block': 'cobblestone', 'how': 'auto'})
        self.assertEqual(runner.goal.status, 'done')
        self.assertEqual(runner.state()['changes'], ['丸石が見える所に無いので、探す段を足した'])


if __name__ == '__main__':
    unittest.main()
