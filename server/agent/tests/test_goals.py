"""目的の係（goals.py）。ゲームの係の中身（計画・段・直し方）はゲームの側の試験（server/minecraft/test/ciel.test.js）、
ゲームの MCP を通した流れは tests/test_game_env.py"""
import asyncio
import json
import unittest
import unittest.mock

import goals


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

    async def test_owner_request_replaces_infinite_mind_step_by_default(self):
        a = FakeAdapter([None, steps('B')], [{'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', 'ついてきて', {})
        await settle(self.runner)
        old = self.runner.goal
        result = await self.runner.start('mc', 'ツルハシを作る', {'make': 'stone_pickaxe'})
        await settle(self.runner)
        self.assertEqual(result['status'], 'started')
        self.assertEqual(old.status, 'stopped')
        self.assertEqual(self.runner.goal.status, 'done')
        self.assertEqual(self.runner.next, [])

    async def test_explicit_queue_waits_for_current_goal(self):
        a = FakeAdapter([None, steps('B')], [{'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '追従', {})
        await settle(self.runner)
        result = await self.runner.start('mc', '工作', {}, queue=True)
        self.assertEqual(result['status'], 'queued')
        await self.runner.stop()

    async def test_slow_old_plan_cannot_restart_after_new_goal(self):
        entered, release = asyncio.Event(), asyncio.Event()
        a = FakeAdapter([], [{'ok': True}])
        async def plan(goal):
            if goal.title == 'old':
                entered.set()
                await release.wait()
            return steps(goal.title)
        a.plan = plan
        self.runner.register('mc', a, 'マイクラ')
        old = asyncio.create_task(self.runner.start('mc', 'old', {}))
        await entered.wait()
        await asyncio.wait_for(self.runner.start('mc', 'new', {}), .5)
        await settle(self.runner)
        release.set()
        self.assertEqual((await old)['status'], 'cancelled')
        self.assertEqual(a.ran, ['new'])
        self.assertEqual(self.runner.goal.title, 'new')

    async def test_cancelled_repair_cannot_submit_another_old_step(self):
        entered, release = asyncio.Event(), asyncio.Event()
        a = FakeAdapter([steps('old'), steps('new')], [{'ok': False}, {'ok': True}])
        async def repair(goal, step, result):
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                # 遅い外部処理がキャンセルを飲んでも、世代の確認で止める。
                pass
            return steps('stale'), 'repair'
        a.repair = repair
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', 'old', {})
        await entered.wait()
        await self.runner.start('mc', 'new', {})
        release.set()
        await settle(self.runner)
        self.assertEqual(a.ran, ['old', 'new'])

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
        # 呼び名が読めなくても（名簿の読み違い）、目的は見せる（2026-11-07、目的の係ごと止まった）
        self.runner.presence = lambda: 'solo'
        self.runner.owner_name = lambda: (_ for _ in ()).throw(TypeError('not callable'))
        self.assertEqual(self.runner.state()['goal']['by_label'], '持ち主のお願い')

    async def test_unavailable_game_and_stop(self):
        self.runner.register('mc', FakeAdapter([], [], linked=False), 'マイクラ')
        self.assertEqual((await self.runner.start('mc', 'x', {}))['status'], 'unavailable')
        self.assertEqual((await self.runner.stop())['status'], 'no_goal')


    async def test_subgoal_runs_then_the_parent_step_is_retried(self):
        # 作業台を置く場所が無くて止まった件（2026-11-07）：小さな目標を作り、できたら止まった段からやり直す
        a = FakeAdapter([steps('丸石を集める', '石のツルハシを作る'), None],
                        [{'ok': True}, {'ok': False, 'reason': 'no_room'}, {'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '石のツルハシを作る', {'make': 'stone_pickaxe'})
        await settle(self.runner)
        self.assertIn('add_subgoal', self.said.lines[-1])
        r = await self.runner.add_subgoal('広い場所へ移る', {})
        self.assertEqual(r['path'], ['石のツルハシを作る', '広い場所へ移る'])
        self.assertEqual(r['for'], '石のツルハシを作る')
        await settle(self.runner)
        st = self.runner.state()
        self.assertEqual(st['path'], ['石のツルハシを作る', '広い場所へ移る'])
        self.assertEqual(st['goal']['title'], '石のツルハシを作る')
        self.assertIn('› 広い場所へ移る', self.runner.context())
        self.assertEqual(self.runner.finish_step(True)['status'], 'ok')   # 小さな目標は心が進める段
        await settle(self.runner)
        self.assertEqual(self.runner.goal.status, 'done')
        self.assertEqual(a.ran, ['丸石を集める', '石のツルハシを作る', '石のツルハシを作る'])
        self.assertIn('「広い場所へ移る」ができた', self.said.lines[-2])

    async def test_subgoals_nest_without_a_fixed_depth(self):
        a = FakeAdapter([steps('A'), steps('B'), steps('C'), steps('D')],
                        [{'ok': False, 'reason': 'x'}, {'ok': False, 'reason': 'x'}, {'ok': False, 'reason': 'x'},
                         {'ok': True}, {'ok': True}, {'ok': True}, {'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '吊り橋', {'make': 'bridge'})
        await settle(self.runner)
        for title, item in (('板', 'planks'), ('原木', 'log'), ('斧', 'axe')):
            r = await self.runner.add_subgoal(title, {'make': item})
            self.assertEqual(r['status'], 'started')
            await settle(self.runner)
        await settle(self.runner)
        await settle(self.runner)
        self.assertEqual(self.runner.goal.status, 'done')
        self.assertEqual(a.ran, ['A', 'B', 'C', 'D', 'C', 'B', 'A'])

    async def test_a_subgoal_equal_to_an_ancestor_is_refused(self):
        a = FakeAdapter([steps('作業台を置く'), steps('場所を空ける')],
                        [{'ok': False, 'reason': 'x'}, {'ok': False, 'reason': 'x'}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '作業台を置く', {'make': 'crafting_table'})
        await settle(self.runner)
        await self.runner.add_subgoal('場所を空ける', {})
        await settle(self.runner)
        r = await self.runner.add_subgoal('作業台を 置く', {'make': 'crafting_table'})
        self.assertEqual(r['reason'], 'loop')
        r = await self.runner.add_subgoal('場所を空ける', {})
        self.assertEqual(r['reason'], 'loop')

    async def test_subgoal_budget_asks_the_owner(self):
        a = FakeAdapter([steps('A')] + [steps('S')] * 3, [{'ok': False, 'reason': 'x'}] * 4)
        self.runner.register('mc', a, 'マイクラ')
        with unittest.mock.patch.object(goals, 'MAX_SUBGOALS', 2):
            await self.runner.start('mc', '目的', {'make': 'x'})
            await settle(self.runner)
            for i in range(2):
                self.assertEqual((await self.runner.add_subgoal(f'小{i}', {'make': f'y{i}'}))['status'], 'started')
                await settle(self.runner)
            r = await self.runner.add_subgoal('小2', {'make': 'y2'})
        self.assertEqual(r['reason'], 'budget')
        self.assertIn('持ち主に聞く', self.said.lines[-1])

    async def test_subgoals_that_change_nothing_stop_the_goal(self):
        a = FakeAdapter([steps('A')] + [steps('S')] * 2,
                        [{'ok': False, 'reason': 'x'}, {'ok': True}, {'ok': False, 'reason': 'x'}, {'ok': True},
                         {'ok': False, 'reason': 'x'}])
        a.snapshot = lambda: 'same'
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '目的', {'make': 'x'})
        await settle(self.runner)
        for i in range(2):
            await self.runner.add_subgoal(f'小{i}', {'make': f'y{i}'})
            await settle(self.runner)
            await settle(self.runner)
        self.assertEqual(self.runner.goal.status, 'paused')
        self.assertIn('変わらない', self.said.lines[-1])

    async def test_asking_the_same_paused_goal_again_replans(self):
        # 止まっている目的と同じ物の start_goal が「あとで」に並ぶだけで、止まったままだった（2026-11-07）
        a = FakeAdapter([steps('作る'), steps('集める', '作る')], [{'ok': False, 'reason': 'x'}, {'ok': True}, {'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '石のつるはしを作る', {'make': 'stone_pickaxe'})
        await settle(self.runner)
        self.assertEqual(self.runner.goal.status, 'paused')
        r = await self.runner.start('mc', '石のつるはしを作る', {'make': 'stone_pickaxe'})
        self.assertEqual(r['status'], 'started')
        await settle(self.runner)
        self.assertEqual(self.runner.goal.status, 'done')
        self.assertEqual(self.runner.next, [])

    async def test_stop_only_the_subgoal(self):
        a = FakeAdapter([steps('A'), None], [{'ok': False, 'reason': 'x'}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '目的', {'make': 'x'})
        await settle(self.runner)
        await self.runner.add_subgoal('移る', {})
        await settle(self.runner)
        r = await self.runner.stop(only_current=True)
        self.assertEqual(r['back_to'], '目的')
        self.assertEqual(self.runner.active.title, '目的')
        self.assertEqual(self.runner.goal.status, 'paused')

    async def test_app_buttons_stop_and_resume(self):
        import types
        a = FakeAdapter([steps('A', 'B')], [{'ok': False, 'reason': 'not_found'}, {'ok': True}, {'ok': True}])
        self.runner.register('mc', a, 'マイクラ')
        await self.runner.start('mc', '目的', {'make': 'x'})
        await settle(self.runner)
        pkt = lambda action: types.SimpleNamespace(topic='ciel.goal', data=json.dumps({'v': 1, 'type': 'goal.control', 'action': action}).encode())
        self.runner.on_data(types.SimpleNamespace(topic='ciel.other', data=b'{}'))
        self.assertEqual(self.runner.goal.status, 'paused')
        self.runner.on_data(pkt('resume'))
        await settle(self.runner)
        self.assertEqual(self.runner.goal.status, 'done')


class BodyBusyTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_running_body_step_is_known_and_a_replaced_step_is_told(self):
        # 係が原木を集めている途中で、心が板を作る道具を呼び、集める技が替わって目的が黙って止まった件（2026-11-07）
        said = Said()
        runner = goals.GoalRunner(said)
        gate = asyncio.Event()

        class Slow(FakeAdapter):
            async def run(self, goal, step):
                self.ran.append(step.label)
                await gate.wait()
                return self.results.pop(0)
        a = Slow([steps('原木を集める', 'ツルハシを作る')], [{'ok': False, 'reason': 'replaced'}])
        runner.register('mc', a, 'マイクラ')
        self.assertIsNone(runner.body_step())
        await runner.start('mc', '木のツルハシを作る', {})
        await asyncio.sleep(0)
        self.assertEqual(runner.body_step(), '原木を集める')   # 係が体を使っている
        gate.set()
        await settle(runner)
        self.assertEqual(runner.goal.status, 'paused')
        self.assertIsNone(runner.body_step())
        self.assertIn('ほかの頼みに替わったので止まって待っている', said.lines[-1])
        self.assertIn('resume_goal', said.lines[-1])

    async def test_a_step_left_to_the_mind_does_not_hold_the_body(self):
        runner = goals.GoalRunner(Said())
        a = FakeAdapter([None], [])
        runner.register('mc', a, 'マイクラ')
        await runner.start('mc', '広い場所へ移る', {})   # 係では分けられない：心に任せる段
        await asyncio.sleep(0)
        self.assertIsNone(runner.body_step())
        await runner.stop()


class OneBodyCallTest(unittest.TestCase):
    def test_only_one_moving_tool_per_reply(self):
        # 集めると作るを同時に呼び、体の技が取り合いになって両方失敗した件（2026-11-07）
        import mind
        from livekit.agents import llm
        def chunk(*names):
            calls = [llm.FunctionToolCall(name=n, arguments='{}', call_id=f'c{i}') for i, n in enumerate(names)]
            return llm.ChatChunk(id='x', delta=llm.ChoiceDelta(role='assistant', tool_calls=calls))
        taken = []
        moving = {'collect_blocks', 'craft_item'} | mind.GOAL_ONE   # ゲームの act の道具と、目的の道具（Mind.one_call_tools）
        out, dropped = mind.one_body_call(chunk('collect_blocks', 'look_around', 'craft_item'), taken, moving)
        self.assertEqual([c.name for c in out.delta.tool_calls], ['collect_blocks', 'look_around'])
        self.assertEqual(dropped, ['craft_item'])
        out, dropped = mind.one_body_call(chunk('start_goal'), taken, moving)   # 同じ返事の続きの chunk でも
        self.assertIsNone(out)
        self.assertEqual(dropped, ['start_goal'])
        out, dropped = mind.one_body_call(chunk('remember_about_speaker'), [], moving)
        self.assertEqual(dropped, [])


if __name__ == '__main__':
    unittest.main()
