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
         'hostiles': [{'name': 'zombie', 'distance': 6.0}], 'doing': {'id': 1, 'skill': 'follow', 'args': {}},
         'blocks': {'oak_log': 12, 'coal_ore': 3}}
    s.update(kw)
    return s


class Said:
    def __init__(self):
        self.calls = []

    def __call__(self, why, *, settle, instructions, merge=False):
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
        self.assertIn('近くのブロック：oak_log×12、coal_ore×3', text)

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
        self.assertEqual(said.calls[0][1], minecraft.URGENT_SETTLE)

    def test_on_a_tree_is_shown_and_said(self):
        said = Said()
        body = linked_body(said)
        body.on_message(json.dumps(state(footing={'on': 'oak_leaves', 'height': 12})))
        self.assertIn('足元：oak_leaves（木の上。地面から約 12 ブロック', body.context())
        body.on_message(json.dumps({'v': 1, 'type': 'event', 'kind': 'on_tree', 'on': 'oak_leaves', 'height': 12}))
        self.assertEqual(said.lines(), ['[マイクラ：木の上にいる（足元：oak_leaves、地面から約 12 ブロック）。ふつうに歩いては降りられない]'])
        body._asked[5] = '足元を掘って降りる'
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 5, 'ok': True, 'note': {'descended': 12, 'dug': 9}}))
        self.assertEqual(said.lines()[-1], '[マイクラ：頼まれた「足元を掘って降りる」ができた（12 ブロック降りた）。目的の途中なら、次の段の道具を呼んで続ける]')

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
        body._asked.update({7: 'oak_log を 3 個集める', 8: '持ち主についていく', 9: '持ち主のそばへ行く', 10: '持ち主についていく'})
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 7, 'ok': True, 'note': {'gained': {'oak_log': 3}}}))
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 8, 'ok': False, 'reason': 'player_not_visible'}))
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 9, 'ok': True}))   # 着いたのは見えるので言わない
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 10, 'ok': False, 'reason': 'stopped'}))   # 止めた
        self.assertEqual(said.lines(), [
            '[マイクラ：頼まれた「oak_log を 3 個集める」ができた（oak_log×3）。目的の途中なら、次の段の道具を呼んで続ける]',
            '[マイクラ：頼まれた「持ち主についていく」ができなかった。理由：相手が見えない（遠い・別の場所にいる）。'
            'できたところ：なし。同じ頼みでうまくいかなかったのは 1 回目]'])

    def test_failures_tell_the_reason_the_progress_and_how_many_times(self):
        said = Said()
        body = linked_body(said)
        name = 'oak_log を 10 個集める'
        body._asked.update({1: name, 2: name, 3: name, 4: name})
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 1, 'ok': True,
                                    'note': {'gained': {'oak_log': 3}, 'wanted': 10, 'short': 'no_path'}}))
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 2, 'ok': False, 'reason': 'no_path',
                                    'note': {'gained': {}, 'wanted': 10}}))
        self.assertEqual(said.lines(), [
            f'[マイクラ：頼まれた「{name}」は途中まで（できたところ：oak_log×3）。残りの理由：そこまでの道が見つからない'
            '（遠い・高い・水や崖の向こう）。同じ頼みでうまくいかなかったのは 1 回目]',
            f'[マイクラ：頼まれた「{name}」ができなかった。理由：そこまでの道が見つからない（遠い・高い・水や崖の向こう）。'
            'できたところ：なし。同じ頼みでうまくいかなかったのは 2 回目]'])
        # できたら数え直す。体のエラーは、その中身も添える
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 3, 'ok': True, 'note': {'gained': {'oak_log': 10}}}))
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 4, 'ok': False, 'reason': 'error', 'detail': 'Digging aborted'}))
        self.assertIn('うまくいかなかった（体のエラー：Digging aborted）', said.lines()[-1])
        self.assertIn('1 回目', said.lines()[-1])


class BoardTest(unittest.IsolatedAsyncioTestCase):
    async def test_skills_become_cards_and_are_not_taken_twice(self):
        import board
        tasks = board.Board()
        body = minecraft.Body('ws://test', Said(), board=tasks)
        body.on_message(json.dumps({'v': 1, 'type': 'hello', 'owner': 'Hakase', 'state': state()}))
        body._ws = FakeWs(body, 'started')
        self.assertEqual(await body.do('collect', {'block': 'oak_log', 'count': 10}), {'status': 'started'})
        self.assertEqual(await body.do('collect', {'block': 'oak_log', 'count': 10}), {'status': 'already_doing'})
        self.assertIn('oak_log を 10 個集める：実行中', tasks.context())
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 1, 'ok': True, 'note': {'gained': {'oak_log': 10}}}))
        self.assertIn('oak_log を 10 個集める：完了', tasks.context())
        await body.do('follow')
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 2, 'ok': False, 'reason': 'player_not_visible'}))
        self.assertIn('持ち主についていく：失敗', tasks.context())
        self.assertIn('相手が見えない', tasks.context())


def packet(on, topic='ciel.game'):
    return types.SimpleNamespace(topic=topic, data=json.dumps({'v': 1, 'type': 'game.link', 'on': on}).encode('utf-8'))


class LinkTest(unittest.IsolatedAsyncioTestCase):
    async def test_app_switch_links_and_unlinks(self):
        shown = []
        body = minecraft.Body('ws://test', Said(), notify=shown.append)
        with mock.patch.object(minecraft.Body, '_run', new=mock.AsyncMock()):
            body.on_data(packet(True, topic='ciel.style'))   # ほかの知らせでは動かない
            self.assertIsNone(body._task)
            body.on_data(packet(True))
            self.assertIsNotNone(body._task)
            self.assertEqual(shown[-1], {'v': 1, 'type': 'game.state', 'linked': False, 'in_world': False, 'reason': 'connecting'})
            body.on_message(json.dumps({'v': 1, 'type': 'hello', 'owner': 'Hakase', 'state': state()}))
            self.assertEqual(shown[-1]['linked'], True)
            self.assertEqual(shown[-1]['in_world'], True)
            n = len(shown)
            body.on_message(json.dumps(state()))   # 変わらなければ知らせない
            self.assertEqual(len(shown), n)
            body.linked = False
            await body.close()
            self.assertEqual(shown[-1]['reason'], 'off')

    async def test_busy_is_shown(self):
        shown = []
        body = minecraft.Body('ws://test', Said(), notify=shown.append)
        body.on_message(json.dumps({'v': 1, 'type': 'busy'}))
        self.assertEqual(shown[-1]['reason'], 'busy')

    def test_server_without_a_body_refuses(self):
        shown = []
        on_data = minecraft.refuse(shown.append)
        on_data(packet(False))
        self.assertEqual(shown, [])
        on_data(packet(True))
        self.assertEqual(shown[-1]['reason'], 'unavailable')


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

    async def test_refusal_before_starting_tells_why(self):
        # 体が始める前に断ったら（道具が無い・名前が違う）、理由の文を道具の返事に入れる。心はその場で正直に言える
        body = linked_body()

        class Refuse(FakeWs):
            async def send(self, raw):
                m = json.loads(raw)
                self.body.on_message(json.dumps({'v': 1, 'type': 'error', 'id': m['id'], 'reason': 'needs_tool',
                                                 'note': {'tool': 'wooden_pickaxe'}}))
        body._ws = Refuse(body, None)
        r = await body.do('collect', {'block': 'stone', 'count': 3})
        self.assertEqual(r['status'], 'error')
        self.assertIn('掘る道具が無い', r['why'])
        self.assertIn('wooden_pickaxe', r['why'])
        self.assertFalse(body._cards)

    def test_missing_materials_are_told(self):
        said = []
        body = linked_body(lambda why, **kw: said.append(kw['instructions']))
        body._asked[5] = 'wooden_pickaxe を 1 個作る'
        body.on_message(json.dumps({'v': 1, 'type': 'done', 'id': 5, 'ok': False, 'reason': 'missing_materials',
                                    'note': {'needs': {'stick': 2}}}))
        self.assertIn('材料が足りない（足りない物：stick×2）', said[-1])

    async def test_look_hands_the_view_to_the_eyes(self):
        import base64
        import eyes
        body = linked_body()
        body.eyes = eyes.Eyes(Said())
        jpeg = eyes.MAGIC[0][0] + b'0' * 50

        class LookWs(FakeWs):
            async def send(self, raw):
                m = json.loads(raw)
                self.sent.append(m)
                self.body.on_message(json.dumps({'v': 1, 'type': 'seen', 'id': m['id'], 'facing': 'west',
                                                 'jpeg': base64.b64encode(jpeg).decode()}))
        body._ws = LookWs(body, None)
        self.assertEqual(await body.look(), {'status': 'seen', 'view': 1, 'facing': '西'})
        self.assertEqual(body._ws.sent[0], {'v': 1, 'type': 'look', 'id': 1})
        pic = body.eyes.pictures[-1]
        self.assertEqual(pic.source, eyes.MINECRAFT)
        self.assertIn('西を向いている', pic.label())
        # 口には頼まない（道具の返事の続きで見る）
        self.assertEqual(body.eyes.say.calls, [])

    async def test_look_errors_and_silence(self):
        import eyes
        body = linked_body()
        body.eyes = eyes.Eyes(Said())

        class ErrWs(FakeWs):
            async def send(self, raw):
                m = json.loads(raw)
                self.body.on_message(json.dumps({'v': 1, 'type': 'error', 'id': m['id'], 'reason': 'eye_unavailable'}))
        body._ws = ErrWs(body, None)
        self.assertEqual(await body.look(), {'status': 'error', 'reason': 'eye_unavailable'})
        body._ws = FakeWs(body, None)
        with mock.patch.object(minecraft, 'LOOK_TIMEOUT', 0.05):
            self.assertEqual(await body.look(), {'status': 'no_answer'})

    async def test_unlinked_body_does_nothing(self):
        body = minecraft.Body('ws://test', Said())
        self.assertEqual(await body.do('follow'), {'status': 'unavailable'})
        self.assertEqual(await body.stop(), {'status': 'unavailable'})
        self.assertEqual(await body.look(), {'status': 'unavailable'})


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
        self.assertEqual(m.route(ctx_with('今何が見えてる、シエル？'), {'seconds': 1.0}), 'mind')
        self.assertEqual(m.route(ctx_with('ツルハシ作れる？'), {'seconds': 1.0}), 'mind')
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
        args = {'go_to_place': {'x': 1, 'z': 2}, 'collect_blocks': {'block': 'oak_log', 'count': 3},
                'craft_item': {'item': 'stick'},
                'give_item': {'item': 'oak_log'}}
        for fn in tools.minecraft.TOOLS:
            result = await fn(ctx, **args.get(fn.id, {}))
            self.assertEqual(json.loads(result)['status'], 'unavailable', fn.id)


if __name__ == '__main__':
    unittest.main()
