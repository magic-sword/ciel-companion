"""いまのシエル（activity.py）：心・道具・体の、いまの動きをアプリへ送る"""
import asyncio
import json
import types
import unittest

import activity


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def executed(*pairs):
    calls = [types.SimpleNamespace(call_id=cid, name=name) for cid, name, _ in pairs]
    outs = [types.SimpleNamespace(output=json.dumps(out, ensure_ascii=False), is_error=False) for _, _, out in pairs]
    return types.SimpleNamespace(function_calls=calls, function_call_outputs=outs)


class ActivityTest(unittest.TestCase):
    def setUp(self):
        self.sent, self.clock = [], Clock()
        self.a = activity.Activity(self.sent.append, clock=self.clock)
        self.a.titles['minecraft_craft_item'] = '作る'

    def test_a_tool_is_waiting_until_its_result_comes_back(self):
        self.a.thinking('mind')
        self.a.call_started('c1', 'minecraft_craft_item')
        self.clock.now += 3
        s = self.a.state()
        self.assertEqual((s['mind'], s['who']), ('thinking', 'mind'))
        self.assertEqual(s['calls'], [{'label': '作る', 'for_s': 3.0}])
        self.a.tools_executed(executed(('c1', 'minecraft_craft_item',
                                        {'status': 'error', 'reason': 'missing_materials', 'why': '材料が足りない（cobblestone×3）'})))
        s = self.a.state()
        self.assertEqual(s['calls'], [])
        self.assertEqual(s['log'][0]['text'], '作る：始めなかった（材料が足りない（cobblestone×3））')
        self.assertEqual(s['log'][0]['kind'], 'error')

    def test_body_tasks_last_until_the_end_notice(self):
        self.a.task_started('mc:6', 'oak_log を 3 個集める')
        self.clock.now += 12
        self.assertEqual(self.a.state()['tasks'], [{'title': 'oak_log を 3 個集める', 'for_s': 12.0}])
        self.a.task_done('mc:6', 'oak_log を 3 個集める', False, '見える所に無い')
        s = self.a.state()
        self.assertEqual(s['tasks'], [])
        self.assertEqual(s['log'][0]['text'], '体：oak_log を 3 個集める（できなかった：見える所に無い）')
        self.a.task_started('mc:7', '持ち主についていく')
        self.a.task_done('mc:7', '持ち主についていく', False, 'やめた', quiet=True)   # 止めたことは「できなかった」にしない
        self.assertEqual(len(self.a.state()['log']), 1)

    def test_body_doing_goal_step_and_states(self):
        self.a.body_doing = lambda: '持ち主についていく'
        self.a.goal_step = lambda: 'オークの原木を 2 個集める'
        self.a.agent_state(types.SimpleNamespace(new_state='speaking'))
        s = self.a.state()
        self.assertEqual((s['doing'], s['goal_step'], s['mind'], s['who']),
                         ('持ち主についていく', 'オークの原木を 2 個集める', 'speaking', ''))

    def test_waiting_results_are_logged_as_waiting(self):
        self.a.tools_executed(executed(('c2', 'minecraft_collect_blocks', {'status': 'goal_running', 'why': '目的の係が「原木」を体で進めている'})))
        self.assertEqual(self.a.state()['log'][0]['kind'], 'wait')
        self.assertIn('目的の係が', self.a.state()['log'][0]['text'])

    def test_publish_only_when_something_changed(self):
        self.a.publish()
        self.a.publish()
        self.assertEqual(len(self.sent), 1)
        self.clock.now += 5   # 経った秒数だけでは送らない
        self.a.publish()
        self.assertEqual(len(self.sent), 1)
        self.a.log('心へ：うながした', 'wait')   # ループの外ではすぐ送る
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[-1]['type'], 'activity.state')


class DetailTest(unittest.TestCase):
    def test_background_timer_and_cleanup(self):
        clock, sent = Clock(), []
        a = activity.Activity(sent.append, clock=clock)
        a.background(True)
        clock.now += 4
        self.assertTrue(a.state()['background_thinking'])
        self.assertEqual(a.state()['background_for'], 4)
        self.assertEqual(a.state()['detail_version'], 1)
        a.publish()
        before = len(sent)
        clock.now += 3
        a.publish()
        self.assertEqual(len(sent), before)
        a.background(False)
        self.assertFalse(a.state()['background_thinking'])

    def test_repeated_thinking_resets_the_timer_and_is_published(self):
        clock, sent = Clock(), []
        a = activity.Activity(sent.append, clock=clock)
        a.thinking('mind', 'initiative')
        clock.now += 5
        before = len(sent)
        a.thinking('mind', 'initiative')
        self.assertEqual(a.state()['mind_for'], 0)
        self.assertEqual(a.state()['thinking_origin'], 'initiative')
        self.assertGreater(len(sent), before)
        a.agent_state(types.SimpleNamespace(new_state='listening'))
        self.assertEqual(a.state()['thinking_origin'], '')


class BatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_changes_close_together_are_sent_once(self):
        sent = []
        a = activity.Activity(sent.append)
        a.thinking('mind')
        a.call_started('c1', 'x')
        a.log('ひとこと')
        self.assertEqual(sent, [])
        await asyncio.sleep(activity.PUBLISH_GAP + 0.1)
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(sent[0]['calls']), 1)


if __name__ == '__main__':
    unittest.main()
