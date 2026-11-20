import asyncio
import time
import types
import unittest
from unittest import mock

from livekit.agents import llm

import board
import mind
from conversation import Conversation


class Speaker:
    def __init__(self, name):
        self.name, self.label = name, name


def history_with(*rows):
    h = Conversation()
    for role, text, who in rows:
        t = h.reserve(role=role)
        h.complete(t, text, Speaker(who) if who else None, who or '不明', sure=True)
    return h


class Style:
    def __init__(self, talk='normal'):
        self.talk = talk


class MindBuildTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('clock.now_line', return_value='[今：朝]')
        patcher.start()
        self.addCleanup(patcher.stop)

    def livekit_ctx(self, *extra):
        ctx = llm.ChatContext()
        ctx.add_message(role='system', content='会話の指示')
        ctx.add_message(role='user', content='LiveKit だけが覚えている古い発言')
        ctx.add_message(role='assistant', content='古い返事')
        for role, text in extra:
            ctx.add_message(role=role, content=text)
        return ctx

    def test_context_comes_from_the_record(self):
        h = history_with(('user', '星を撮ったよ', 'ゆうき'), ('assistant', 'すてきなのです', None),
                         ('user', 'オリオン座だよ', 'ゆうき'))
        m = mind.Mind(h, style=Style())
        out = m.build(self.livekit_ctx(('user', '[発言者：ゆうき]\nオリオン座だよ')))
        texts = [(i.role, i.text_content) for i in out.items]
        self.assertEqual(texts[0], ('system', '会話の指示'))
        self.assertIn(('user', 'ゆうき：星を撮ったよ'), texts)
        self.assertIn(('assistant', 'すてきなのです'), texts)
        # 今回の発言は 1 回だけ（話者を添えた LiveKit の側の分）。LiveKit だけが覚えている発言は使わない
        self.assertEqual([t for r, t in texts if 'オリオン座' in t], ['[発言者：ゆうき]\nオリオン座だよ'])
        self.assertNotIn(('user', 'LiveKit だけが覚えている古い発言'), texts)
        self.assertEqual(texts[-1][1], '[発言者：ゆうき]\nオリオン座だよ')
        self.assertIn('[今：朝]', texts[-2][1])

    def test_an_earlier_same_utterance_stays_in_the_history(self):
        # 前と同じ言葉（2 回目の「うん」）でも、前の分は過去の発言として残す。消すと履歴の途中が変わり、キャッシュが外れる
        h = history_with(('user', 'うん', 'ゆうき'), ('assistant', 'よかったのです', None),
                         ('user', 'うん', 'ゆうき'))
        out = mind.Mind(h, style=Style()).build(self.livekit_ctx(('user', 'うん')))
        texts = [(i.role, i.text_content) for i in out.items]
        self.assertEqual(texts[1:3], [('user', 'ゆうき：うん'), ('assistant', 'よかったのです')])
        self.assertEqual([t for r, t in texts if r == 'user' and 'うん' in t], ['ゆうき：うん', 'うん'])

    def test_quiet_reminder_and_memory_and_minutes(self):
        minutes = mock.Mock()
        minutes.context.return_value = '[議事録状態] {}'
        minutes.take_note.return_value = '[議事録：送った]'
        m = mind.Mind(history_with(), style=Style('quiet'), minutes=minutes, quiet_turn='呼ばれたときだけ')
        out = m.build(self.livekit_ctx(('user', 'こんにちは')),
                      turn={'memory': '[覚えていること] 走るのが好き', 'tag': '[発言者：ゆうき]'})
        notes = out.items[-3].text_content
        for part in ('[議事録状態] {}', '[議事録：送った]', '走るのが好き', '呼ばれたときだけ'):
            self.assertIn(part, notes)
        # 話者の 1 行は、今回の発言のすぐ前に置く（LiveKit の会話の発言は書き換えない）
        self.assertEqual([i.text_content for i in out.items[-2:]], ['[発言者：ゆうき]', 'こんにちは'])

    def test_tool_calls_of_this_turn_are_kept(self):
        ctx = self.livekit_ctx(('user', '議事録とって'))
        ctx.items.append(llm.FunctionCall(call_id='c1', name='start_minutes', arguments='{}'))
        ctx.items.append(llm.FunctionCallOutput(call_id='c1', name='start_minutes', output='{}', is_error=False))
        out = mind.Mind(history_with(), style=Style()).build(ctx)
        self.assertEqual([getattr(i, 'type', None) for i in out.items[-2:]], ['function_call', 'function_call_output'])


class TalkerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = mock.patch('clock.now_line', return_value='[今：朝]')
        patcher.start()
        self.addCleanup(patcher.stop)

    def ctx_with(self, text):
        ctx = llm.ChatContext()
        ctx.add_message(role='system', content='全部の指示')
        ctx.add_message(role='user', content=text)
        return ctx

    async def test_the_reply_gets_the_fixed_instructions_and_the_brief(self):
        m = mind.Mind(history_with(), style=Style())
        m.apply_brief({'topic': '展示', 'decided': 'A2 で印刷'}, through=3)
        out = m.build(self.ctx_with('どう思う？'))
        texts = [i.text_content for i in out.items]
        self.assertEqual(texts[0], '全部の指示')
        self.assertIn('[今のまとめ]\n話題：展示\n決まったこと：A2 で印刷', texts[-2])

    async def test_the_history_window_moves_only_in_steps(self):
        # 先頭が毎回ずれると履歴のキャッシュが外れるので、超えたときだけまとめて進める
        h = history_with(*[('user', f'発言{i}', 'ゆうき') for i in range(mind.WINDOW_MAX)])
        m = mind.Mind(h, style=Style())
        first = m._window()[0]
        self.assertEqual(len(m._window()), mind.WINDOW_KEEP)

        def say(text):
            t = h.reserve(role='user')
            h.complete(t, text, Speaker('ゆうき'), 'ゆうき', sure=True)
        for n in range(mind.WINDOW_MAX - mind.WINDOW_KEEP):
            say(f'続き{n}')
        self.assertIs(m._window()[0], first)                   # 超えるまでは同じ先頭のまま
        self.assertEqual(len(m._window()), mind.WINDOW_MAX)
        say('次の発言')
        self.assertEqual(len(m._window()), mind.WINDOW_KEEP)   # 超えたら KEEP 件まで進める
        self.assertIsNot(m._window()[0], first)

    async def test_code_routes_turns(self):
        m = mind.Mind(history_with(), style=Style())
        self.assertEqual(m.route(self.ctx_with('シエルは何色が好き？'), {'seconds': 2.0}), 'mind')
        # 議事録・歌の知らせ、話す番（自分から話す）は、どこから来た返事かを残す
        m.on_say('research')
        self.assertEqual(m.route(llm.ChatContext()), 'mind')
        self.assertEqual(m.reply_origin, 'research')
        m.route(self.ctx_with('こんにちは'), {})
        self.assertEqual(m.reply_origin, 'reply')

    def board_with_minutes(self, said):
        tasks = board.Board()
        tasks.add('minutes', '会議の議事録をとる', board.RUNNING, 'listener', said=said)
        return tasks

    async def test_requests_on_the_board_are_not_requests_again(self):
        m = mind.Mind(history_with(), style=Style(), board=self.board_with_minutes('あ、そうだ、議事録開始して。'))
        ctx = self.ctx_with('商店街にも声をかけて。あ、そうだ、議事録開始して。それで屋台を増やしたい')
        self.assertEqual(m.route(ctx, {'seconds': 4.0}), 'mind')
        # 付箋になった頼みは付箋の印で渡す（終了の頼みと取り違えないように）
        items = m.build(ctx, turn={}).items
        self.assertNotIn('議事録開始して', items[-1].text_content)
        self.assertIn('（→ #1 会議の議事録をとる：実行中）', items[-1].text_content)
        self.assertIn('[今のタスク]\n#1 会議の議事録をとる：実行中', items[-2].text_content)

    async def test_a_turn_that_was_only_the_request_gets_no_reply(self):
        m = mind.Mind(history_with(), style=Style('quiet'), board=self.board_with_minutes('議事録開始して。'))
        self.assertEqual(m.route(self.ctx_with('あ、議事録開始して。'), {'seconds': 2.0}), 'skip')
        self.assertEqual(m.route(self.ctx_with('議事録開始して。ポスターは水曜まで'), {'seconds': 2.0}), 'mind')
        # 黙って聞いた前の発言が今回の分に残っていても、最後の発言が頼みだけなら返さない
        ctx = self.ctx_with('賛成です。じゃあ解説は私が下書きを作ります。')
        ctx.add_message(role='user', content='はっ、 議事録開始して。')
        self.assertEqual(m.route(ctx, {'seconds': 2.0}), 'skip')

    async def test_minutes_tools_only_when_this_turn_asks(self):
        # 道具の一覧は変えず（キャッシュのため）、頼みの無い発言では、始める・終える道具を呼んでも断る
        tools = [types.SimpleNamespace(id=n) for n in ('start_minutes', 'finish_minutes', 'read_minutes')]
        m = mind.Mind(history_with(), style=Style(), board=self.board_with_minutes('議事録開始して。'))
        moves = {'start_minutes', 'finish_minutes'}
        self.assertEqual(m.tools_for(self.ctx_with('予算は去年と同じくらい'), tools), tools)
        self.assertTrue(moves <= m.refused_now(self.ctx_with('予算は去年と同じくらい')))
        self.assertTrue(moves <= m.refused_now(self.ctx_with('それで、議事録開始して。屋台を増やしたい')))   # 付箋になった頼みは除く
        self.assertFalse(moves & m.refused_now(self.ctx_with('議事録まとめて')))
        self.assertFalse(moves & m.refused_now(self.ctx_with('記録ストップ')))
        # ほかの道具の結果を受けた続きでも、頼みが無ければ通さない
        ctx = self.ctx_with('予算は去年と同じくらい')
        ctx.items.append(llm.FunctionCall(call_id='c1', name='search_conversation', arguments='{}'))
        ctx.items.append(llm.FunctionCallOutput(call_id='c1', name='search_conversation', output='{}', is_error=False))
        self.assertTrue(moves <= m.refused_now(ctx))

    async def test_a_waiting_notice_goes_into_the_reply(self):
        m = mind.Mind(history_with(), style=Style())
        waiting = {'minutes': '[議事録：とり始めた]'}
        m.waiting = lambda: waiting
        ctx = self.ctx_with('ここまでで何か気になることある？')
        self.assertEqual(m.route(ctx, {'seconds': 2.0}), 'mind')
        items = m.build(ctx, turn={}).items
        self.assertIn('[まだ伝えていない知らせ]\n[議事録：とり始めた]', items[-2].text_content)
        self.assertEqual(m.handed, 'minutes')
        # 知らせそのものの返事（相手の発言が無い）には添えない
        ctx = llm.ChatContext()
        ctx.add_message(role='system', content='全部の指示')
        m.build(ctx)
        self.assertIsNone(m.handed)

    async def test_requests_on_the_board_stay_marked_in_later_turns(self):
        h = history_with(('user', '商店街にも声をかけて。あ、そうだ、議事録開始して。', 'ゆうき'))
        m = mind.Mind(h, style=Style(), board=self.board_with_minutes('議事録開始して。'))
        texts = [i.text_content for i in m.build(self.ctx_with('予算は去年と同じくらい'), turn={}).items]
        self.assertFalse(any('議事録開始して' in t for t in texts))
        self.assertIn('ゆうき：商店街にも声をかけて。あ、そうだ、（→ #1 会議の議事録をとる：実行中）', texts)
        # 今どうなっているかも渡す（していないことを言わないように）
        self.assertTrue(any('[今のタスク]' in t for t in texts))

    async def test_tool_results_go_to_the_mind(self):
        ctx = llm.ChatContext()
        ctx.add_message(role='user', content='議事録とって')
        ctx.items.append(llm.FunctionCallOutput(call_id='c1', name='start_minutes', output='{}', is_error=False))
        self.assertEqual(mind.Mind(history_with()).route(ctx), 'mind')

    async def test_brief_is_written_when_enough_was_said(self):
        h = history_with(*[('user', f'発言{i}', 'ゆうき') for i in range(6)])
        m = mind.Mind(h, style=Style(), brief_instructions='まとめて')
        m._brief_at -= 100
        with mock.patch.object(m, '_write_brief', mock.AsyncMock()) as write:
            m.step(time.monotonic())
            await asyncio.sleep(0)
        write.assert_called_once_with(h.last_id)


if __name__ == '__main__':
    unittest.main()
