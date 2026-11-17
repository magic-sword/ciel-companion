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

    def test_capability_selection_has_a_user_facing_label(self):
        self.a.call_started('select', 'load_capabilities')
        self.assertEqual(self.a.state()['calls'][0]['label'], '使う機能を確認')

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
        self.assertEqual(len(self.a._tasks), 1)
        self.a.task_done('mc:6', 'oak_log を 3 個集める', False, '見える所に無い')
        s = self.a.state()
        self.assertEqual(self.a._tasks, {})
        self.assertEqual(s['log'][0]['text'], '体：oak_log を 3 個集める（できなかった：見える所に無い）')
        self.a.task_started('mc:7', '持ち主についていく')
        self.a.task_done('mc:7', '持ち主についていく', False, 'やめた', quiet=True)   # 止めたことは「できなかった」にしない
        self.assertEqual(len(self.a.state()['log']), 1)

    def test_body_snapshot_is_the_only_current_body_representation(self):
        self.a.set_body({'version': 1, 'phase': 'running', 'title': 'follow'})
        s = self.a.state()
        self.assertEqual(s['body']['title'], 'follow')
        for key in ('doing', 'tasks', 'goal_step'):
            self.assertNotIn(key, s)

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
    def test_controller_states_replace_dead_background_flag(self):
        a = activity.Activity(None)
        a.controller('continuation', enabled=True, phase='waiting')
        s = a.state()
        self.assertEqual(s['v'], 3)
        self.assertEqual(s['continuation'], dict(enabled=True, phase='waiting'))
        self.assertNotIn('initiative', s)
        self.assertNotIn('background_thinking', s)
        self.assertNotIn('detail_version', s)

    def test_heartbeat_advances_revision_without_state_changes(self):
        sent = []
        a = activity.Activity(sent.append)
        a.publish(force=True)
        a.publish(force=True)
        self.assertEqual([v['revision'] for v in sent], [1, 2])
        self.assertEqual(sent[0]['stream_id'], sent[1]['stream_id'])
        self.assertEqual(sent[1]['valid_for_s'], 6)

    def test_repeated_thinking_resets_the_timer_and_is_published(self):
        clock, sent = Clock(), []
        a = activity.Activity(sent.append, clock=clock)
        a.thinking('mind', 'research')
        clock.now += 5
        before = len(sent)
        a.thinking('mind', 'research')
        self.assertEqual(a.state()['mind_for'], 0)
        self.assertEqual(a.state()['thinking_origin'], 'research')
        self.assertGreater(len(sent), before)
        a.agent_state(types.SimpleNamespace(new_state='listening'))
        self.assertEqual(a.state()['thinking_origin'], '')


class BatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_close_stops_heartbeat_and_late_observers(self):
        sent = []
        a = activity.Activity(sent.append)
        a.start()
        await asyncio.sleep(0)
        await a.close()
        before = len(sent)
        a.controller('initiative', phase='disabled', reason='closed', outcome='')
        a.publish(force=True)
        self.assertEqual(len(sent), before)
        self.assertIsNone(a._pending)

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
