"""マイクラの体へつなぐ係（minecraft.py）と、心の振り分け・道具（mind.py、tools/minecraft.py）"""
import asyncio
import json
import types
import unittest
from unittest import mock

from livekit.agents import llm

import mind
import minecraft
import tools
from conversation import Conversation
from tools.minecraft import BODY_TOOLS


def state(**kw):
    s = {'type': 'state', 'connected': True, 'pos': {'x': 1, 'y': 64, 'z': 2}, 'health': 20, 'food': 20,
         'time': 14000, 'night': True, 'raining': False, 'held': 'iron_sword',
         'inventory': {'oak_log': 3, 'iron_sword': 1}, 'players': [{'name': 'Hakase', 'distance': 2.1}],
         'hostiles': [{'name': 'zombie', 'distance': 6.0}], 'doing': {'id': 1, 'skill': 'follow', 'args': {}}}
    s.update(kw)
    return s


class Said:
    def __init__(self):
        self.calls = []

    def __call__(self, why, *, settle, instructions):
        self.calls.append((why, settle, instructions))

    def lines(self):
        return [c[2].split('\n')[0] for c in self.calls]


def linked_body(said=None, diary=None):
    body = minecraft.Body('ws://test', said or Said(), diary=diary)
    body.on_message(json.dumps({'v': 1, 'type': 'hello', 'owner': 'Hakase', 'state': state()}))
    return body


class BodyTest(unittest.TestCase):
    def test_context_shows_what_ciel_sees(self):
        text = linked_body().context()
        self.assertTrue(text.startswith('[マイクラの様子]'))
        self.assertIn('体力 20/20', text)
        self.assertIn('持ち物 oak_log×3、iron_sword×1', text)
        self.assertIn('していること ついていく', text)
        self.assertIn('夜（敵が出る）', text)
        self.assertIn('Hakase（持ち主） 2.1 ブロック', text)
        self.assertIn('zombie 6.0 ブロック', text)

    def test_context_when_not_linked_or_not_in_the_world(self):
        body = minecraft.Body('ws://test', Said())
        self.assertIn('つながっていない', body.context())
        body = linked_body()
        body.on_message(json.dumps({'v': 1, 'type': 'state', 'connected': False}))
        self.assertIn('入っていない', body.context())
        self.assertIsNone(minecraft.Body('', Said()).context())   # つなぐ先が無ければ、様子も渡さない

    def test_owner_far_away_is_said(self):
        body = linked_body()
        body.on_message(json.dumps(state(players=[])))
        self.assertIn('Hakase（持ち主）は近くにいない', body.context())

    def test_only_events_worth_saying_are_said(self):
        said = Said()
        body = linked_body(said)
        for e in ({'kind': 'hurt', 'amount': 1, 'health': 19}, {'kind': 'night'}, {'kind': 'chat', 'who': 'x', 'text': 'y'},
                  {'kind': 'defend', 'name': 'zombie'}, {'kind': 'safe'}, {'kind': 'player_joined', 'name': 'x'}):
            body.on_message(json.dumps({'v': 1, 'type': 'event', **e}))
        self.assertEqual(said.calls, [])
        body.on_message(json.dumps({'v': 1, 'type': 'event', 'kind': 'hurt', 'amount': 4.5, 'health': 15.5}))
        body.on_message(json.dumps({'v': 1, 'type': 'event', 'kind': 'defeated', 'name': 'zombie'}))
        body.on_message(json.dumps({'v': 1, 'type': 'event', 'kind': 'flee', 'from': 'creeper', 'health': 12}))
        self.assertEqual(said.lines(), ['[マイクラ：4.5 のダメージを受けた（体力 15.5/20）]', '[マイクラ：zombieを倒した]',
                                        '[マイクラ：creeperから逃げている（体力 12/20）]'])
        self.assertTrue(all(why == 'game' for why, _, _ in said.calls))
        self.assertIn('[マイクラの様子]', said.calls[0][2])   # 知らせには、今の様子も添える
        self.assertEqual(said.calls[0][1], minecraft.URGENT_SETTLE)

    def test_same_kind_is_said_once_in_a_while(self):
        said = Said()
        body = linked_body(said)
        for _ in range(3):
            body.on_message(json.dumps({'v': 1, 'type': 'event', 'kind': 'defeated', 'name': 'zombie'}))
        self.assertEqual(len(said.calls), 1)

    def test_diary_keeps_each_happening_once(self):
        diary = mock.Mock()
        body = linked_body(diary=diary)
        for _ in range(3):
            body.on_message(json.dumps({'v': 1, 'type': 'event', 'kind': 'defeated', 'name': 'zombie'}))
        body.on_message(json.dumps({'v': 1, 'type': 'event', 'kind': 'died'}))
        self.assertEqual([c.args for c in diary.add.call_args_list],
                         [('minecraft', 'マイクラで zombie を倒した'), ('minecraft', 'マイクラで倒れた')])

    def test_done_is_said_when_gathered_or_failed(self):
        said = Said()
        body = linked_body(said)
        body._skills.update({7: 'collect', 8: 'follow', 9: 'come', 10: 'follow'})
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 7, 'ok': True, 'note': {'gained': {'oak_log': 3}}}))
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 8, 'ok': False, 'reason': 'player_not_visible'}))
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 9, 'ok': True}))   # 着いたのは見えるので言わない
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 10, 'ok': False, 'reason': 'stopped'}))   # 止めた
        self.assertEqual(said.lines(), ['[マイクラ：頼まれたものを集め終えた（oak_log×3）]',
                                        '[マイクラ：頼まれた「ついていく」の相手が見えなくなった（遠い・別の場所にいる）]'])


class FakeWs:
    def __init__(self, body, answer):
        self.body, self.answer, self.sent = body, answer, []

    async def send(self, raw):
        m = json.loads(raw)
        self.sent.append(m)
        if self.answer and m['type'] == 'do':
            self.body.on_message(json.dumps({'v': 1, 'type': self.answer, 'id': m['id'], 'reason': 'unknown_skill'}))


class BodyDoTest(unittest.IsolatedAsyncioTestCase):
    async def test_do_returns_when_started(self):
        body = linked_body()
        body._ws = FakeWs(body, 'started')
        self.assertEqual(await body.do('follow'), {'status': 'started'})
        self.assertEqual(body._ws.sent[0], {'v': 1, 'type': 'do', 'id': 1, 'skill': 'follow', 'args': {}})

    async def test_do_reports_errors_and_silence(self):
        body = linked_body()
        body._ws = FakeWs(body, 'error')
        self.assertEqual(await body.do('dance'), {'status': 'error', 'reason': 'unknown_skill'})
        body._ws = FakeWs(body, None)
        with mock.patch.object(minecraft, 'START_TIMEOUT', 0.05):
            self.assertEqual(await body.do('follow'), {'status': 'no_answer'})

    async def test_unlinked_body_does_nothing(self):
        body = minecraft.Body('ws://test', Said())
        self.assertEqual(await body.do('follow'), {'status': 'unavailable'})
        self.assertEqual(await body.stop(), {'status': 'unavailable'})


def ctx_with(text):
    ctx = llm.ChatContext()
    ctx.add_message(role='system', content='会話の指示')
    ctx.add_message(role='user', content=text)
    return ctx


class MindGameTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('clock.now_line', return_value='[今：朝]')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_game_requests_go_to_the_mind_only_while_linked(self):
        body = linked_body()
        m = mind.Mind(Conversation(), body=body)
        self.assertEqual(m.route(ctx_with('ついてきて'), {'seconds': 1.0}), 'mind')
        self.assertEqual(m.route(ctx_with('ちょっと待って'), {'seconds': 1.0}), 'mind')
        self.assertEqual(m.route(ctx_with('あれ、ついてくるの止められないかな？'), {'seconds': 1.0}), 'mind')
        self.assertEqual(m.route(ctx_with('うまくできてる'), {'seconds': 1.0}), 'talker')
        body.linked = False
        self.assertEqual(m.route(ctx_with('ついてきて'), {'seconds': 1.0}), 'talker')
        self.assertEqual(mind.Mind(Conversation()).route(ctx_with('ついてきて'), {'seconds': 1.0}), 'talker')

    def test_body_tools_only_while_linked(self):
        body = linked_body()
        m = mind.Mind(Conversation(), body=body)
        ids = lambda: {t.id for t in m.tools_for(ctx_with('ついてきて'), tools.TOOLS)}
        self.assertTrue(set(BODY_TOOLS) <= ids())
        body.linked = False
        self.assertFalse(set(BODY_TOOLS) & ids())

    def test_the_state_goes_to_the_talker_and_the_mind(self):
        m = mind.Mind(Conversation(), body=linked_body())
        ctx = ctx_with('今どんな感じ？')
        for built in (m.build(ctx, turn={}), m.build(ctx, talker_instructions='短い指示', turn={})):
            self.assertTrue(any('[マイクラの様子]' in (i.text_content or '') for i in built.items))

    def test_moving_the_body_is_not_for_comments(self):
        allowed = {t.id for t in tools.for_comments(tools.TOOLS)}
        self.assertNotIn('follow_me', allowed)
        self.assertNotIn('come_here', allowed)
        self.assertNotIn('stop_moving', allowed)
        self.assertIn('look_around', allowed)


class ToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_tools_without_a_body_say_unavailable(self):
        ctx = types.SimpleNamespace(userdata=tools.State())
        for fn in tools.minecraft.TOOLS:
            result = await fn(ctx)
            self.assertEqual(json.loads(result)['status'], 'unavailable', fn.id)


if __name__ == '__main__':
    unittest.main()
